import asyncio
import logging
import threading
import time
from os import environ

from bellows.zigbee.application import ControllerApplication

from monitor.config.models import ZigbeeCoordinatorConfig
from monitor.database import create_database_session
from utils.constants import LOG_ADZIGBEE

USE_SIMULATOR = environ.get("USE_SIMULATOR", "false").lower() in ["true", "1", "yes"]


logger = logging.getLogger(LOG_ADZIGBEE)


def get_zigbee_adapter():
    """Return the simulator or real Zigbee adapter based on the runtime mode."""
    if USE_SIMULATOR:
        from monitor.adapters.mock.zigbee import ZigbeeAdapter as MockZigbeeAdapter

        return MockZigbeeAdapter()

    return ZigbeeAdapter()


class ZigbeeAdapter:
    def __init__(self):
        self._serial_port_path: str = ""
        self._baudrate: int = 0

        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self.app: ControllerApplication | None = None
        self._running = False

    def start(self):
        """Starts the dedicated asyncio event loop in a background thread."""

        with create_database_session() as db_session:
            config = ZigbeeCoordinatorConfig().load_config(session=db_session)
            self._serial_port_path = config.serial_port_path
            self._baudrate = config.baudrate
        self._thread = threading.Thread(target=self._run_event_loop, daemon=True)
        self._thread.start()

        # Wait until the event loop and bellows application are fully initialized
        while self.app is None and self._running:
            time.sleep(0.05)

    def _run_event_loop(self):
        """Worker function running on the background thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._running = True

        # Run async initialization inside this thread's loop
        self._loop.run_until_complete(self._async_init())

        # Keep loop running indefinitely to handle serial I/O & events
        try:
            self._loop.run_forever()
        finally:
            self._loop.close()

    async def _async_init(self):
        """Asynchronous initialization of the bellows radio."""
        config = {
            "device": {
                "path": self._serial_port_path,
                "baudrate": self._baudrate,
                "flow_control": "hardware",
            }
        }
        # Initialize radio controller
        self.app = await ControllerApplication.new(config, auto_form=False)
        print(f"[Thread {threading.get_ident()}] Bellows radio initialized.")

    def stop(self):
        """Thread-safe shutdown sequence."""
        if self._loop and self._loop.is_running():
            # Submit async shutdown to loop thread
            future = asyncio.run_coroutine_threadsafe(self.app.shutdown(), self._loop)
            future.result(timeout=5.0)  # Block caller thread until completed

            # Stop the loop
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._running = False

    def permit_joining(self, duration_seconds: int = 60) -> bool:
        """
        Start the permit joining process for a specified duration.

        Returns True if successful, False otherwise.
        """
        if not self._loop or not self.app:
            raise RuntimeError("Controller is not running.")

        # Schedule the async method on the event loop thread and block for result
        future = asyncio.run_coroutine_threadsafe(self.app.permit(duration_seconds), self._loop)

        # Block calling thread until operation finishes (or times out)
        return future.result(timeout=10.0)

    def send_raw_command(self, node_id: int, cluster_id: int, data: bytes):
        """Example placeholder for dispatching an async request safely."""

        async def _async_send():
            # Access underlying EZSP driver frame sender safely inside the loop
            # e.g., await self.app._ezsp.send_unicast(...)
            pass

        future = asyncio.run_coroutine_threadsafe(_async_send(), self._loop)
        return future.result(timeout=5.0)
