import logging
from threading import Event, Thread
from time import time

from monitor.adapters.output import get_output_adapter
from monitor.socket_io import send_syren_state
from utils.constants import LOG_ALERT, THREAD_ALERT

logger = logging.getLogger(LOG_ALERT)


class Syren(Thread):
    """
    Handling of syren alerts.
    """

    # default config
    SILENT = False  # alarm type not silent
    DELAY = 0  # default delay 0 seconds
    DURATION = 0  # default stop never

    SYREN_CHANNEL = 0

    _is_running = False
    _stop_event = Event()

    @classmethod
    def start_syren(cls, silent=None, delay=None, duration=None):
        """
        Starts the syren using resolved parameters.
        """
        logger = logging.getLogger(LOG_ALERT)
        logger.debug("Starting syren...")

        resolved_silent = cls.SILENT if silent is None else silent
        resolved_delay = cls.DELAY if delay is None else delay
        resolved_duration = cls.DURATION if duration is None else duration

        logger.info(
            "Using resolved syren settings: silent=%s, delay=%s, duration=%s",
            resolved_silent,
            resolved_delay,
            resolved_duration,
        )

        if not cls._is_running:
            cls._stop_event.clear()
            syren = Syren(
                silent=resolved_silent,
                delay=resolved_delay,
                duration=resolved_duration,
            )
            syren.start()
            cls._is_running = True
        else:
            logger.warning("Syren is already in use!")

    @classmethod
    def stop_syren(cls):
        """
        Stops the syren.
        """
        logging.getLogger(LOG_ALERT).debug("Stopping syren...")
        cls._stop_event.set()
        cls._is_running = False
        send_syren_state(None)

    def __init__(self, silent: bool, delay: int, duration: int):
        super().__init__(name=THREAD_ALERT)
        self._output_adapter = get_output_adapter()
        self._silent = silent
        self._delay = delay
        self._duration = duration

    def run(self):
        if self._silent:
            logger.info("Syren is in silent mode")
            send_syren_state(False)
            Syren._is_running = False
            return

        delay = self._delay
        duration = self._duration

        start_time = time()
        syren_is_on = delay == 0
        self._output_adapter.control_channel(self.SYREN_CHANNEL, syren_is_on)
        send_syren_state(syren_is_on)
        if syren_is_on:
            logger.info("Syren started")
        while not self._stop_event.is_set():
            now = time()
            if not syren_is_on and (now - start_time > delay):
                logger.info("Syren turned on after delay")
                # turn on the syren
                syren_is_on = True
                self._output_adapter.control_channel(self.SYREN_CHANNEL, syren_is_on)
                send_syren_state(syren_is_on)
                logger.info("Syren started")
            elif syren_is_on and duration > 0 and now - start_time > duration:
                logger.info("Syren stopped after %d seconds", duration)
                break

            if self._stop_event.wait(timeout=1):
                break

        # turn off the syren
        syren_is_on = None
        self._output_adapter.control_channel(self.SYREN_CHANNEL, False)
        send_syren_state(syren_is_on)
        logger.info("Syren stopped")

        logger.debug("Syren exited")
