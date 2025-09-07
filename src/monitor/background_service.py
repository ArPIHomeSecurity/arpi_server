# create a thread which monitors the health of the threads
import logging

from threading import Thread, Event
from time import sleep, time

from constants import LOG_SERVICE, MONITOR_STOP
from monitor.broadcast import Broadcaster
from monitor.ipc import IPCServer
from monitor.keypad_handler import KeypadHandler
from monitor.monitor import Monitor
from monitor.notifications.notifier import Notifier
from monitor.logging import print_logging
from monitor.output.handler import OutputHandler


MAX_RETRIES = 3
CRASH_TIMEOUT = 120


class BackgroundService(Thread):
    """
    The main background service of the application which monitors the health of the threads
    and restarts them if necessary.
    """
    def __init__(self, stop_event: Event):
        super().__init__(name="HealthCheck")
        self._threads: list = None
        self._stop_event = stop_event
        self._broadcaster: Broadcaster = None
        self._logger = logging.getLogger(LOG_SERVICE)

    def run(self):
        """
        The thread checks the health of the other threads
        and stops the application if any problem happens.
        If the application stops the service running system has to restart it clearly.
        """

        self._start_threads()
        retries = 0
        last_crash = None

        while not self._stop_event.wait(timeout=1):
            # print the logging configuration for debugging
            # print_logging()

            self._logger.trace("Health check of threads: %s", [t.name for t in self._threads])
            for thread in self._threads:
                if not thread.is_alive():
                    self._logger.error("Thread crashed: %s", thread.name)
                    last_crash = time()
                    retries += 1
                    if retries > MAX_RETRIES:
                        self._logger.error("Too many retries. Stopping the application.")
                        return

                    self._stop_threads()
                    sleep(1)
                    self._start_threads()
                    break

            # reset the retries if the last crash was a long time ago
            if last_crash and time() - last_crash > CRASH_TIMEOUT:
                retries = 0
                last_crash = None

        if retries < MAX_RETRIES:
            self._stop_threads()

        self._logger.info("Health checker stopped")

    def _start_threads(self):
        self._logger.info("Starting threads...")
        self._stop_event.clear()
        self._broadcaster = Broadcaster()
        monitor = Monitor(self._broadcaster)
        monitor.start()

        notifier = Notifier(self._broadcaster)
        notifier.start()

        output_handler = OutputHandler(broadcaster=self._broadcaster)
        output_handler.start()

        keypad = KeypadHandler(self._broadcaster)
        keypad.start()

        ipc_server = IPCServer(self._stop_event, self._broadcaster)
        ipc_server.start()

        self._threads = [monitor, ipc_server, notifier, output_handler, keypad]

    def _stop_threads(self):
        self._logger.info("Stopping threads...")
        self._broadcaster.send_message(message={"action": MONITOR_STOP})
        self._stop_event.set()

        # wait for all threads to stop
        for thread in self._threads or []:
            self._logger.debug("Waiting for thread to stop: %s %s", thread.name, thread.is_alive())
            if thread.is_alive():
                thread.join()
            self._logger.info("Stopped thread: %s", thread.name)
            thread = None

        self._threads = None
