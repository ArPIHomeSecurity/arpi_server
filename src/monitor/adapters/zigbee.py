import asyncio
import logging
import os
import threading
import time
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime
from enum import Enum
from os import environ

import zhaquirks
from zha.application.const import (
    ZHA_GW_MSG_DEVICE_FULL_INIT,
    ZHA_GW_MSG_DEVICE_JOINED,
    ZHA_GW_MSG_DEVICE_REMOVED,
)
from zha.application.gateway import Gateway
from zha.application.helpers import (
    CoordinatorConfiguration,
    QuirksConfiguration,
    ZHAConfiguration,
    ZHAData,
)
from zha.zigbee.device import BaseDevice as ZhaDevice
from zigpy.types import EUI64

from monitor.config.helper import load_config
from monitor.config.models import ZigbeeCoordinatorConfig
from utils.constants import LOG_ADZIGBEE
from utils.zigbee import (
    ZigbeeDevice,
    ZigbeeEntity,
    ZigbeeEntityReading,
    ZigbeeSnapshot,
)

USE_ZIGBEE_SIMULATOR = environ.get("USE_ZIGBEE_SIMULATOR", "false").lower() in [
    "true",
    "1",
    "yes",
]

logger = logging.getLogger(LOG_ADZIGBEE)


def get_zigbee_adapter():
    """Return the simulator or real Zigbee adapter based on the runtime mode."""
    if USE_ZIGBEE_SIMULATOR:
        from monitor.adapters.mock.zigbee import ZigbeeAdapter as MockZigbeeAdapter

        logger.debug("Using mock Zigbee adapter")
        return MockZigbeeAdapter()

    return ZigbeeAdapter()


