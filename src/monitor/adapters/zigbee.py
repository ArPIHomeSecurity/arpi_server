import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from os import environ

from bellows.zigbee.application import ControllerApplication

from monitor.config.models import ZigbeeCoordinatorConfig
from monitor.database import create_database_session
from utils.constants import LOG_ADZIGBEE

USE_SIMULATOR = environ.get("USE_SIMULATOR", "false").lower() in ["true", "1", "yes"]

logger = logging.getLogger(LOG_ADZIGBEE)


@dataclass
class ZigbeeReading:
    ieee_address: str
    endpoint: str
    capability: str
    value: object
    timestamp: str | None = None
    available: bool = True
    battery_level: int | None = None
    signal_quality: int | None = None
    error_reason: str | None = None


@dataclass
class DiscoveredDevice:
    ieee_address: str
    network_address: int | None = None
    manufacturer: str | None = None
    model: str | None = None
    name: str | None = None
    metadata: dict = field(default_factory=dict)
    capabilities: dict = field(default_factory=dict)


def get_zigbee_adapter():
    """Return the simulator or real Zigbee adapter based on the runtime mode."""
    if USE_SIMULATOR:
        from monitor.adapters.mock.zigbee import ZigbeeAdapter as MockZigbeeAdapter

        return MockZigbeeAdapter()

    return ZigbeeAdapter()


