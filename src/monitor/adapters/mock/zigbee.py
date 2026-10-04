"""Simulator-backed Zigbee adapter.

The mock follows the same runtime contract as the real Zigbee adapter: it reads
mutable live state from simulator_zigbee.json, resolves values by IEEE address,
endpoint, and capability, and exposes normalized readings that the monitor can
consume without bypassing the normal sensor/alert path.
"""

import logging
import threading
from datetime import UTC, datetime

from monitor.adapters.mock.utils import (
    get_zigbee_devices,
    set_zigbee_devices,
)
from monitor.adapters.zigbee import ZigbeeDevice, ZigbeeSensorData
from utils.constants import LOG_ADZIGBEE
from utils.zigbee import IAS_TAMPER_CAPABILITY, IAS_ZONE_CAPABILITY, decode_zone_status

logger = logging.getLogger(LOG_ADZIGBEE)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


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
        state = get_zigbee_devices()
        cache: dict[tuple[str, str, str], ZigbeeSensorData] = {}

        for ieee_address, device in state.get("devices", {}).items():
            timestamp = device.get("last_seen") or _utc_now_iso()
            capabilities = device.get("capabilities", {})
            for capability_key, raw_value in capabilities.items():
                if not isinstance(raw_value, bool):
                    continue

                endpoint, separator, capability = capability_key.partition("/")
                if not separator:
                    endpoint, capability = "1", capability_key

                cache[(str(ieee_address), str(endpoint), str(capability))] = ZigbeeSensorData(
                    ieee_address=str(ieee_address),
                    endpoint=str(endpoint),
                    capability=str(capability),
                    value=raw_value,
                    timestamp=timestamp,
                )

            for endpoint, status in device.get("ias_zone_status", {}).items():
                alarm, tamper, error_reason = decode_zone_status(status)
                for capability, value in (
                    (IAS_ZONE_CAPABILITY, alarm), (IAS_TAMPER_CAPABILITY, tamper)
                ):
                    cache[(str(ieee_address), str(endpoint), capability)] = ZigbeeSensorData(
                        ieee_address=str(ieee_address),
                        endpoint=str(endpoint),
                        capability=capability,
                        value=value,
                        timestamp=timestamp,
                        error_reason=error_reason,
                    )

        with self._lock:
            self._cache = cache

    def get_joined_devices(self) -> list[ZigbeeDevice]:
        """Return the devices offered for pairing while joining is permitted."""
        if not self._pairing or self._pairing_duration <= 0:
            return []

        state = get_zigbee_devices()
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
                    capabilities=self._capability_metadata(device),
                    zone_type=device.get("zone_type"),
                )
            )

        return devices

    def get_device_states(self) -> list[ZigbeeDevice]:
        """Return the simulated coordinator view of every known device."""
        state = get_zigbee_devices()
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
                capabilities=self._capability_metadata(device),
                zone_type=device.get("zone_type"),
            )
            for ieee_address, device in state.get("devices", {}).items()
        ]

    @staticmethod
    def _capability_metadata(device):
        descriptors = device.get("capability_metadata", device.get("capabilities", {}))
        capabilities = {
            key: dict(descriptor)
            for key, descriptor in descriptors.items()
            if isinstance(descriptor, dict)
        }
        for key, descriptor in list(capabilities.items()):
            endpoint, separator, capability = key.partition("/")
            if separator and capability == IAS_ZONE_CAPABILITY:
                descriptor["field"] = "alarm"
                capabilities[f"{endpoint}/{IAS_TAMPER_CAPABILITY}"] = {
                    **descriptor, "field": "tamper"
                }
        return capabilities

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
        state = get_zigbee_devices()
        devices = state.get("devices", {})
        for device in devices.values():
            device["pairing"] = False

        set_zigbee_devices(state)

    def get_device_state(self, ieee_address: str):
        """Return the raw runtime state for one simulated device."""
        state = get_zigbee_devices()
        return dict(state.get("devices", {}).get(str(ieee_address), {}))

    def close(self):
        self.stop()
