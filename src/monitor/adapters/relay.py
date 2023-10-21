
import logging
import threading

from monitor.adapters import (
    LATCH_PIN,
    ENABLE_PIN,
    CLOCK_PIN,
    DATA_IN_PIN
)
from constants import LOG_ADRELAYS

from gpiozero import DigitalOutputDevice


class RelayAdapter:
    _instance = None
    _lock = threading.Lock()
    _states = [0, 0, 0, 0, 0, 0, 0, 0]

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls, *args, **kwargs)
                cls._instance.setup()
        return cls._instance

    def __init__(self):
        pass

    def setup(self):
        self._logger = logging.getLogger(LOG_ADRELAYS)
        try:
            self._latch = DigitalOutputDevice(LATCH_PIN)
            self._enable = DigitalOutputDevice(ENABLE_PIN)
            self._clock = DigitalOutputDevice(CLOCK_PIN)
            self._data_in = DigitalOutputDevice(DATA_IN_PIN)
            # self._data_out = DigitalOutputDevice(DATA_OUT_PIN)
            self._latch.on()
            self._enable.off()
            self._clock.off()
            self._logger.debug("Relay adapter setup finished")
        except Exception as error:
            self._logger.error("Cannot setup relay adapter! %s", error)

    def control_relay(self, relay_number: int, state: bool):
        """
        Control relay by number
        """
        # set the relay number position in states array
        self._states[relay_number] = 1 if state else 0
        self._logger.debug("Control relay %d to %d, %s",
                           relay_number,
                           state,
                           self._states
                           )
        self._write_states()

    def _write_states(self):
        self._enable.off()
        self._latch.off()
        self._clock.off()

        for state in self._states:
            self._data_in.value = state
            self._clock.on()
            self._clock.off()

        self._latch.on()
        self._enable.on()

    def cleanup(self):
        self._latch.close()
        self._enable.close()
        self._clock.close()
        self._data_in.close()
        # self._data_out.close()
        self._logger.debug("Relay adapter cleanup finished")

    def __del__(self):
        self.cleanup()
