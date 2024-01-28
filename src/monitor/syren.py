import json
import logging
import os

from threading import Thread, Event
from time import time

from models import Alert, Option
from monitor.database import Session
from monitor.socket_io import send_syren_state

from constants import LOG_ALERT, THREAD_ALERT

# check if using the simulator
if os.environ.get("USE_SIMULATOR", "false").lower() == "false":
    from monitor.adapters.output import OutputAdapter
else:
    from monitor.adapters.mock.relay import RelayAdapter


class Syren(Thread):
    """
    Handling of syren alerts.
    """

    # default config
    SILENT = False      # alarm type not silent
    DELAY = 0           # default delay 0 seconds
    STOP_TIME = 600     # default stop 10 minutes

    SYREN_RELAY_ID = 0

    _is_running = False
    _stop_event = Event()
    _alert: Alert = None

    @classmethod
    def start_syren(cls, silent=None, delay=None, stop_time=None):
        """
        Starts the syren with a configuration.

        Priority: parameters < database settings < code defaults
        """
        logging.getLogger(LOG_ALERT).debug("Starting syren...")

        db_config = Syren.load_syren_config() or {}
        config = {}
        config["silent"] = silent if silent is not None else db_config.get("silent", Syren.SILENT)
        config["delay"] = delay if delay is not None else db_config.get("delay", Syren.DELAY)
        config["stop_time"] = stop_time if stop_time is not None else db_config.get("stop_time", Syren.STOP_TIME)

        logging.getLogger(LOG_ALERT).info("Using syren config: %s )!", config)

        if not cls._is_running:
            cls._stop_event.clear()
            alert = Syren(config=config)
            alert.start()
            cls._is_running = True
        else:
            logging.getLogger(LOG_ALERT).warning("Syren is already in use!")

    @classmethod
    def stop_syren(cls):
        """
        Stops the syren.
        """
        logging.getLogger(LOG_ALERT).debug("Stopping syren...")
        cls._stop_event.set()
        cls._is_running = False
        send_syren_state(None)

    @staticmethod
    def load_syren_config():
        """
        Loads the syren configuration from the database.
        """
        _db_session = Session()
        syren_config = _db_session.query(Option).filter_by(name="syren", section="timing").first()
        if syren_config:
            syren_config = json.loads(syren_config.value)
            logging.getLogger(LOG_ALERT).debug("Loaded syren config from database: %s )!", syren_config)
            return syren_config
        else:
            logging.getLogger(LOG_ALERT).warning(
                "Missing syren settings (using defaults: %s / %s )!",
                Syren.STOP_TIME,
                Syren.DELAY,
            )

    def __init__(self, config):
        super(Syren, self).__init__(name=THREAD_ALERT)
        self._logger = logging.getLogger(LOG_ALERT)
        self._output_adapter = OutputAdapter()
        self._alert = None
        self._syren_config = config

    def get_alert(self) -> Alert:
        return self._db_session.query(Alert).filter_by(end_time=None).first()

    def run(self):
        self._db_session = Session()

        SILENT = self._syren_config["silent"]

        alert = self.get_alert()
        if alert:
            alert.silent = SILENT
            self._db_session.commit()

        if SILENT:
            self._logger.info("Syren is in silent mode")
            return

        DELAY = self._syren_config["delay"]
        STOP_TIME = self._syren_config["stop_time"]

        now = time()
        start_time = time()
        syren_is_on = (DELAY == 0)
        self._output_adapter.control_channel(self.SYREN_RELAY_ID, syren_is_on)
        send_syren_state(syren_is_on)
        while (
            not self._stop_event.is_set()
            and not self._stop_event.wait(timeout=1)
        ):
            if not syren_is_on and (now - start_time > DELAY):
                self._logger.info("Syren turned on after delay")
                # turn on the syren
                syren_is_on = True
                self._output_adapter.control_channel(self.SYREN_RELAY_ID, syren_is_on)
                send_syren_state(syren_is_on)
                self._logger.info("Syren started")
            elif syren_is_on and now - start_time > STOP_TIME:
                self._logger.info("Syren stopped after %d seconds", STOP_TIME)
                break

            now = time()

        # turn off the syren
        syren_is_on = None
        self._output_adapter.control_channel(self.SYREN_RELAY_ID, syren_is_on)
        send_syren_state(syren_is_on)
        self._logger.info("Syren stopped")

        self._logger.debug("Syren exited")
        self._db_session.close()