class ZigbeeAdapter:
    """ArPI adapter around the ZHA gateway."""

    def __init__(self):
        self._enabled = False
        self._serial_port: str | None = None
        self._baudrate = 115200
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._gateway: Gateway | None = None
        self._running = False
        self._ready = False
        self._startup_error: Exception | None = None

        self._pairing_lock = threading.Lock()
        self._pairing_active = False
        self._known_before_pairing: set[str] = set()
        self._joining_devices: set[str] = set()
        self._discovered: list[ZigbeeDevice] = []

        self._state_lock = threading.Lock()
        self._devices: dict[str, ZhaDevice] = {}
        self._readings: dict[tuple[str, str], ZigbeeEntityReading] = {}
        self._entity_unsubscribers: dict[tuple[str, str], Callable[[], None]] = {}

    def start(self):
        """Start the ZHA gateway in a dedicated event loop thread."""
        if self._running:
            return

        config = load_config(ZigbeeCoordinatorConfig)
        self._ready = False
        self._startup_error = None
        self._enabled = config.enabled
        self._serial_port = config.serial_port
        self._baudrate = config.baudrate

        if not self._enabled:
            logger.info("Zigbee coordinator is disabled")
            return

        if not self._serial_port:
            logger.warning("Zigbee serial port is not configured, coordinator not started")
            self._enabled = False
            return

        if not os.path.exists(self._serial_port):
            logger.warning(
                "Zigbee serial port %s does not exist, coordinator not started",
                self._serial_port,
            )
            self._enabled = False
            return

        self._thread = threading.Thread(
            target=self._run_event_loop, name="ZHAGatewayLoop", daemon=True
        )
        self._thread.start()

        while self._thread.is_alive() and not self._ready:
            time.sleep(0.05)

        if self._startup_error is not None:
            raise RuntimeError(
                "Failed to initialize the ZHA Zigbee gateway"
            ) from self._startup_error
        if not self._ready:
            raise RuntimeError("ZHA Zigbee gateway stopped before becoming ready")

    def _run_event_loop(self):
        """Worker function running the gateway event loop."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._running = True

        try:
            self._loop.run_until_complete(self._async_init())
        except Exception as error:
            self._startup_error = error
            logger.exception("Failed to initialize the ZHA Zigbee gateway")
        else:
            self._ready = True
            self._loop.run_forever()
        finally:
            self._ready = False
            self._loop.close()
            self._running = False

    async def _async_init(self):
        """Initialize ZHA and install its device-quirk provider."""
        configuration = ZHAConfiguration(
            coordinator_configuration=CoordinatorConfiguration(
                path=self._serial_port,
                baudrate=self._baudrate,
                # The Sonoff MG21 dongle has no RTS/CTS wiring; preserve Bellows' old default.
                flow_control="software",
                radio_type="ezsp",
            ),
            quirks_configuration=QuirksConfiguration(setup_function=zhaquirks.setup),
        )
        data = ZHAData(
            config=configuration,
            zigpy_config={"database_path": os.environ["ZIGBEE_DATABASE_PATH"]},
        )
        self._gateway = await Gateway.async_from_config(data)
        self._gateway.on_event(ZHA_GW_MSG_DEVICE_JOINED, self._device_joined)
        self._gateway.on_event(ZHA_GW_MSG_DEVICE_FULL_INIT, self._device_initialized)
        self._gateway.on_event(ZHA_GW_MSG_DEVICE_REMOVED, self._device_removed)
        await self._gateway.async_initialize()

        for device in self._gateway.devices.values():
            if not device.is_active_coordinator:
                self._register_device(device)

        logger.info("ZHA Zigbee gateway initialized")

    def stop(self):
        """Shut down the ZHA gateway from another thread."""
        self._ready = False
        if self._gateway is None or self._loop is None:
            self._running = False
            return

        if self._loop.is_running():
            future = asyncio.run_coroutine_threadsafe(self._gateway.shutdown(), self._loop)
            future.result(timeout=10.0)
            self._loop.call_soon_threadsafe(self._loop.stop)
        self._running = False

    def _device_joined(self, event):
        ieee_address = str(event.device_info.ieee)
        with self._pairing_lock:
            pairing_active = self._pairing_active
            if self._pairing_active and ieee_address not in self._known_before_pairing:
                self._joining_devices.add(ieee_address)
        logger.info(
            "ZHA received join notification for Zigbee device %s (NWK 0x%04x, pairing active: %s)",
            ieee_address,
            event.device_info.nwk,
            pairing_active,
        )

    def _device_initialized(self, event):
        if self._gateway is None:
            return

        device = self._gateway.devices.get(event.device_info.ieee)
        if device is None or device.is_active_coordinator:
            return

        self._register_device(device)
        ieee_address = str(device.ieee)
        with self._pairing_lock:
            pairing_active = self._pairing_active
            if ieee_address in self._joining_devices or (pairing_active and event.new_join):
                self._joining_devices.discard(ieee_address)
                self._discovered.append(self._build_device(device))
                logger.info("Discovered Zigbee device %s", ieee_address)
            elif event.new_join:
                logger.info(
                    "ZHA initialized new Zigbee device %s outside the active pairing window",
                    ieee_address,
                )

    def _device_removed(self, event):
        ieee_address = str(event.device_info.ieee)
        with self._state_lock:
            self._devices.pop(ieee_address, None)
            for key, unsubscribe in list(self._entity_unsubscribers.items()):
                if key[0] == ieee_address:
                    unsubscribe()
                    del self._entity_unsubscribers[key]
            self._readings = {
                key: reading for key, reading in self._readings.items() if key[0] != ieee_address
            }

    def _register_device(self, device: ZhaDevice):
        ieee_address = str(device.ieee)
        with self._state_lock:
            old_subscriptions = [
                (key, unsubscribe)
                for key, unsubscribe in self._entity_unsubscribers.items()
                if key[0] == ieee_address
            ]
            for key, _ in old_subscriptions:
                del self._entity_unsubscribers[key]
            self._readings = {
                key: reading for key, reading in self._readings.items() if key[0] != ieee_address
            }
            self._devices[ieee_address] = device

        for _, unsubscribe in old_subscriptions:
            unsubscribe()

        for entity in device.platform_entities.values():
            platform = str(entity.PLATFORM)
            entity_id = f"{platform}/{entity.unique_id}"
            key = (ieee_address, entity_id)
            with self._state_lock:
                already_subscribed = key in self._entity_unsubscribers
            if already_subscribed:
                continue

            unsubscribe = entity.subscribe_state(
                lambda event, device=device, entity=entity: self._entity_updated(
                    device, entity, event
                )
            )
            with self._state_lock:
                self._entity_unsubscribers[key] = unsubscribe
                self._readings[key] = self._build_reading(ieee_address, entity)


    def _entity_updated(self, device: ZhaDevice, entity, _event):
        ieee_address = str(device.ieee)
        reading = self._build_reading(ieee_address, entity)
        with self._state_lock:
            self._readings[reading.key] = reading

    @staticmethod
    def _json_value(value):
        if isinstance(value, Enum):
            return ZigbeeAdapter._json_value(value.value)
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        if isinstance(value, Mapping):
            return {str(key): ZigbeeAdapter._json_value(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set, frozenset)):
            return [ZigbeeAdapter._json_value(item) for item in value]
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        return str(value)

    @classmethod
    def _entity_value(cls, state):
        if hasattr(state, "is_on"):
            return cls._json_value(state.is_on)
        if hasattr(state, "native_value"):
            return cls._json_value(state.native_value)
        return None

    @classmethod
    def _entity_attributes(cls, state) -> dict:
        attributes = getattr(state, "extra_state_attributes", {})
        return cls._json_value(attributes) if attributes else {}

    @classmethod
    def _build_reading(cls, ieee_address: str, entity) -> ZigbeeEntityReading:
        state = entity.state
        platform = str(entity.PLATFORM)
        entity_id = f"{platform}/{entity.unique_id}"
        return ZigbeeEntityReading(
            ieee_address=ieee_address,
            entity_id=entity_id,
            value=cls._entity_value(state),
            device_class=cls._json_value(state.device_class),
            attributes=cls._entity_attributes(state),
            available=state.available,
            timestamp=datetime.now(UTC).isoformat(),
        )

    @classmethod
    def _build_entity(cls, entity) -> ZigbeeEntity:
        state = entity.state
        platform = str(entity.PLATFORM)
        entity_id = f"{platform}/{entity.unique_id}"
        device_class = cls._json_value(state.device_class)
        cluster = getattr(entity, "cluster", None)
        cluster_name = getattr(cluster, "name", None) or getattr(cluster, "ep_attribute", None)
        return ZigbeeEntity(
            entity_id=entity_id,
            unique_id=entity.unique_id,
            platform=platform,
            name=entity.fallback_name or entity.translation_key or entity.unique_id,
            cluster=cluster_name,
            attribute=getattr(state, "attribute_name", None),
            device_class=device_class,
            value=cls._entity_value(state),
            available=state.available,
            attributes=cls._entity_attributes(state),
        )

    def _build_device(self, device: ZhaDevice) -> ZigbeeDevice:
        last_seen = (
            datetime.fromtimestamp(device.last_seen, UTC).isoformat()
            if device.last_seen is not None
            else None
        )
        entities = [
            self._build_entity(entity) for entity in device.platform_entities.values()
        ]
        battery_level = next(
            (
                min(100, max(0, int(entity.value)))
                for entity in entities
                if entity.device_class == "battery"
                and isinstance(entity.value, (int, float))
            ),
            None,
        )
        return ZigbeeDevice(
            ieee_address=str(device.ieee),
            network_address=int(device.nwk),
            manufacturer=device.manufacturer,
            model=device.model,
            name=device.name,
            last_seen=last_seen,
            battery_level=battery_level,
            signal_quality=device.lqi,
            entities=entities,
        )

    def poll(self, include_devices: bool = False) -> ZigbeeSnapshot:
        """Return the current ZHA entity readings and optional device metadata."""
        with self._state_lock:
            readings = tuple(self._readings.values())
            known_devices = tuple(self._devices.values()) if include_devices else ()

        devices = (
            tuple(self._build_device(device) for device in known_devices)
            if include_devices
            else None
        )
        return ZigbeeSnapshot(readings, devices)

    async def _async_permit_joining(self, duration_seconds: int):
        if self._gateway is None or self._gateway.application_controller is None:
            raise RuntimeError("ZHA Zigbee gateway is not initialized")

        if duration_seconds > 0:
            with self._state_lock:
                known = set(self._devices)
            with self._pairing_lock:
                self._pairing_active = True
                self._known_before_pairing = known
                self._joining_devices.clear()
                self._discovered.clear()
        else:
            with self._pairing_lock:
                self._pairing_active = False

        await self._gateway.application_controller.permit(duration_seconds)

    def permit_joining(self, duration_seconds: int) -> bool:
        """Enable or disable device joining."""
        if not self._enabled:
            logger.warning("Zigbee coordinator is disabled, joining not permitted")
            return False
        if self._loop is None or self._gateway is None:
            logger.warning("ZHA Zigbee gateway is not running, joining not permitted")
            return False

        future = asyncio.run_coroutine_threadsafe(
            self._async_permit_joining(duration_seconds), self._loop
        )
        future.result(timeout=10.0)
        logger.info(
            "Zigbee joining %s for %s seconds",
            "enabled" if duration_seconds else "disabled",
            duration_seconds,
        )
        return True

    def get_joined_devices(self) -> list[ZigbeeDevice]:
        """Drain devices that completed ZHA initialization during pairing."""
        with self._pairing_lock:
            devices, self._discovered = self._discovered, []
        return devices

    def unpair_device(self, ieee_address: str) -> bool:
        """Remove a device through the ZHA gateway."""
        if not self._enabled:
            logger.warning("Zigbee coordinator is disabled, unpairing not possible")
            return False
        if self._loop is None or self._gateway is None:
            logger.warning("ZHA Zigbee gateway is not running, unpairing not possible")
            return False

        try:
            ieee = EUI64.convert(ieee_address)
            future = asyncio.run_coroutine_threadsafe(
                self._gateway.async_remove_device(ieee), self._loop
            )
            future.result(timeout=10.0)
            logger.info("Zigbee device unpaired: %s", ieee_address)
            return True
        except Exception:
            logger.exception("Failed to unpair Zigbee device %s", ieee_address)
            return False
