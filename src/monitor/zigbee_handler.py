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

from monitor.actions import MonitorStopCommand, MonitorZigbeePairingCommand
from monitor.adapters.zigbee import DiscoveredDevice, ZigbeeReading, get_zigbee_adapter
from monitor.broadcast import Broadcaster
from monitor.database import create_database_session
from monitor.socket_io import send_zigbee_pairing_state
from utils.constants import LOG_ZIGBEE, THREAD_ZIGBEE
from utils.models import ZigbeeDevice

logger = logging.getLogger(LOG_ZIGBEE)

COMMUNICATION_PERIOD = 0.5  # sec
PAIRING_DURATION = 60  # sec


class ZigbeeDeviceStore:
    """
    Thread safe storage of the Zigbee device states.

    Written by the Zigbee handler thread and read by the other threads.
    """

    _lock = RLock()
    _readings: ClassVar[dict[tuple[str, str, str], ZigbeeReading]] = {}
    _devices: ClassVar[dict[str, DiscoveredDevice]] = {}

    @classmethod
    def update_readings(cls, readings: list[ZigbeeReading]):
        new_readings = {
            (
                str(reading.ieee_address),
                str(reading.endpoint),
                str(reading.capability),
            ): reading
            for reading in readings
        }
        with cls._lock:
            cls._readings = new_readings

    @classmethod
    def get_reading(cls, ieee_address, endpoint, capability) -> ZigbeeReading | None:
        with cls._lock:
            return cls._readings.get((str(ieee_address), str(endpoint), str(capability)))

    @classmethod
    def get_readings(cls) -> list[ZigbeeReading]:
        with cls._lock:
            return list(cls._readings.values())

    @classmethod
    def update_devices(cls, devices: list[DiscoveredDevice]):
        new_devices = {str(device.ieee_address): device for device in devices}
        with cls._lock:
            cls._devices = new_devices

    @classmethod
    def get_devices(cls) -> list[DiscoveredDevice]:
        with cls._lock:
            return list(cls._devices.values())

    @classmethod
    def clear(cls):
        with cls._lock:
            cls._readings = {}
            cls._devices = {}


class ZigbeeHandler(Thread):
    """
    Thread managing the Zigbee coordinator: pairing and device state polling.
    """

    def __init__(self, broadcaster: Broadcaster):
        super().__init__(name=THREAD_ZIGBEE)
        self._actions = Queue()
        self._adapter = None
        self._pairing_start = None

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
                    case MonitorStopCommand():
                        break

            self.update_device_states()
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
            self._adapter.permit_joining(duration_seconds)
        except Exception:
            logger.exception("Failed to start Zigbee pairing")
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

        ZigbeeDeviceStore.update_devices(devices)
        self.register_devices(devices)
        self._pairing_start = -1

    def register_devices(self, devices: list[DiscoveredDevice]):
        """
        Store the newly discovered devices in the database, updating the already known ones.
        """
        try:
            with create_database_session() as session:
                for device in devices:
                    metadata = device.metadata or {}
                    values = {
                        "network_address": device.network_address,
                        "manufacturer": device.manufacturer,
                        "model": device.model,
                        "name": device.name or device.ieee_address,
                        "availability": (
                            "online" if metadata.get("available", True) else "offline"
                        ),
                        "last_seen": self._parse_last_seen(metadata.get("last_seen")),
                        "battery_level": metadata.get("battery_level"),
                        "signal_quality": metadata.get("signal_quality"),
                        "metadata": {"capabilities": device.capabilities},
                    }

                    registered = (
                        session.query(ZigbeeDevice)
                        .filter_by(ieee_address=device.ieee_address)
                        .first()
                    )
                    if registered is None:
                        session.add(ZigbeeDevice(ieee_address=device.ieee_address, **values))
                        logger.info("Registered new Zigbee device: %s", device.ieee_address)
                    else:
                        registered.update(values)

                session.commit()
        except Exception:
            logger.exception("Failed to register the Zigbee devices")

    @staticmethod
    def _parse_last_seen(last_seen):
        if not last_seen:
            return None
        with contextlib.suppress(TypeError, ValueError):
            return datetime.fromisoformat(last_seen)
        return None

    def update_device_states(self):
        """
        Refresh the shared store with the latest coordinator state.
        """
        try:
            ZigbeeDeviceStore.update_readings(self._adapter.get_values())
        except Exception:
            logger.exception("Failed to update the Zigbee device states")

    def close(self):
        ZigbeeDeviceStore.clear()
        if self._adapter is not None:
            with contextlib.suppress(Exception):
                self._adapter.stop()
            self._adapter = None
