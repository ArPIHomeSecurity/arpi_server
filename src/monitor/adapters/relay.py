
import logging
import threading

from enum import Enum
from typing import List

from monitor.adapters import (
    LATCH_PIN,
    ENABLE_PIN,
    CLOCK_PIN,
    DATA_IN_PIN,
    DATA_OUT_PIN
)
from constants import LOG_ADRELAYS

from gpiozero import DigitalOutputDevice, DigitalInputDevice


class FaultException(Exception):
    """
    Exception for faults
    """
    pass


class Commands(Enum):
    """
    DRV8860 commands
    """
    WRITE_CONTROL_REGISTER = [1, 2, 2, 3]
    READ_CONTROL_REGISTER = [1, 4, 2, 3]
    READ_DATA_REGISTER = [1, 4, 4, 3]
    RESET_FAULT_REGISTER = [1, 2, 4, 3]
    PWM_START = [1, 6, 6, 3]


class RelayAdapter:
    """
    Singleton class for controlling outputs with DRV8860
    """
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
            self._data_out = DigitalInputDevice(DATA_OUT_PIN)
            self._latch.on()
            self._enable.off()
            self._clock.off()

            faults = self._read_faults()
            if any(faults):
                self._logger.warning("Faults detected: %s", faults)
                self._write_command(*Commands.RESET_FAULT_REGISTER.value)
                faults = self._read_faults()
                if any(faults):
                    self._logger.error("Cannot reset faults: %s", faults)
                    raise FaultException("Cannot reset faults")

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

    def _read_faults(self) -> List[int]:
        self._enable.off()
        self._latch.off()
        self._clock.off()

        buffer = []
        for i in range(16):
            self._clock.on()
            self._clock.off()
            buffer.append(self._data_out.value)

        self._logger.debug("Read faults: %s", "".join([str(i) for i in buffer]))
        self._latch.on()
        self._enable.on()

        return buffer

    def _write_command(self, part1, part2, part3, part4):
        self._enable.off()
        self._latch.off()
        self._clock.off()

        for part in [part1, part2, part3, part4]:
            for _ in range(part):
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
