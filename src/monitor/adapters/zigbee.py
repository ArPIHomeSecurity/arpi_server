import asyncio
import contextlib
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from os import environ

from bellows.zigbee.application import ControllerApplication
from zigpy.exceptions import ZigbeeException
from zigpy.types import EUI64
from zigpy.zcl import foundation
from zigpy.zcl.clusters.general import PollControl, PowerConfiguration
from zigpy.zcl.clusters.security import IasZone

from monitor.config.models import ZigbeeCoordinatorConfig
from monitor.database import create_database_session
from utils.constants import LOG_ADZIGBEE
from utils.zigbee import (
    IAS_TAMPER_CAPABILITY,
    IAS_ZONE_CAPABILITY,
    decode_zone_status,
    encode_capability,
    normalize_attribute_value,
)

USE_ZIGBEE_SIMULATOR = environ.get("USE_ZIGBEE_SIMULATOR", "false").lower() in ["true", "1", "yes"]

logger = logging.getLogger(LOG_ADZIGBEE)


@dataclass
class ZigbeeSensorData:
    ieee_address: str
    endpoint: str
    capability: str
    value: object
    timestamp: str | None = None
    error_reason: str | None = None


@dataclass
class ZigbeeDevice:
    ieee_address: str
    network_address: int | None = None
    manufacturer: str | None = None
    model: str | None = None
    name: str | None = None
    available: bool = True
    last_seen: str | None = None
    battery_level: int | None = None
    signal_quality: int | None = None
    capabilities: dict = field(default_factory=dict)
    zone_type: int | None = None


def get_zigbee_adapter():
    """Return the simulator or real Zigbee adapter based on the runtime mode."""
    if USE_ZIGBEE_SIMULATOR:
        from monitor.adapters.mock.zigbee import ZigbeeAdapter as MockZigbeeAdapter
        logger.debug("Using mock Zigbee adapter")
        return MockZigbeeAdapter()

    return ZigbeeAdapter()


