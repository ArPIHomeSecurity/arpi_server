"""Simulator-backed Zigbee adapter.

The mock follows the same runtime contract as the real Zigbee adapter: it reads
mutable live state from simulator_zigbee.json, resolves values by IEEE address,
endpoint, cluster, attribute, and signal field, and exposes normalized readings that the monitor can
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
from utils.zigbee import IAS_ZONE_STATUS_ATTRIBUTE, decode_zigbee_attribute

logger = logging.getLogger(LOG_ADZIGBEE)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class ZigbeeAdapter:
    """Mock Zigbee coordinator adapter backed by simulator_zigbee.json."""

    def __init__(self):
        self._lock = threading.RLock()
        self._cache: dict[tuple[str, str, int, int, str | None], ZigbeeSensorData] = {}
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
        cache: dict[tuple[str, str, int, int, str | None], ZigbeeSensorData] = {}

        for ieee_address, device in state.get("devices", {}).items():
            timestamp = device.get("last_seen") or _utc_now_iso()
            for signal in device.get("signal_values", []):
                raw_value = signal.get("value")
                if not isinstance(raw_value, bool):
                    continue

                endpoint = str(signal["endpoint"])
                cluster_id = int(signal["clusterId"])
                attribute_id = int(signal["attributeId"])
                field = signal.get("field")
                cache[(str(ieee_address), endpoint, cluster_id, attribute_id, field)] = ZigbeeSensorData(
                    ieee_address=str(ieee_address),
                    endpoint=endpoint,
                    cluster_id=cluster_id,
                    attribute_id=attribute_id,
                    field=field,
                    value=raw_value,
                    timestamp=timestamp,
                )

            for endpoint, status in device.get("ias_zone_status", {}).items():
                decoded = decode_zigbee_attribute(IAS_ZONE_STATUS_ATTRIBUTE, status)
                for signal, value in decoded.signals:
                    cluster_id = int(IAS_ZONE_STATUS_ATTRIBUTE.cluster.cluster_id)
                    attribute_id = IAS_ZONE_STATUS_ATTRIBUTE.attribute_id
                    cache[(str(ieee_address), str(endpoint), cluster_id, attribute_id, signal.field)] = ZigbeeSensorData(
                        ieee_address=str(ieee_address),
                        endpoint=str(endpoint),
                        cluster_id=cluster_id,
                        attribute_id=attribute_id,
                        field=signal.field,
                        value=value,
                        timestamp=timestamp,
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
                    signals=self._signal_metadata(device),
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
                signals=self._signal_metadata(device),
            )
            for ieee_address, device in state.get("devices", {}).items()
        ]

    @staticmethod
    def _signal_metadata(device):
        return [
            dict(signal)
            for signal in device.get("signal_metadata", [])
            if isinstance(signal, dict)
        ]

    def get_values(self):
        """Return the latest normalized readings from the simulator cache."""
        self._refresh_cache()
        with self._lock:
            return list(self._cache.values())

    def get_value(
        self, ieee_address: str, endpoint: str, cluster_id: int, attribute_id: int, field=None
    ):
        """Return the normalized reading for a specific endpoint attribute signal."""
        self._refresh_cache()
        with self._lock:
            return self._cache.get(
                (str(ieee_address), str(endpoint), int(cluster_id), int(attribute_id), field)
            )

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
