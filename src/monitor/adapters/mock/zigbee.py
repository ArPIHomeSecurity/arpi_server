"""Simulator-backed Zigbee adapter.

The mock follows the same runtime contract as the real Zigbee adapter: it reads
mutable live state from simulator_zigbee.json, resolves values by IEEE address,
endpoint, and capability, and exposes normalized readings that the monitor can
consume without bypassing the normal sensor/alert path.
"""

import logging
import threading
from datetime import datetime, timezone

from monitor.adapters.mock.utils import (
    DEFAULT_ZIGBEE_DATA,
    ZIGBEE_FILE,
    protected_read,
    protected_write,
)
from monitor.adapters.zigbee import ZigbeeDevice, ZigbeeSensorData
from utils.constants import LOG_ADZIGBEE

logger = logging.getLogger(LOG_ADZIGBEE)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ZigbeeAdapter:
    """Mock Zigbee coordinator adapter backed by simulator_zigbee.json."""

    def __init__(self):
        self._lock = threading.RLock()
        self._cache: dict[tuple[str, str, str], ZigbeeSensorData] = {}
        self._running = False
        self._pairing = False
        self._pairing_duration = 0

    def start(self):
        """Initializes the simulator adapter and refreshes the cache."""
        self._running = True
        self._refresh_cache()
        logger.debug("Mock ZigbeeAdapter started")

    def stop(self):
        """Stops the adapter and clears the cache."""
        self._running = False
        with self._lock:
            self._cache.clear()
        logger.debug("Mock ZigbeeAdapter stopped")

    def is_running(self) -> bool:
        return self._running

    def _refresh_cache(self):
        """Rebuild the normalized in-memory cache from the simulator state file."""
        state = protected_read(ZIGBEE_FILE, DEFAULT_ZIGBEE_DATA)
        cache: dict[tuple[str, str, str], ZigbeeSensorData] = {}

        for ieee_address, device in state.get("devices", {}).items():
            capabilities = device.get("capabilities", {})
            for capability_key, raw_value in capabilities.items():
                if "/" not in capability_key:
                    endpoint = "1"
                    capability = capability_key
                else:
                    endpoint, capability = capability_key.split("/", 1)

                cache[(str(ieee_address), str(endpoint), str(capability))] = ZigbeeSensorData(
                    ieee_address=str(ieee_address),
                    endpoint=str(endpoint),
                    capability=str(capability),
                    value=raw_value,
                    timestamp=device.get("last_seen") or _utc_now_iso(),
                )

        with self._lock:
            self._cache = cache

    def get_joined_devices(self) -> list[ZigbeeDevice]:
        """Return the devices offered for pairing while joining is permitted."""
        if not self._pairing or self._pairing_duration <= 0:
            return []

        state = protected_read(ZIGBEE_FILE, DEFAULT_ZIGBEE_DATA)
        devices = []
        for ieee_address, device in state.get("devices", {}).items():
            if not device.get("pairing"):
                continue

            devices.append(
                ZigbeeDevice(
                    ieee_address=str(ieee_address),
                    network_address=device.get("network_address"),
                    name=device.get("name"),
                    manufacturer=device.get("manufacturer"),
                    model=device.get("model"),
                    available=bool(device.get("available", True)),
                    last_seen=device.get("last_seen"),
                    battery_level=device.get("battery_level", 100),
                    signal_quality=device.get("signal_quality", 100),
                    capabilities=dict(device.get("capabilities", {})),
                )
            )

        return devices

    def get_device_states(self) -> list[ZigbeeDevice]:
        """Return the simulated coordinator view of every known device."""
        state = protected_read(ZIGBEE_FILE, DEFAULT_ZIGBEE_DATA)
        return [
            ZigbeeDevice(
                ieee_address=str(ieee_address),
                network_address=device.get("network_address"),
                name=device.get("name"),
                manufacturer=device.get("manufacturer"),
                model=device.get("model"),
                available=bool(device.get("available", True)),
                last_seen=device.get("last_seen"),
                battery_level=device.get("battery_level"),
                signal_quality=device.get("signal_quality"),
            )
            for ieee_address, device in state.get("devices", {}).items()
        ]

    def get_values(self):
        """Return the latest normalized readings from the simulator cache."""
        self._refresh_cache()
        with self._lock:
            return list(self._cache.values())

    def get_value(self, ieee_address: str, endpoint: str, capability: str):
        """Return the normalized reading for a specific device endpoint/capability."""
        self._refresh_cache()
        with self._lock:
            return self._cache.get((str(ieee_address), str(endpoint), str(capability)))

    def permit_joining(self, duration_seconds) -> bool:
        """Open or close the pairing window, clearing pairing flags when closing."""
        if duration_seconds <= 0:
            self._pairing = False
            self._pairing_duration = 0
            self._clear_pairing_flags()
            logger.info("Zigbee joining closed")
            return True

        if not self._running:
            return False

        self._pairing = True
        self._pairing_duration = duration_seconds
        logger.info("Permitting Zigbee joining for %s seconds", duration_seconds)
        return True

    def _clear_pairing_flags(self):
        """Clear the pairing flags of simulated devices."""
        state = protected_read(ZIGBEE_FILE, DEFAULT_ZIGBEE_DATA)
        devices = state.get("devices", {})
        for device in devices.values():
            device["pairing"] = False

        protected_write(ZIGBEE_FILE, state)

    def get_device_state(self, ieee_address: str):
        """Return the raw runtime state for one simulated device."""
        state = protected_read(ZIGBEE_FILE, DEFAULT_ZIGBEE_DATA)
        return dict(state.get("devices", {}).get(str(ieee_address), {}))

    def close(self):
        self.stop()
