import asyncio
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from os import environ

from bellows.zigbee.application import ControllerApplication
from zigpy.application import ControllerApplication as ZigpyControllerApplication
from zigpy.device import Device
from zigpy.exceptions import ZigbeeException
from zigpy.types import EUI64
from zigpy.zcl import Cluster
from zigpy.zcl.clusters.security import IasZone

from monitor.config.helper import load_config
from monitor.config.models import ZigbeeCoordinatorConfig
from utils.constants import LOG_ADZIGBEE
from utils.zigbee import (
    ZIGBEE_ATTRIBUTE_REGISTRY,
    decode_zigbee_attribute,
    describe_zigbee_signals,
)

USE_ZIGBEE_SIMULATOR = environ.get("USE_ZIGBEE_SIMULATOR", "false").lower() in ["true", "1", "yes"]

logger = logging.getLogger(LOG_ADZIGBEE)


@dataclass
class ZigbeeSensorData:
    ieee_address: str
    endpoint: str
    cluster_id: int
    attribute_id: int
    field: str | None
    value: object
    timestamp: str | None = None


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
    signals: list[dict] = field(default_factory=list)


def get_zigbee_adapter():
    """Return the simulator or real Zigbee adapter based on the runtime mode."""
    if USE_ZIGBEE_SIMULATOR:
        from monitor.adapters.mock.zigbee import ZigbeeAdapter as MockZigbeeAdapter

        logger.debug("Using mock Zigbee adapter")
        return MockZigbeeAdapter()

    return ZigbeeAdapter()


