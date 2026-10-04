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
from threading import RLock, Thread
from time import time
from typing import ClassVar

from monitor.actions import (
    MonitorStopCommand,
    MonitorUnpairZigbeeDeviceCommand,
    MonitorZigbeePairingCommand,
)
from monitor.adapters.zigbee import ZigbeeDevice, ZigbeeSensorData, get_zigbee_adapter
from monitor.broadcast import Broadcaster
from monitor.database import create_database_session
from monitor.socket_io import send_zigbee_pairing_state
from utils.constants import LOG_ZIGBEE, THREAD_ZIGBEE
from utils.models import ZigbeeDevice as ZigbeeDeviceModel

logger = logging.getLogger(LOG_ZIGBEE)

COMMUNICATION_PERIOD = 0.5  # sec
PAIRING_DURATION = 60  # sec
DEVICE_STATE_UPDATE_PERIOD = 30  # sec


class ZigbeeDeviceStore:
    """
    Thread safe storage of the Zigbee device states.

    Written by the Zigbee handler thread and read by the other threads.
    """

    _lock = RLock()
    _sensor_data: ClassVar[dict[tuple[str, str, str], ZigbeeSensorData]] = {}

    @classmethod
    def is_initialized(cls) -> bool:
        with cls._lock:
            return bool(cls._sensor_data)

    @classmethod
    def update_sensor_data(cls, sensor_datas: list[ZigbeeSensorData]):
        new_sensor_data = {
            (
                str(sensor_data.ieee_address),
                str(sensor_data.endpoint),
                str(sensor_data.capability),
            ): sensor_data
            for sensor_data in sensor_datas
        }
        with cls._lock:
            cls._sensor_data = new_sensor_data

    @classmethod
    def get_sensor_data(cls, ieee_address, endpoint, capability) -> ZigbeeSensorData | None:
        with cls._lock:
            return cls._sensor_data.get((str(ieee_address), str(endpoint), str(capability)))

    @classmethod
    def get_sensor_datas(cls) -> list[ZigbeeSensorData]:
        with cls._lock:
            return list(cls._sensor_data.values())

    @classmethod
    def clear(cls):
        with cls._lock:
            cls._sensor_data = {}


def extract_attributes(device: ZigbeeDevice, include_identity: bool = False, metadata=None):
    last_seen = None
    with contextlib.suppress(TypeError, ValueError):
        last_seen = datetime.fromisoformat(device.last_seen)

    values = {
        "availability": "online" if device.available else "offline",
        "last_seen": last_seen,
        "battery_level": device.battery_level,
        "signal_quality": device.signal_quality,
    }
    if device.zone_type is not None:
        values["zone_type"] = device.zone_type
    if device.capabilities or include_identity:
        metadata = metadata or {}
        values["metadata"] = {
            **metadata,
            "capabilities": {**metadata.get("capabilities", {}), **device.capabilities},
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

            self.update_device_states()
            self.update_registered_devices()
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

                    registered = (
                        session.query(ZigbeeDeviceModel)
                        .filter_by(
                            ieee_address=device.ieee_address,
                            deleted=False,
                        )
                        .first()
                    )
                    if registered is None:
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
        except Exception:
            logger.exception("Failed to persist the Zigbee devices")

    def update_device_states(self):
        """
        Refresh the shared store with the latest coordinator state.
        """
        try:
            ZigbeeDeviceStore.update_sensor_data(self._adapter.get_values())
        except Exception:
            logger.exception("Failed to update the Zigbee device states")

    def update_registered_devices(self):
        """
        Persist the availability and health attributes reported by the coordinator.
        """
        if time() - self._device_state_update < DEVICE_STATE_UPDATE_PERIOD:
            return

        self._device_state_update = time()
        devices = self._adapter.get_device_states()

        if not devices:
            return

        with create_database_session() as session:
            for device in devices:
                registered = (
                    session.query(ZigbeeDeviceModel)
                    .filter_by(ieee_address=device.ieee_address, deleted=False)
                    .first()
                )
                if registered is None:
                    continue

                values = extract_attributes(device, metadata=registered.device_metadata)
                registered.update(
                    {key: value for key, value in values.items() if value is not None}
                )

            session.commit()

    def close(self):
        ZigbeeDeviceStore.clear()
        if self._adapter is not None:
            with contextlib.suppress(Exception):
                self._adapter.stop()
            self._adapter = None
