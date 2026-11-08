"""Simulator-backed Zigbee adapter.

The mock follows the same runtime contract as the real Zigbee adapter: it reads
mutable live state from simulator_zigbee.json, resolves values by IEEE address,
endpoint, cluster, attribute, and signal field, and exposes normalized readings that the monitor can
consume without bypassing the normal sensor/alert path.
"""

import logging
import threading
from types import MappingProxyType

from monitor.adapters.mock.utils import (
    get_zigbee_devices,
    set_zigbee_devices,
)
from monitor.config.helper import load_config
from monitor.config.models import ZigbeeCoordinatorConfig
from utils.constants import LOG_ADZIGBEE
from utils.zigbee import (
    IAS_ZONE_STATUS_ATTRIBUTE,
    ZigbeeDevice,
    ZigbeeDeviceHealth,
    ZigbeeReading,
    ZigbeeSignal,
    ZigbeeSnapshot,
    ZigbeeSupervision,
    decode_zigbee_attribute,
)

logger = logging.getLogger(LOG_ADZIGBEE)


class ZigbeeAdapter:
    """Mock Zigbee coordinator adapter backed by simulator_zigbee.json."""

    def __init__(self):
        self._lock = threading.Lock()
        self._cache: dict[tuple[str, ZigbeeSignal], ZigbeeReading] = {}
        self._running = False
        self._pairing = False
        self._pairing_duration = 0
        self._supervision = ZigbeeSupervision()
        self._packet_tokens: dict[str, str | None] = {}

    def start(self):
        """Initializes the simulator adapter and refreshes the cache."""
        config = load_config(ZigbeeCoordinatorConfig)
        devices = get_zigbee_devices().get("devices", {})
        with self._lock:
            self._supervision = ZigbeeSupervision(
                config.supervision_timeout_seconds, config.supervision_timeout_overrides
            )
            self._packet_tokens = {
                str(address): device.get("last_seen") for address, device in devices.items()
            }
            for address in self._packet_tokens:
                self._supervision.register(address)
            self._running = True
            self._refresh_cache(devices)
        logger.debug("Mock ZigbeeAdapter started")

    def stop(self):
        """Stops the adapter and clears the cache."""
        with self._lock:
            self._running = False
            self._cache.clear()
        logger.debug("Mock ZigbeeAdapter stopped")

    def _refresh_cache(self, devices: dict):
        """Ingest parsed device state while the adapter lock is held."""
        for ieee_address, device in devices.items():
            ieee_address = str(ieee_address)
            timestamp = device.get("last_seen")
            if ieee_address not in self._packet_tokens:
                self._supervision.register(ieee_address)
            previous = self._packet_tokens.get(ieee_address)
            self._packet_tokens[ieee_address] = timestamp
            if not device.get("available", True):
                self._supervision.mark_offline(ieee_address)
                continue
            if timestamp is not None and timestamp != previous:
                self._supervision.record_packet(ieee_address)
            for signal in device.get("signal_values", []):
                raw_value = signal.get("value")
                if not isinstance(raw_value, bool):
                    continue

                reading = ZigbeeReading(
                    ieee_address, ZigbeeSignal.from_json(signal), raw_value, timestamp
                )
                self._cache[reading.key] = reading

            for endpoint, status in device.get("ias_zone_status", {}).items():
                decoded = decode_zigbee_attribute(IAS_ZONE_STATUS_ATTRIBUTE, status)
                for field, value in decoded.values:
                    reading = ZigbeeReading(
                        ieee_address,
                        IAS_ZONE_STATUS_ATTRIBUTE.signal(endpoint, field),
                        value,
                        timestamp,
                    )
                    self._cache[reading.key] = reading

    def get_joined_devices(self) -> list[ZigbeeDevice]:
        """Return the devices offered for pairing while joining is permitted."""
        if not self._pairing or self._pairing_duration <= 0:
            return []

        devices = get_zigbee_devices().get("devices", {})
        joining = {
            str(address)
            for address, device in devices.items()
            if device.get("pairing")
        }
        with self._lock:
            for address in joining:
                self._supervision.register(address)
        snapshot = self._snapshot(devices, include_devices=True)
        return [device for device in snapshot.devices or () if device.ieee_address in joining]

    def poll(self, include_devices: bool = False) -> ZigbeeSnapshot:
        """Read the simulator file once for readings, health, and optional metadata."""
        return self._snapshot(get_zigbee_devices().get("devices", {}), include_devices)

    def _snapshot(self, devices: dict, include_devices: bool) -> ZigbeeSnapshot:
        with self._lock:
            self._refresh_cache(devices)
            health = {
                address: health
                for address, health in self._supervision.snapshot(self._running).items()
                if address in devices
            }
            metadata = (
                tuple(
                    self._build_device(str(address), device, health[str(address)])
                    for address, device in devices.items()
                )
                if include_devices else None
            )
            return ZigbeeSnapshot(tuple(self._cache.values()), MappingProxyType(health), metadata)

    @staticmethod
    def _build_device(address: str, device: dict, health: ZigbeeDeviceHealth) -> ZigbeeDevice:
        metadata = [signal for signal in device.get("signal_metadata", []) if isinstance(signal, dict)]
        return ZigbeeDevice(
            ieee_address=address,
            network_address=device.get("network_address"),
            name=device.get("name"),
            manufacturer=device.get("manufacturer"),
            model=device.get("model"),
            available=health.available,
            last_seen=device.get("last_seen"),
            battery_level=device.get("battery_level"),
            signal_quality=device.get("signal_quality"),
            signals=[ZigbeeSignal.from_json(signal) for signal in metadata],
            zone_types={
                str(signal["endpoint"]): signal["zoneType"]
                for signal in metadata
                if signal.get("zoneType") is not None
            },
            health=health,
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

    def unpair_device(self, ieee_address: str) -> bool:
        """Unpair a simulated device by its IEEE address."""
        state = get_zigbee_devices()
        devices = state.get("devices", {})
        device = devices.get(str(ieee_address))
        if not device:
            return False

        device["pairing"] = False
        device["available"] = False
        with self._lock:
            self._supervision.mark_offline(str(ieee_address), removed=True)
        set_zigbee_devices(state)
        return True

    def close(self):
        self.stop()
