# create a thread which monitors the health of the threads
import logging
import sys

from threading import Thread

from constants import LOG_SERVICE, MONITOR_STOP
from monitor.broadcast import Broadcaster
from monitor.ipc import IPCServer
from monitor.adapters.keypad import KeypadHandler
from monitor.monitor import Monitor
from monitor.notifications.notifier import Notifier
from monitor.logging import print_logging


logger = logging.getLogger(LOG_SERVICE)


class BackgroundService(Thread):
    def __init__(self, stop_event):
        super().__init__(name="HealthCheck")
        self._threads = None
        self._stop_service = stop_event
        self._broadcaster = None
        self._logger = logging.getLogger(LOG_SERVICE)

    def run(self):
        """
        The thread checks the health of the other threads
        and stops the application if any problem happens.
        If the application stops the service running system has to restart it clearly.
        """

        self._start_threads()

        while not self._stop_service.wait(timeout=1):
            print_logging()

            self._logger.debug("Health check of threads: %s", [t.name for t in self._threads])
            for thread in self._threads:
                if not thread.is_alive():
                    self._logger.error("Thread crashed: %s", thread.name)
                    # restart the threads
                    self._stop_threads()
                    self._start_threads()
                    break

        self._stop_threads()
        logger.info("Health checker stopped")
        sys.exit(0)

    def _start_threads(self):
        self._logger.info("Starting threads...")
        self._stop_service.clear()
        self._broadcaster = Broadcaster()
        monitor = Monitor(self._broadcaster)
        monitor.start()

        notifier = Notifier(self._broadcaster)
        notifier.start()

        keypad = KeypadHandler(self._broadcaster)
        keypad.start()

        ipc_server = IPCServer(self._stop_service, self._broadcaster)
        ipc_server.start()

        self._threads = (monitor, ipc_server, notifier, keypad)

    def _stop_threads(self):
        self._logger.info("Stopping threads...")
        self._broadcaster.send_message(message={"action": MONITOR_STOP})
        self._stop_service.set()

        # wait for all threads to stop
        for thread in self._threads:
            self._logger.debug("Stopping thread: %s", thread.name)
            thread.join()
            self._logger.info("Stopped thread: %s", thread.name)
