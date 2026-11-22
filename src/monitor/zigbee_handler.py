"""
Zigbee coordinator handling in a dedicated thread.

The handler owns the Zigbee adapter, polls the coordinator for device readings
and publishes them into a thread safe store that other threads (the sensor
handler) read from.
"""

import contextlib
import logging
from datetime import datetime
from queue import Empty, Queue
from threading import Lock, Thread
from time import monotonic, time
from typing import ClassVar

from sqlalchemy import select

from monitor.actions import (
    MonitorStopCommand,
    MonitorUnpairZigbeeDeviceCommand,
    MonitorZigbeePairingCommand,
)
from monitor.adapters.zigbee import get_zigbee_adapter
from monitor.broadcast import Broadcaster
from monitor.database import create_database_session
from monitor.socket_io import send_zigbee_pairing_state, send_zigbee_state
from utils.constants import LOG_ZIGBEE, THREAD_ZIGBEE
from utils.models import ZigbeeDevice as ZigbeeDeviceModel
from utils.zigbee import (
    ZigbeeDevice,
    ZigbeeEntityReading,
    ZigbeeSnapshot,
)

logger = logging.getLogger(LOG_ZIGBEE)

COMMUNICATION_PERIOD = 0.5  # sec
PAIRING_DURATION = 60  # sec
DEVICE_STATE_UPDATE_PERIOD = 30  # sec


class ZigbeeDeviceStore:
    """
    Thread safe storage of the Zigbee device states.

    Written by the Zigbee handler thread and read by the other threads.
    """

    _lock = Lock()
    _sensor_data: ClassVar[dict[tuple[str, str], ZigbeeEntityReading]] = {}

    @classmethod
    def update_snapshot(cls, snapshot: ZigbeeSnapshot):
        new_sensor_data = {reading.key: reading for reading in snapshot.readings}
        with cls._lock:
            cls._sensor_data = new_sensor_data

    @classmethod
    def get_entity_state(cls, ieee_address: str, entity_id: str) -> ZigbeeEntityReading | None:
        with cls._lock:
            reading = cls._sensor_data.get((ieee_address, entity_id))
        return reading if isinstance(reading, ZigbeeEntityReading) else None

    @classmethod
    def has_entity_status(cls, ieee_address: str, device_class: str) -> bool:
        with cls._lock:
            return any(
                reading.device_class == device_class
                and reading.available is not False
                and reading.value is True
                for (address, _), reading in cls._sensor_data.items()
                if address == str(ieee_address)
            )

    @classmethod
    def clear(cls):
        with cls._lock:
            cls._sensor_data = {}


def extract_attributes(device: ZigbeeDevice, include_identity: bool = False, metadata=None):
    last_seen = None
    with contextlib.suppress(TypeError, ValueError):
        last_seen = datetime.fromisoformat(device.last_seen)

    values = {
        "last_seen": last_seen,
        "battery_level": device.battery_level,
        "signal_quality": device.signal_quality,
    }
    if device.entities or include_identity or metadata is not None:
        values["metadata"] = {
            **(metadata or {}),
            "entities": device.entities_json(),
        }
    if include_identity:
        values.update(
            {
                "network_address": device.network_address,
                "manufacturer": device.manufacturer,
                "model": device.model,
                "name": device.name or device.ieee_address,
            }
        )
    return values


