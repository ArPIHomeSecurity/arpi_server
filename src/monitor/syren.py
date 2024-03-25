import logging
import os

from threading import Thread, Event
from time import time

from models import Alert
from monitor.config_helper import SyrenConfig, load_syren_config
from monitor.database import Session
from monitor.socket_io import send_syren_state

from constants import LOG_ALERT, THREAD_ALERT

# check if using the simulator
if os.environ.get("USE_SIMULATOR", "false").lower() == "false":
    from monitor.adapters.output import OutputAdapter
else:
    from monitor.adapters.mock.output import OutputAdapter


class Syren(Thread):
    """
    Handling of syren alerts.
    """

    # default config
    SILENT = False  # alarm type not silent
    DELAY = 0  # default delay 0 seconds
    STOP_TIME = 0  # default stop never

    SYREN_CHANNEL = 0

    _is_running = False
    _stop_event = Event()
    _alert: Alert = None

    @classmethod
    def start_syren(cls, silent=None, delay=None, stop_time=None):
        """
        Starts the syren with a configuration.

        Priority: parameters < database settings < code defaults
        """
        logger = logging.getLogger(LOG_ALERT)
        logger.debug("Starting syren...")

        config = load_syren_config()
        if config is None:
            logging.info("Missing ssh settings!")
            config = SyrenConfig(cls.SILENT, cls.DELAY, cls.STOP_TIME)

        if silent is not None:
            config.silent = silent
        if delay is not None:
            config.delay = delay
        if stop_time is not None:
            config.stop_time = stop_time

        logger.info("Using syren config: %s )!", config)

        if not cls._is_running:
            cls._stop_event.clear()
            alert = Syren(config=config)
            alert.start()
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

    def __init__(self, config: SyrenConfig):
        super(Syren, self).__init__(name=THREAD_ALERT)
        self._logger = logging.getLogger(LOG_ALERT)
        self._output_adapter = OutputAdapter()
        self._alert = None
        self._config = config

    def run(self):
        db_session = Session()
        alert = db_session.query(Alert).filter_by(end_time=None).first()

        # We need to decide if the syren should be silent or not.

        # The inputs are the syren configuration and the sensors configuration.
        # Both can have 3 state:
        # * None: no information, use the syren as default behavior
        # * False: loud mode, force using syren (higher priority)
        # * True: silent mode, allow not using syren
        sensor_silent_alert = None
        for sensor in alert.sensors:
            if sensor.silent is None:
                continue
            if sensor.silent == False:
                sensor_silent_alert = False
                break
            if sensor.silent == True:
                sensor_silent_alert = sensor_silent_alert and True if sensor_silent_alert is not None else True

        syren_silent_alert = self._config.silent

        silent_alert = False
        if syren_silent_alert == None:
            # use sensor configuration if no syren configuration
            # if no sensor configuration, use default silent=False
            silent_alert = (
                sensor_silent_alert if sensor_silent_alert is not None else False
            )
        elif syren_silent_alert == False:
            # force using syren
            silent_alert = False
        elif syren_silent_alert == True:
            # use syren configuration if sensor configuration is not set
            # otherwise use sensor configuration
            # sensor silent=False will override syren silent=True
            silent_alert = (
                sensor_silent_alert if sensor_silent_alert is not None else True
            )

        if alert:
            alert.silent = silent_alert
            db_session.commit()

        self._logger.info(
            "Silent alert = %s <= Syren silent = %s, Sensor silent = %s",
            silent_alert,
            syren_silent_alert,
            sensor_silent_alert,
        )
        if silent_alert:
            self._logger.info("Syren is in silent mode")
            send_syren_state(False)
            Syren._is_running = False
            return

        DELAY = self._config.delay
        STOP_TIME = self._config.stop_time

        start_time = time()
        syren_is_on = DELAY == 0
        self._output_adapter.control_channel(self.SYREN_CHANNEL, syren_is_on)
        send_syren_state(syren_is_on)
        if syren_is_on:
            self._logger.info("Syren started")
        while not self._stop_event.is_set():
            now = time()
            if not syren_is_on and (now - start_time > DELAY):
                self._logger.info("Syren turned on after delay")
                # turn on the syren
                syren_is_on = True
                self._output_adapter.control_channel(self.SYREN_CHANNEL, syren_is_on)
                send_syren_state(syren_is_on)
                self._logger.info("Syren started")
            elif syren_is_on and STOP_TIME > 0 and now - start_time > STOP_TIME:
                self._logger.info("Syren stopped after %d seconds", STOP_TIME)
                break

            if self._stop_event.wait(timeout=1):
                break

        # turn off the syren
        syren_is_on = None
        self._output_adapter.control_channel(self.SYREN_CHANNEL, False)
        send_syren_state(syren_is_on)
        self._logger.info("Syren stopped")

        self._logger.debug("Syren exited")
        db_session.close()
