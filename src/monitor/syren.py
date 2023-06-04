import json
import logging

from threading import Thread, Event
from time import time

from models import Alert, Option
from monitor.adapters.syren import SyrenAdapter
from monitor.database import Session
from monitor.socket_io import send_syren_state

from constants import (
    LOG_ALERT,
    THREAD_ALERT
)


class Syren(Thread):
    """
    Handling of syren alerts.
    """

    # default timing
    ALERT_TIME = 10  # 10 minutes
    SUSPEND_TIME = 5  # 5 minutes

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

    def run(self):
        self.load_syren_config()

        start_time = time()
        syren_is_on = True
        self._syren.alert(syren_is_on)
        send_syren_state(syren_is_on)

        while not self._stop_event.is_set() and not self._stop_event.wait(timeout=1):
            now = time()
            if (now - start_time > self._syren_config.get("alert_time", Syren.ALERT_TIME)) and syren_is_on:
                start_time = time()
                syren_is_on = False
                self._syren.alert(syren_is_on)
                send_syren_state(syren_is_on)
                self._logger.info("Syren suspended")
            elif (now - start_time > self._syren_config.get("suspend_time", Syren.SUSPEND_TIME)) and not syren_is_on:
                start_time = time()
                syren_is_on = True
                self._syren.alert(syren_is_on)
                send_syren_state(syren_is_on)
                self._logger.info("Syren started")

        self._logger.debug("Syren exited")

    def load_syren_config(self):
        db_session = Session()
        syren_config = db_session.query(Option).filter_by(name="syren", section="timing").first()
        if syren_config:
            self._syren_config = json.loads(syren_config.value)
            self._logger.warn("Using syren config: %s )!", self._syren_config)
        else:
            self._logger.warn("Missing syren settings (using defaults: %s / %s )!",
                              Syren.ALERT_TIME,
                              Syren.SUSPEND_TIME)
            return
