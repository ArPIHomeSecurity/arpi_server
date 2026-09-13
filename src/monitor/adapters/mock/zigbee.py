"""Simulator-backed Zigbee adapter.

The mock follows the same runtime contract as the real Zigbee adapter: it reads
mutable live state from simulator_zigbee.json, resolves values by IEEE address,
endpoint, and capability, and exposes normalized readings that the monitor can
consume without bypassing the normal sensor/alert path.
"""

import logging
import threading
from datetime import datetime, timezone
from os import environ

from monitor.adapters.mock.utils import DEFAULT_ZIGBEE_DATA, ZIGBEE_FILE, protected_read
from utils.constants import LOG_ADZIGBEE

logger = logging.getLogger(LOG_ADZIGBEE)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ZigbeeAdapter:
    """Mock Zigbee coordinator adapter backed by simulator_zigbee.json."""

    def __init__(self):
        self._lock = threading.RLock()
        self._cache: dict[tuple[str, str, str], dict] = {}
        self._running = False

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

    def _load_state(self) -> dict:
        data = protected_read(ZIGBEE_FILE, DEFAULT_ZIGBEE_DATA)
        if not isinstance(data, dict):
            return {"devices": {}}

        devices = data.get("devices", {})
        if not isinstance(devices, dict):
            devices = {}

        return {"devices": devices}

    def _refresh_cache(self):
        """Rebuild the normalized in-memory cache from the simulator state file."""
        state = self._load_state()
        cache: dict[tuple[str, str, str], dict] = {}

        for ieee_address, device in state.get("devices", {}).items():
            if not isinstance(device, dict):
                continue

            capabilities = device.get("capabilities", {})
            if not isinstance(capabilities, dict):
                continue

            for capability_key, raw_value in capabilities.items():
                if "/" not in capability_key:
                    endpoint = "1"
                    capability = capability_key
                else:
                    endpoint, capability = capability_key.split("/", 1)

                cache[(str(ieee_address), str(endpoint), str(capability))] = {
                    "ieee_address": str(ieee_address),
                    "endpoint": str(endpoint),
                    "capability": str(capability),
                    "value": raw_value,
                    "timestamp": device.get("last_seen") or _utc_now_iso(),
                    "available": bool(device.get("available", True)),
                    "battery_level": device.get("battery_level", 100),
                    "signal_quality": device.get("signal_quality", 100),
                }

        with self._lock:
            self._cache = cache

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

    def get_device_state(self, ieee_address: str):
        """Return the raw runtime state for one simulated device."""
        state = self._load_state().get("devices", {}).get(str(ieee_address), {})
        if not isinstance(state, dict):
            return {}
        return dict(state)

    def close(self):
        self.stop()
