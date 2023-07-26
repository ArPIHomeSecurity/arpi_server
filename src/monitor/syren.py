import json
import logging

from threading import Thread, Event
from time import time

from models import Alert, Option
from monitor.adapters.syren import SyrenAdapter
from monitor.database import Session
from monitor.socket_io import send_syren_state

from constants import LOG_ALERT, THREAD_ALERT


class Syren(Thread):
    """
    Handling of syren alerts.
    """

    # default config
    SILENT = False      # never
    DELAY = 0           # 5 seconds
    STOP_TIME = 600     # 10 seconds

    _is_running = False
    _stop_event = Event()
    _alert: Alert = None

    @classmethod
    def start_syren(cls):
        logging.getLogger(LOG_ALERT).debug("Starting syren...")
        if not cls._is_running:
            cls._stop_event.clear()
            alert = Syren()
            alert.start()
            cls._is_running = True

    @classmethod
    def stop_syren(cls):
        logging.getLogger(LOG_ALERT).debug("Stopping syren...")
        cls._stop_event.set()
        cls._is_running = False
        send_syren_state(None)

    def __init__(self):
        super(Syren, self).__init__(name=THREAD_ALERT)
        self._logger = logging.getLogger(LOG_ALERT)
        self._syren = SyrenAdapter()
        self._alert = None
        self._syren_config = {}

    def get_alert(self) -> Alert:
        return self._db_session.query(Alert).filter_by(end_time=None).first()

    def run(self):
        self._db_session = Session()

        self.load_syren_config()
        SILENT = self._syren_config.get("silent", Syren.SILENT)

        alert = self.get_alert()
        if alert:
            alert.silent = SILENT
            self._db_session.commit()

        if SILENT:
            self._logger.info("Syren is in silent mode")
            return

        DELAY = self._syren_config.get("delay", Syren.DELAY)
        STOP_TIME = self._syren_config.get("stop_time", Syren.STOP_TIME)

        now = time()
        start_time = time()
        syren_is_on = False
        self._syren.alert(syren_is_on)
        send_syren_state(syren_is_on)
        while (
            not self._stop_event.is_set()
            and not self._stop_event.wait(timeout=1)
        ):
            if not syren_is_on and (now - start_time > DELAY):
                self._logger.info("Syren turned on after delay")
                # turn on the syren
                syren_is_on = True
                self._syren.alert(syren_is_on)
                send_syren_state(syren_is_on)
                self._logger.info("Syren started")
            elif syren_is_on and now - start_time > STOP_TIME:
                self._logger.info("Syren stopped after time")
                break

            now = time()

        # turn off the syren
        syren_is_on = None
        self._syren.alert(syren_is_on)
        send_syren_state(syren_is_on)
        self._logger.info("Syren stopped")

        self._logger.debug("Syren exited")

    def load_syren_config(self):
        syren_config = self._db_session.query(Option).filter_by(name="syren", section="timing").first()
        if syren_config:
            self._syren_config = json.loads(syren_config.value)
            self._logger.info("Using syren config: %s )!", self._syren_config)
        else:
            self._logger.warning(
                "Missing syren settings (using defaults: %s / %s )!",
                Syren.STOP_TIME,
                Syren.DELAY,
            )
            return