class ZigbeeAdapter:
    def __init__(self):
        self._enabled = False
        self._serial_port: str | None = None
        self._baudrate: int = 115200
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self.app: ControllerApplication | None = None
        self._running = False

        self._pairing_lock = threading.Lock()
        self._pairing_seen: set[str] = set()
        self._discovered: list[ZigbeeDevice] = []

        self._readings_lock = threading.Lock()
        self._readings: dict[tuple[str, int, str], ZigbeeSensorData] = {}

        self._state_lock = threading.Lock()
        self._battery_levels: dict[str, int] = {}
        self._offline_devices: set[str] = set()
        self._zone_types: dict[tuple[str, int], int] = {}

        self._tasks: set[asyncio.Task] = set()

    def start(self):
        """Start the dedicated asyncio event loop in a background thread."""
        if self._running:
            return

        with create_database_session() as db_session:
            config = ZigbeeCoordinatorConfig.load_config(session=db_session)
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
            logger.warning("Zigbee serial port %s does not exist, coordinator not started", self._serial_port)
            self._enabled = False
            return

        self._thread = threading.Thread(
            target=self._run_event_loop, name="BellowsLoop", daemon=True
        )
        self._thread.start()

        while self.app is None and self._running:
            time.sleep(0.05)

    def _run_event_loop(self):
        """Worker function running on the background thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._running = True

        try:
            self._loop.run_until_complete(self._async_init())
            self._loop.run_forever()
        finally:
            self._loop.close()
            self._running = False

    async def _async_init(self):
        """Asynchronous initialization of the bellows radio."""
        config = {
            "device": {
                "path": self._serial_port,
                "baudrate": self._baudrate,
            },
        }
        self.app = await ControllerApplication.new(config, auto_form=False)
        self.app.add_listener(self)

        # devices restored from the zigpy database do not emit device_initialized
        for device in list(self.app.devices.values()):
            if str(device.ieee) == str(self.app.state.node_info.ieee):
                continue
            await self._subscribe_clusters(device)
        logger.info("Bellows radio initialized")

    def stop(self):
        """Thread-safe shutdown sequence."""
        if self.app is None or self._loop is None:
            self._running = False
            return

        if self._loop.is_running():
            future = asyncio.run_coroutine_threadsafe(self.app.shutdown(), self._loop)
            future.result(timeout=5.0)
            self._loop.call_soon_threadsafe(self._loop.stop)
        self._running = False

    # --- zigpy application listener callbacks, invoked from the loop thread ---
    async def _subscribe_clusters(self, device):
        """Attach an attribute_updated listener to every cluster of a device."""
        logger.debug("Subscribing to clusters for device %s", device.ieee)
        for endpoint_id, endpoint in device.endpoints.items():
            if endpoint_id == 0:
                continue

            for cluster in endpoint.in_clusters.values():
                cluster.add_context_listener(self)
                cluster_name = cluster.ep_attribute or type(cluster).__name__

                if cluster_name == PollControl.ep_attribute:
                    await self._setup_reporting(
                        cluster, PollControl.AttributeDefs.checkin_interval.name, 60, 600
                    )
                elif cluster_name == IasZone.ep_attribute:
                    attribute = IasZone.AttributeDefs.zone_type
                    cached_type = cluster.get(attribute.id)
                    if cached_type is not None:
                        self._store_reading(
                            cluster, attribute.id, attribute.name, cached_type, datetime.now(UTC)
                        )
                    await self._read_attribute(cluster, attribute.name)
                    await self._setup_reporting(
                        cluster, IasZone.AttributeDefs.zone_status.name, 60, 600
                    )
                elif cluster_name == PowerConfiguration.ep_attribute:
                    await self._setup_reporting(
                        cluster,
                        PowerConfiguration.AttributeDefs.battery_percentage_remaining.name,
                        3600,
                        21600,
                    )

    async def _setup_reporting(
        self,
        cluster,
        attribute: str,
        min_interval: int,
        max_interval: int,
        reportable_change: int = 1,
    ):
        """Configure reporting of an attribute and seed its current value."""
        ieee_address = str(cluster.endpoint.device.ieee)
        try:
            await cluster.configure_reporting(
                attribute=attribute,
                min_interval=min_interval,
                max_interval=max_interval,
                reportable_change=reportable_change,
            )
        except (ZigbeeException, TimeoutError):
            logger.info(
                "Failed to configure reporting of %s for device %s", attribute, ieee_address
            )

        await self._read_attribute(cluster, attribute)

    async def _read_attribute(self, cluster, attribute: str):
        ieee_address = str(cluster.endpoint.device.ieee)
        try:
            success, _ = await cluster.read_attributes([attribute])
        except (ZigbeeException, TimeoutError):
            logger.info("Failed to read %s of device %s", attribute, ieee_address)
            return

        # zigpy suppresses the attribute_updated listener for read responses
        attribute_def = cluster.find_attribute(attribute)
        for value in success.values():
            self._store_reading(
                cluster, attribute_def.id, attribute_def.name, value, datetime.now(UTC)
            )

    def _build_discovered_device(self, device) -> ZigbeeDevice:
        capabilities = {}
        for endpoint_id, endpoint in device.endpoints.items():
            if endpoint_id == 0:
                continue

            for cluster in endpoint.clusters:
                cluster_name = cluster.ep_attribute or type(cluster).__name__
                command_sources = self._get_command_attribute_sources(cluster)
                for attribute in cluster.attributes.values():
                    if not self._is_sensor_attribute(attribute):
                        continue

                    is_reportable = bool(attribute.access & foundation.ZCLAttributeAccess.Report)
                    sources = command_sources.get(attribute.name, [])
                    if not is_reportable and not sources:
                        continue

                    capability = encode_capability(cluster.cluster_id, attribute.id)
                    capabilities[f"{endpoint_id}/{capability}"] = {
                        "cluster": cluster_name,
                        "clusterId": int(cluster.cluster_id),
                        "attribute": attribute.name,
                        "attributeId": int(attribute.id),
                        "valueType": getattr(attribute.type, "__name__", str(attribute.type)),
                        "sources": (["attribute"] if is_reportable else []) + sources,
                    }
                    if capability == IAS_ZONE_CAPABILITY:
                        descriptor = capabilities[f"{endpoint_id}/{capability}"]
                        descriptor["field"] = "alarm"
                        capabilities[f"{endpoint_id}/{IAS_TAMPER_CAPABILITY}"] = {
                            **descriptor,
                            "field": "tamper",
                        }

        with self._state_lock:
            zone_types = sorted(
                (endpoint_id, zone_type)
                for (ieee, endpoint_id), zone_type in self._zone_types.items()
                if ieee == str(device.ieee)
            )

        return ZigbeeDevice(
            ieee_address=str(device.ieee),
            network_address=int(device.nwk),
            manufacturer=device.manufacturer,
            model=device.model,
            available=True,
            last_seen=(
                datetime.fromtimestamp(device.last_seen, UTC).isoformat()
                if device.last_seen
                else None
            ),
            signal_quality=device.lqi,
            capabilities=capabilities,
            zone_type=zone_types[0][1] if zone_types else None,
        )


    @staticmethod
    def _get_command_attribute_sources(cluster) -> dict[str, list[str]]:
        attributes = {
            attribute.name: attribute
            for attribute in cluster.attributes.values()
            if ZigbeeAdapter._is_sensor_attribute(attribute)
        }
        sources: dict[str, list[str]] = {}
        commands = list(cluster.server_commands.values()) + list(cluster.client_commands.values())
        for command in commands:
            for command_field in command.schema.fields:
                attribute = attributes.get(command_field.name)
                if attribute is not None and command_field.type is attribute.type:
                    sources.setdefault(command_field.name, []).append(f"command:{command.name}")

        return sources

    @staticmethod
    def _is_sensor_attribute(attribute) -> bool:
        return attribute.zcl_type.name == "bool_" or attribute.zcl_type.name.startswith("map")

    def _schedule_subscribe(self, device):
        # zigpy invokes listener callbacks synchronously on the loop thread, so async work must be scheduled
        task = asyncio.get_running_loop().create_task(self._subscribe_clusters(device))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def device_initialized(self, device):
        """Subscribe to attribute reports and, if newly joined, queue for pairing UI."""
        self._schedule_subscribe(device)

        ieee_address = str(device.ieee)
        with self._state_lock:
            self._offline_devices.discard(ieee_address)

        discovered = self._build_discovered_device(device)

        with self._pairing_lock:
            if ieee_address in self._pairing_seen:
                return

            self._pairing_seen.add(ieee_address)
            self._discovered.append(discovered)

        logger.info("Discovered Zigbee device %s", ieee_address)

    def device_reinterviewed(self, device):
        """Re-attach cluster listeners after zigpy replaces the device on re-interview."""
        self._schedule_subscribe(device)

    def device_left(self, device):
        self._mark_unavailable(str(device.ieee))

    def device_removed(self, device):
        self._mark_unavailable(str(device.ieee))

    def attribute_updated(self, cluster, attrid, value, timestamp):
        """Cluster-level callback fired by zigpy whenever a device reports a value."""
        try:
            attr_name = cluster.find_attribute(attrid).name
        except KeyError:
            attr_name = str(attrid)

        self._store_reading(cluster, attrid, attr_name, value, timestamp)

    def _store_reading(self, cluster, attrid, attr_name, value, timestamp):
        """Normalize an attribute value and publish it as the latest reading."""
        ieee_address = str(cluster.endpoint.device.ieee)
        endpoint_id = cluster.endpoint.endpoint_id
        with self._state_lock:
            if (
                int(cluster.cluster_id) == IasZone.cluster_id
                and attr_name == IasZone.AttributeDefs.zone_type.name
            ):
                if value is not None:
                    self._zone_types[(ieee_address, endpoint_id)] = int(value)
                return
            if (
                int(cluster.cluster_id) == PowerConfiguration.cluster_id
                and attr_name == PowerConfiguration.AttributeDefs.battery_percentage_remaining.name
            ):
                with contextlib.suppress(TypeError, ValueError):
                    # the ZCL attribute is reported in half percent steps
                    logger.debug(
                        "Raw battery percentage remaining for device %s: %s",
                        ieee_address,
                        value,
                    )
                    self._battery_levels[ieee_address] = min(100, int(value) // 2)

        capability = encode_capability(cluster.cluster_id, attrid)
        values = {capability: normalize_attribute_value(cluster.cluster_id, attr_name, value)}
        error_reason = None
        if capability == IAS_ZONE_CAPABILITY:
            alarm, tamper, error_reason = decode_zone_status(value)
            values = {IAS_ZONE_CAPABILITY: alarm, IAS_TAMPER_CAPABILITY: tamper}

        with self._readings_lock:
            for reading_capability, reading_value in values.items():
                self._readings[(ieee_address, endpoint_id, reading_capability)] = ZigbeeSensorData(
                    ieee_address=ieee_address,
                    endpoint=str(endpoint_id),
                    capability=reading_capability,
                    value=reading_value,
                    timestamp=timestamp.isoformat(),
                    error_reason=error_reason,
                )
            logger.debug(
                "Attribute updated for device %s, endpoint %s, capability %s: %s",
                ieee_address,
                endpoint_id,
                capability,
                value,
            )

    def cluster_command(self, cluster, tsn, command_id, args):
        """Fired for incoming ZCL commands, e.g. IAS Zone status change notifications."""
        command = getattr(args, "command", None)
        if command is None:
            command = {**cluster.server_commands, **cluster.client_commands}.get(command_id)

        command_name = command.name if command else str(command_id)
        ieee_address = str(cluster.endpoint.device.ieee)
        endpoint_id = cluster.endpoint.endpoint_id
        logger.debug(
            "Command received for device %s, endpoint %s, command %s: %s",
            ieee_address,
            endpoint_id,
            command_name,
            args,
        )

        if command is None:
            return

        attributes = {
            attribute.name: attribute
            for attribute in cluster.attributes.values()
            if self._is_sensor_attribute(attribute)
        }
        timestamp = datetime.now(UTC)
        for command_field in type(args).fields:
            attribute = attributes.get(command_field.name)
            if attribute is None or command_field.type is not attribute.type:
                continue

            self._store_reading(
                cluster, attribute.id, attribute.name, getattr(args, command_field.name), timestamp
            )

    def _mark_unavailable(self, ieee_address: str):
        with self._state_lock:
            self._offline_devices.add(ieee_address)

        with self._readings_lock:
            for key, reading in self._readings.items():
                if key[0] == ieee_address:
                    reading.available = False

    # --- Poll-facing API, safe to call from any thread ---
    def permit_joining(self, duration_seconds) -> bool:
        """Start the permit joining process for a specified duration."""
        if not self._enabled:
            logger.warning("Zigbee coordinator is disabled, joining not permitted")
            return False

        if not self._loop or not self.app:
            raise RuntimeError("Controller is not running.")

        with self._pairing_lock:
            self._pairing_seen = {str(device.ieee) for device in self.app.devices.values()}
            self._discovered.clear()

        future = asyncio.run_coroutine_threadsafe(self.app.permit(duration_seconds), self._loop)
        future.result(timeout=10.0)
        logger.info("Zigbee joining enabled for %s seconds", duration_seconds)
        return True

    def get_joined_devices(self) -> list[ZigbeeDevice]:
        """Drain devices queued by device_initialized() since the last poll."""
        with self._pairing_lock:
            devices, self._discovered = self._discovered, []
        return devices

    def unpair_device(self, ieee_address: str) -> bool:
        """Unpair the specified Zigbee device."""
        logger.info("Unpairing Zigbee device: %s", ieee_address)
        if not self._enabled:
            logger.warning("Zigbee coordinator is disabled, unpairing not possible")
            return False

        if not self._loop or not self.app:
            raise RuntimeError("Controller is not running.")

        ieee = EUI64.convert(ieee_address)
        future = asyncio.run_coroutine_threadsafe(self.app.remove(ieee), self._loop)
        future.result(timeout=10.0)
        logger.info("Zigbee device unpaired: %s", ieee_address)
        return True

    def get_device_states(self) -> list[ZigbeeDevice]:
        """Return the coordinator's current view of every known device."""
        if not self.app:
            return []

        coordinator_ieee = str(self.app.state.node_info.ieee)
        devices = []
        for device in list(self.app.devices.values()):
            ieee_address = str(device.ieee)
            if ieee_address == coordinator_ieee:
                continue

            with self._state_lock:
                available = ieee_address not in self._offline_devices
                battery_level = self._battery_levels.get(ieee_address)

            discovered = self._build_discovered_device(device)
            discovered.available = available
            discovered.battery_level = battery_level
            devices.append(discovered)

        return devices

    def get_values(self) -> list[ZigbeeSensorData]:
        with self._readings_lock:
            return list(self._readings.values())

    def get_value(self, ieee_address, endpoint, capability):
        with self._readings_lock:
            return self._readings.get((ieee_address, int(endpoint), capability))