class ZigbeeAdapter:
    """
    A class to manage the Zigbee coordinator for device communication.
    """

    def __init__(self):
        self._enabled = False
        self._serial_port: str | None = None
        self._baudrate: int = 115200
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._app: ZigpyControllerApplication | None = None
        self._running = False

        self._pairing_lock = threading.Lock()
        self._pairing_seen: set[str] = set()
        self._discovered: list[ZigbeeDevice] = []

        self._readings_lock = threading.Lock()
        self._readings: dict[tuple[str, str, int, int, str | None], ZigbeeSensorData] = {}

        self._state_lock = threading.Lock()
        self._battery_levels: dict[str, int] = {}
        self._last_seen: dict[str, str] = {}
        self._signal_qualities: dict[str, int] = {}
        self._metadata_listeners: set[str] = set()
        self._offline_devices: set[str] = set()
        self._zone_types: dict[tuple[str, int], int] = {}

        self._tasks: set[asyncio.Task] = set()

    def start(self):
        """Start the dedicated asyncio event loop in a background thread."""
        if self._running:
            return

        config = load_config(ZigbeeCoordinatorConfig)
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
                "Zigbee serial port %s does not exist, coordinator not started", self._serial_port
            )
            self._enabled = False
            return

        self._thread = threading.Thread(
            target=self._run_event_loop, name="BellowsLoop", daemon=True
        )
        self._thread.start()

        while self._app is None and self._running:
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
        self._app = await ControllerApplication.new(config, auto_form=False)
        self._app.add_listener(self)

        # devices restored from the zigpy database do not emit device_initialized
        for device in list(self._app.devices.values()):
            if str(device.ieee) == str(self._app.state.node_info.ieee):
                continue
            self._register_device_metadata_listener(device)
            await self._subscribe_clusters(device)
        logger.info("Bellows radio initialized")

    def stop(self):
        """Thread-safe shutdown sequence."""
        if self._app is None or self._loop is None:
            self._running = False
            return

        if self._loop.is_running():
            future = asyncio.run_coroutine_threadsafe(self._app.shutdown(), self._loop)
            future.result(timeout=5.0)
            self._loop.call_soon_threadsafe(self._loop.stop)
        self._running = False

    # --- zigpy application listener callbacks, invoked from the loop thread ---
    def device_initialized(self, device: Device):
        """
        Callback invoked by zigpy when a new device is paired or restored from the database.
        Schedule the subscription to attribute reports on the event loop thread.
        """
        self._register_device_metadata_listener(device)
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

    def device_reinterviewed(self, device: Device):
        """
        Callback invoked by zigpy when a device has been re-interviewed after a reset or rejoin.
        """
        self._register_device_metadata_listener(device)
        self._schedule_subscribe(device)

    def _register_device_metadata_listener(self, device: Device):
        ieee_address = str(device.ieee)
        with self._state_lock:
            if ieee_address in self._metadata_listeners:
                return

            self._metadata_listeners.add(ieee_address)
            if device.last_seen:
                self._last_seen[ieee_address] = datetime.fromtimestamp(
                    device.last_seen, UTC
                ).isoformat()
            if device.lqi is not None:
                self._signal_qualities[ieee_address] = device.lqi

        device.add_context_listener(self)

    def device_last_seen_updated(self, device: Device, last_seen: datetime | None):
        """Refresh packet metadata after zigpy has updated the device's LQI."""
        asyncio.get_running_loop().call_soon(self._update_device_metadata, device, last_seen)

    def _update_device_metadata(self, device: Device, last_seen: datetime | None):
        ieee_address = str(device.ieee)
        with self._state_lock:
            if last_seen is not None:
                self._last_seen[ieee_address] = last_seen.isoformat()
            if device.lqi is not None:
                self._signal_qualities[ieee_address] = device.lqi

    def device_left(self, device: Device):
        """
        Callback invoked by zigpy when a device has been removed from the network.
        """
        self._mark_unavailable(str(device.ieee))

    def device_removed(self, device: Device):
        """
        Callback invoked by zigpy when a device has been removed from the network.
        """
        self._mark_unavailable(str(device.ieee))

    def attribute_updated(self, cluster, attrid, value, timestamp):
        """
        Cluster-level callback fired by zigpy whenever a device reports a value.
        This is the main entry point for receiving sensor readings from devices.
        """
        self._store_reading(cluster, attrid, value, timestamp)

    def cluster_command(self, cluster: Cluster, _tsn, command_id, args) -> None:
        """
        Callback invoked by zigpy when a cluster command is received.
        This is used to handle IAS Zone status notifications, which are sent
        as commands rather than attribute reports.
        """
        definitions = ZIGBEE_ATTRIBUTE_REGISTRY.get(int(cluster.cluster_id), ())
        definition = None
        for d in definitions:
            if any(command.id == int(command_id) for command in d.commands):
                definition = d
                break

        if definition is None:
            return

        ieee_address = str(cluster.endpoint.device.ieee)
        endpoint_id = cluster.endpoint.endpoint_id
        logger.debug(
            "IAS Zone status notification received for device %s, endpoint %s: %s",
            ieee_address,
            endpoint_id,
            args,
        )

        timestamp = datetime.now(UTC)
        attribute = cluster.find_attribute(definition.attribute_id)
        self._store_reading(
            cluster,
            definition.attribute_id,
            getattr(args, attribute.name),
            timestamp,
        )

    # --- Zigbee cluster subscription and attribute handling ---
    async def _subscribe_clusters(self, device: Device):
        """
        Subscribe to attribute reports for all clusters on the device.
        This is called when a device is first paired or restored from the zigpy database.
        """
        logger.debug("Subscribing to clusters for device %s", device.ieee)
        for endpoint_id, endpoint in device.endpoints.items():
            if endpoint_id == 0:
                continue

            for cluster in endpoint.in_clusters.values():
                # check for a registered attribute definition for this cluster
                cluster_id = int(cluster.cluster_id)
                definitions = ZIGBEE_ATTRIBUTE_REGISTRY.get(cluster_id, ())
                if not definitions:
                    continue

                # attach a listener to the cluster
                # so that attribute updates are reported to this adapter
                cluster.add_context_listener(self)
                for definition in definitions:
                    attribute = cluster.find_attribute(definition.attribute_id)
                    if definition.reporting is not None:
                        await self._setup_reporting(
                            cluster,
                            attribute.name,
                            definition.reporting[0],
                            definition.reporting[1],
                        )
                    else:
                        cached_value = cluster.get(definition.attribute_id)
                        if cached_value is not None:
                            self._store_reading(
                                cluster,
                                definition.attribute_id,
                                cached_value,
                                datetime.now(UTC),
                            )
                        await self._read_attribute(cluster, attribute.name)

    async def _setup_reporting(
        self,
        cluster: Cluster,
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

    async def _read_attribute(self, cluster: Cluster, attribute: str):
        ieee_address = str(cluster.endpoint.device.ieee)
        try:
            success, _ = await cluster.read_attributes([attribute])
        except (ZigbeeException, TimeoutError):
            logger.info("Failed to read %s of device %s", attribute, ieee_address)
            return

        # zigpy suppresses the attribute_updated listener for read responses
        attribute_def = cluster.find_attribute(attribute)
        for value in success.values():
            self._store_reading(cluster, attribute_def.id, value, datetime.now(UTC))

    def _build_discovered_device(self, device: Device) -> ZigbeeDevice:
        signals = []
        for endpoint_id, endpoint in device.endpoints.items():
            if endpoint_id == 0:
                continue

            for cluster in endpoint.in_clusters.values():
                signals.extend(describe_zigbee_signals(cluster, endpoint_id))

        ieee_address = str(device.ieee)
        with self._state_lock:
            zone_types = {
                endpoint_id: zone_type
                for (ieee, endpoint_id), zone_type in self._zone_types.items()
                if ieee == ieee_address
            }
            last_seen = self._last_seen.get(ieee_address)
            signal_quality = self._signal_qualities.get(ieee_address)

        for signal in signals:
            if int(signal["clusterId"]) == int(IasZone.cluster_id):
                zone_type = zone_types.get(int(signal["endpoint"]))
                if zone_type is not None:
                    signal["zoneType"] = zone_type

        return ZigbeeDevice(
            ieee_address=str(device.ieee),
            network_address=int(device.nwk),
            manufacturer=device.manufacturer,
            model=device.model,
            available=True,
            last_seen=last_seen,
            signal_quality=signal_quality,
            signals=signals,
        )

    def _schedule_subscribe(self, device: Device):
        """
        Schedule the subscription to attribute reports on the event loop thread.
        This is necessary because zigpy invokes listener callbacks synchronously on the loop thread,
        so any async work must be scheduled to run on the loop thread.
        """
        task = asyncio.get_running_loop().create_task(self._subscribe_clusters(device))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _store_reading(self, cluster: Cluster, attrid: int, value, timestamp: datetime):
        """Normalize an attribute value and publish it as the latest reading."""
        definitions = ZIGBEE_ATTRIBUTE_REGISTRY.get(int(cluster.cluster_id), ())

        # Find the attribute definition for the given attribute ID
        definition = next((d for d in definitions if d.attribute_id == attrid), None)
        if definition is None:
            return

        ieee_address = str(cluster.endpoint.device.ieee)
        endpoint_id = cluster.endpoint.endpoint_id
        decoded = decode_zigbee_attribute(definition, value)
        if decoded.device_state is not None:
            state_name, state_value = decoded.device_state
            with self._state_lock:
                if state_name == "zone_type":
                    self._zone_types[(ieee_address, endpoint_id)] = state_value
                elif state_name == "battery_level":
                    self._battery_levels[ieee_address] = state_value
            if not decoded.signals:
                return

        if not decoded.signals:
            return

        with self._readings_lock:
            for signal, reading_value in decoded.signals:
                self._readings[
                    (
                        ieee_address,
                        str(endpoint_id),
                        int(cluster.cluster_id),
                        int(attrid),
                        signal.field,
                    )
                ] = ZigbeeSensorData(
                    ieee_address=ieee_address,
                    endpoint=str(endpoint_id),
                    cluster_id=int(cluster.cluster_id),
                    attribute_id=int(attrid),
                    field=signal.field,
                    value=reading_value,
                    timestamp=timestamp.isoformat(),
                )
            logger.debug(
                "Attribute updated for device %s, endpoint %s, signal %s: %s",
                ieee_address,
                endpoint_id,
                decoded.signals[0][0].field or "attribute",
                value,
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
        """
        Start the permit joining process for a specified duration.
        Returns True if joining was successfully enabled, False otherwise.
        """
        if not self._enabled:
            logger.warning("Zigbee coordinator is disabled, joining not permitted")
            return False

        if not self._loop or not self._app:
            logger.warning("Zigbee coordinator is not running, joining not permitted")
            return False

        with self._pairing_lock:
            self._pairing_seen = {str(device.ieee) for device in self._app.devices.values()}
            self._discovered.clear()

        future = asyncio.run_coroutine_threadsafe(self._app.permit(duration_seconds), self._loop)
        future.result(timeout=10.0)
        logger.info("Zigbee joining enabled for %s seconds", duration_seconds)
        return True

    def get_joined_devices(self) -> list[ZigbeeDevice]:
        """
        Drain devices queued by device_initialized() since the last poll.
        """
        with self._pairing_lock:
            devices, self._discovered = self._discovered, []
        return devices

    def unpair_device(self, ieee_address: str) -> bool:
        """
        Unpair the specified Zigbee device.
        Returns True if unpairing was successful, False otherwise.
        """
        logger.info("Unpairing Zigbee device: %s", ieee_address)
        if not self._enabled:
            logger.warning("Zigbee coordinator is disabled, unpairing not possible")
            return False

        if not self._loop or not self._app:
            logger.warning("Zigbee coordinator is not running, unpairing not possible")
            return False

        ieee = EUI64.convert(ieee_address)
        future = asyncio.run_coroutine_threadsafe(self._app.remove(ieee), self._loop)
        future.result(timeout=10.0)
        logger.info("Zigbee device unpaired: %s", ieee_address)
        return True

    def get_device_states(self) -> list[ZigbeeDevice]:
        """
        Return the coordinator's current view of every known device.
        This includes devices that are currently offline or unavailable.
        """
        if not self._app:
            return []

        coordinator_ieee = str(self._app.state.node_info.ieee)
        devices = []
        for device in list(self._app.devices.values()):
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

    def get_value(self, ieee_address, endpoint, cluster_id, attribute_id, signal_field=None):
        with self._readings_lock:
            return self._readings.get(
                (
                    str(ieee_address),
                    str(endpoint),
                    int(cluster_id),
                    int(attribute_id),
                    signal_field,
                )
            )