class ZigbeeHandler(Thread):
    """
    Thread managing the Zigbee coordinator: pairing and device state polling.
    """

    def __init__(self, broadcaster: Broadcaster):
        super().__init__(name=THREAD_ZIGBEE)
        self._actions = Queue()
        self._adapter = None
        self._pairing_start = None
        self._device_state_update = 0

        self._broadcaster = broadcaster
        self._broadcaster.register_queue(id(self), self._actions)

    def run(self):
        try:
            self._adapter = get_zigbee_adapter()
            self._adapter.start()
            self.communicate()
        except Exception:
            logger.exception("Zigbee thread crashed!")
        finally:
            self.close()

        logger.info("Zigbee handler stopped")

    def communicate(self):
        # load devices from the database
        send_zigbee_state()

        while True:
            with contextlib.suppress(Empty):
                message = self._actions.get(timeout=COMMUNICATION_PERIOD)
                logger.debug("Command: %s", message)
                match message:
                    case MonitorZigbeePairingCommand():
                        self.start_pairing()
                    case MonitorUnpairZigbeeDeviceCommand():
                        self._adapter.unpair_device(message.ieee_address)
                    case MonitorStopCommand():
                        break

            snapshot = self.update_device_states()
            if snapshot is not None and snapshot.devices is not None:
                self.update_registered_devices(snapshot)
            if self._pairing_start:
                self.poll_pairing()
                send_zigbee_pairing_state(
                    state=True,
                    remain_seconds=max(0, PAIRING_DURATION - (time() - self._pairing_start)),
                    progress=min(1.0, (time() - self._pairing_start) / PAIRING_DURATION),
                )

            # detect end of pairing
            if self._pairing_start and time() - self._pairing_start > PAIRING_DURATION:
                if self._pairing_start == -1:
                    logger.info("Zigbee pairing successful")
                else:
                    logger.info("Zigbee pairing duration expired")

                self._pairing_start = None
                with contextlib.suppress(Exception):
                    self._adapter.permit_joining(0)

                send_zigbee_pairing_state(
                    state=False,
                    remain_seconds=0,
                    progress=0.0,
                )

    def start_pairing(self, duration_seconds: int = PAIRING_DURATION):
        """
        Enable joining on the coordinator for the given duration.
        """
        logger.info("Starting Zigbee pairing for %s seconds", duration_seconds)
        try:
            started = self._adapter.permit_joining(duration_seconds)
        except Exception:
            logger.exception("Failed to start Zigbee pairing")
            started = False

        if not started:
            send_zigbee_pairing_state(
                state=False,
                remain_seconds=0,
                progress=0.0,
            )
            return

        self._pairing_start = time()
        send_zigbee_pairing_state(
            state=True,
            remain_seconds=duration_seconds,
            progress=0.0,
        )

    def poll_pairing(self):
        """
        Collect the devices joining during the pairing window and register them.
        """
        try:
            devices = self._adapter.get_joined_devices()
        except Exception:
            logger.exception("Failed to get the joining Zigbee devices")
            return

        if not devices:
            return

        self.register_devices(devices)
        self._pairing_start = -1

    def register_devices(self, devices: list[ZigbeeDevice]):
        """
        Store the newly discovered devices in the database, updating the already known ones.
        """
        self._persist_devices(devices, log_new=True)

    def _persist_devices(self, devices: list[ZigbeeDevice], log_new: bool):
        """
        Insert newly discovered devices and refresh already registered ones in the database.
        """
        try:
            with create_database_session() as session:
                for device in devices:
                    values = extract_attributes(device, include_identity=True)

                    registered = session.scalar(
                        select(ZigbeeDeviceModel).where(
                            ZigbeeDeviceModel.ieee_address == device.ieee_address,
                            ZigbeeDeviceModel.deleted == False,
                        )
                    )
                    if registered is None:
                        deleted_device = session.scalar(
                            select(ZigbeeDeviceModel).where(
                                ZigbeeDeviceModel.ieee_address == device.ieee_address,
                                ZigbeeDeviceModel.deleted == True,
                            )
                        )
                        if deleted_device is not None:
                            deleted_device.deleted = False
                            deleted_device.update(values)
                            registered = deleted_device
                            if log_new:
                                logger.info("Re-paired Zigbee device: %s", device.ieee_address)
                        else:
                            session.add(ZigbeeDeviceModel(ieee_address=device.ieee_address, **values))
                            if log_new:
                                logger.info("Registered new Zigbee device: %s", device.ieee_address)
                    else:
                        values = extract_attributes(
                            device, include_identity=True, metadata=registered.device_metadata
                        )
                        if device.name is None:
                            values.pop("name")
                        registered.update(values)

                session.commit()

            send_zigbee_state()
        except Exception:
            logger.exception("Failed to persist the Zigbee devices")

    def update_device_states(self) -> ZigbeeSnapshot | None:
        """
        Refresh the shared store with the latest coordinator state.
        """
        try:
            snapshot = self._adapter.poll(include_devices=monotonic() >= self._device_state_update)
            ZigbeeDeviceStore.update_snapshot(snapshot)
            return snapshot
        except Exception:
            logger.exception("Failed to update the Zigbee device states")

    def update_registered_devices(self, snapshot: ZigbeeSnapshot):
        """
        Persist device metadata reported by the coordinator.
        """
        self._device_state_update = monotonic() + DEVICE_STATE_UPDATE_PERIOD
        devices = {device.ieee_address: device for device in snapshot.devices or ()}

        with create_database_session() as session:
            registered_devices = session.scalars(
                select(ZigbeeDeviceModel).where(ZigbeeDeviceModel.deleted.is_(False))
            ).all()
            for registered in registered_devices:
                device = devices.get(registered.ieee_address)
                if device is not None:
                    values = extract_attributes(device, metadata=registered.device_metadata)
                    registered.update(
                        {key: value for key, value in values.items() if value is not None}
                    )
            session.commit()

        send_zigbee_state()

    def close(self):
        ZigbeeDeviceStore.clear()
        if self._adapter is not None:
            try:
                self._adapter.stop()
            except Exception:
                logger.exception("Failed to stop the Zigbee adapter")
            self._adapter = None