class ZigbeeAdapter:
    def __init__(self):
        self._serial_port: str | None = None
        self._baudrate: int = 115200
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self.app: ControllerApplication | None = None
        self._running = False
        self._pairing_baseline: set[str] = set()
        self._reported_devices: set[str] = set()
        self._pairing_lock = threading.Lock()
        self._discovered: list[DiscoveredDevice] = []
        self._capability_lock = threading.Lock()
        self._device_info: dict[str, DiscoveredDevice] = {}
        self._capability_changes: list[DiscoveredDevice] = []
        self._readings_lock = threading.Lock()
        self._readings: dict[tuple[str, int, str], ZigbeeReading] = {}

    def start(self):
        """Start the dedicated asyncio event loop in a background thread."""
        if self._running:
            return

        with create_database_session() as db_session:
            config = ZigbeeCoordinatorConfig.load_config(session=db_session)
            self._serial_port = config.serial_port
            self._baudrate = config.baudrate

        self._thread = threading.Thread(target=self._run_event_loop, name="BellowsLoop", daemon=True)
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
        if not self._serial_port:
            raise RuntimeError("Zigbee serial port is not configured")

        config = {
            "device": {
                "path": self._serial_port,
                "baudrate": self._baudrate,
            }
        }
        self.app = await ControllerApplication.new(config, auto_form=False)
        self.app.add_listener(self)
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

    def permit_joining(self, duration_seconds) -> bool:
        """Start the permit joining process for a specified duration."""
        if not self._loop or not self.app:
            raise RuntimeError("Controller is not running.")

        with self._pairing_lock:
        self._pairing_baseline = {str(device.ieee) for device in self.app.devices.values()}
        self._reported_devices.clear()
            self._discovered.clear()
        future = asyncio.run_coroutine_threadsafe(self.app.permit(duration_seconds), self._loop)
        future.result(timeout=10.0)
        logger.info("Zigbee joining enabled for %s seconds", duration_seconds)
        return True

    def get_joined_devices(self) -> list[DiscoveredDevice]:
        """Drain devices queued by device_initialized() since the last poll."""
        with self._pairing_lock:
            devices, self._discovered = self._discovered, []
        return devices

    def get_capability_changes(self) -> list[DiscoveredDevice]:
        """Drain devices whose capabilities changed (e.g. re-interview) since the last poll."""
        with self._capability_lock:
            changes, self._capability_changes = self._capability_changes, []
        return changes

    # --- zigpy application listener callbacks, invoked from the loop thread ---

    def _subscribe_clusters(self, device):
        """Attach an attribute_updated listener to every cluster of a device."""
        for endpoint_id, endpoint in device.endpoints.items():
            if endpoint_id == 0:
                continue
            for cluster in endpoint.in_clusters.values():
                cluster.add_context_listener(self)

    def _build_discovered_device(self, device) -> DiscoveredDevice:
            capabilities = {}
            for endpoint_id, endpoint in device.endpoints.items():
                if endpoint_id == 0:
                    continue
                for cluster in endpoint.clusters:
                    capability = cluster.ep_attribute or type(cluster).__name__
                    capabilities[f"{endpoint_id}/{capability}"] = {}

        return DiscoveredDevice(
            ieee_address=str(device.ieee),
                    network_address=int(device.nwk),
                    manufacturer=device.manufacturer,
                    model=device.model,
                    metadata={
                        "available": True,
                        "signal_quality": device.lqi,
                        "last_seen": (
                            datetime.fromtimestamp(device.last_seen, UTC).isoformat()
                            if device.last_seen
                            else None
                        ),
                    },
                    capabilities=capabilities,
                )

    def device_initialized(self, device):
        """Subscribe to attribute reports and, if newly joined, queue for pairing UI."""
        self._subscribe_clusters(device)

        ieee_address = str(device.ieee)
        discovered = self._build_discovered_device(device)
        with self._capability_lock:
            self._device_info[ieee_address] = discovered

        with self._pairing_lock:
            if ieee_address in self._pairing_baseline or ieee_address in self._reported_devices:
                return
            self._reported_devices.add(ieee_address)
            self._discovered.append(discovered)
        logger.info("Discovered Zigbee device %s", ieee_address)

    def device_reinterviewed(self, device):
        """Re-attach cluster listeners and queue updated capabilities after a re-interview.

        zigpy replaces the device object on re-interview and fires this event
        instead of device_initialized, so the capability set must be recomputed here.
        """
        self._subscribe_clusters(device)

        ieee_address = str(device.ieee)
        discovered = self._build_discovered_device(device)
        with self._capability_lock:
            self._device_info[ieee_address] = discovered
            self._capability_changes.append(discovered)
        logger.info("Zigbee device %s capabilities updated", ieee_address)

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

        ieee_address = str(cluster.endpoint.device.ieee)
        endpoint_id = cluster.endpoint.endpoint_id
        capability = f"{cluster.ep_attribute or type(cluster).__name__}/{attr_name}"
        reading = ZigbeeReading(
            ieee_address=ieee_address,
            endpoint=str(endpoint_id),
            capability=capability,
            value=value,
            timestamp=timestamp.isoformat(),
            signal_quality=cluster.endpoint.device.lqi,
        )

        logger.debug(
            "Attribute updated for device %s, endpoint %s, capability %s: %s",
            ieee_address,
            endpoint_id,
            capability,
            value,
        )
        with self._readings_lock:
            self._readings[(ieee_address, endpoint_id, capability)] = reading

    def cluster_command(self, cluster, tsn, command_id, args):
        """Fired for incoming ZCL commands, e.g. IAS Zone status change notifications."""
        command = {**cluster.server_commands, **cluster.client_commands}.get(command_id)
        command_name = command.name if command else str(command_id)

        ieee_address = str(cluster.endpoint.device.ieee)
        endpoint_id = cluster.endpoint.endpoint_id
        capability = f"{cluster.ep_attribute or type(cluster).__name__}/{command_name}"
        reading = ZigbeeReading(
            ieee_address=ieee_address,
            endpoint=str(endpoint_id),
            capability=capability,
            value=args,
            timestamp=datetime.now(UTC).isoformat(),
            signal_quality=cluster.endpoint.device.lqi,
        )

        logger.debug(
            "Command received for device %s, endpoint %s, capability %s: %s",
            ieee_address,
            endpoint_id,
            capability,
            args,
        )
        with self._readings_lock:
            self._readings[(ieee_address, endpoint_id, capability)] = reading

    def _mark_unavailable(self, ieee_address: str):
        with self._readings_lock:
            for key, reading in self._readings.items():
                if key[0] == ieee_address:
                    reading.available = False

    # --- Poll-facing API, safe to call from any thread ---

    def get_values(self) -> list[ZigbeeReading]:
        with self._readings_lock:
            return list(self._readings.values())

    def get_value(self, ieee_address, endpoint, capability):
        with self._readings_lock:
            return self._readings.get((ieee_address, int(endpoint), capability))

    def send_raw_command(self, node_id: int, cluster_id: int, data: bytes):
        """Example placeholder for dispatching an async request safely."""

        async def _async_send():
            # Access underlying EZSP driver frame sender safely inside the loop
            # e.g., await self.app._ezsp.send_unicast(...)
            return None

        if self._loop is None or self.app is None:
            return None
        future = asyncio.run_coroutine_threadsafe(_async_send(), self._loop)
        return future.result(timeout=5.0)
