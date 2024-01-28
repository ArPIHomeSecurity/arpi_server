"""
Control the outputs
"""

import logging
import os
import threading

from enum import Enum
from typing import List

from monitor.adapters import LATCH_PIN, ENABLE_PIN, CLOCK_PIN, DATA_IN_PIN, DATA_OUT_PIN
from constants import LOG_ADOUTPUT

from gpiozero import DigitalOutputDevice, DigitalInputDevice

OUTPUT_NUMBER = int(os.environ.get("OUTPUT_NUMBER", 8))


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


class OutputAdapter:
    """
    Singleton class for controlling outputs with DRV8860
    """

    _instance = None
    _lock = threading.Lock()
    _states = [0] * OUTPUT_NUMBER

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls, *args, **kwargs)
                cls._instance.setup()
        return cls._instance

    def __init__(self):
        self._latch = None
        self._enable = None
        self._clock = None
        self._data_in = None
        self._data_out = None
        self._logger = None

    def setup(self):
        self._logger = logging.getLogger(LOG_ADOUTPUT)
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

            self._logger.debug("Output adapter setup finished")
        except Exception as error:
            self._logger.error("Cannot setup output adapter! %s", error)

    def control_channel(self, channel: int, state: bool):
        """
        Control output by channel number
        """
        if channel < 0 or channel > OUTPUT_NUMBER - 1:
            raise ValueError(
                f"Channel number must be between 0 and {OUTPUT_NUMBER - 1}!"
            )

        # set the state by channel
        self._states[channel] = 1 if state else 0
        self._logger.debug("Control channel %d to %d, %s", channel, state, self._states)
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
        self._logger.debug("Output adapter cleanup finished")

    def __del__(self):
        self.cleanup()
