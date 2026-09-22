import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
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

    def start(self):
        """Start the dedicated asyncio event loop in a background thread."""
        if self._running:
            return

        with create_database_session() as db_session:
            config = ZigbeeCoordinatorConfig.load_config(session=db_session)
            self._serial_port = config.serial_port
            self._baudrate = config.baudrate

        self._thread = threading.Thread(target=self._run_event_loop, daemon=True)
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
                "flow_control": "hardware",
            }
        }
        self.app = await ControllerApplication.new(config, auto_form=False)
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

        future = asyncio.run_coroutine_threadsafe(self.app.permit(duration_seconds), self._loop)
        return bool(future.result(timeout=10.0))

    def get_joined_devices(self) -> list[DiscoveredDevice]:
        return []

    def get_values(self) -> list[ZigbeeReading]:
        return []

    def get_value(self, ieee_address, endpoint, capability):
        return None

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
