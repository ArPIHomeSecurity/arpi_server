"""
Control the outputs
"""

import logging
import os
from threading import Lock

from enum import Enum
from typing import List

from monitor.adapters import LATCH_PIN, ENABLE_PIN, CLOCK_PIN, DATA_IN_PIN, DATA_OUT_PIN
from constants import LOG_ADOUTPUT

from gpiozero import DigitalOutputDevice, DigitalInputDevice

from monitor.output import OUTPUT_NAMES

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


state_lock = Lock()


class OutputAdapter():
    """
    Singleton class for controlling outputs with DRV8860
    """

    _states = [0] * int(OUTPUT_NUMBER)
    _logger = logging.getLogger(LOG_ADOUTPUT)
    _latch = DigitalOutputDevice(LATCH_PIN)
    _enable = DigitalOutputDevice(ENABLE_PIN)
    _clock = DigitalOutputDevice(CLOCK_PIN)
    _data_in = DigitalOutputDevice(DATA_IN_PIN)
    _data_out = DigitalInputDevice(DATA_OUT_PIN)

    def __init__(self):
        self._logger.debug(
            "Digital devices: %s",
            [self._latch, self._enable, self._clock, self._data_in, self._data_out],
        )
        self._latch.on()
        self._enable.off()
        self._clock.off()

        self._reset_errors()

    def _reset_errors(self):
        try:
            faults = self._read_faults()
            if any(faults):
                self._logger.warning("Faults detected: %s", faults)
                self._write_command(*Commands.RESET_FAULT_REGISTER.value)
                faults = self._read_faults()
                if any(faults):
                    self._logger.error("Cannot reset faults: %s", faults)
                    raise FaultException("Cannot reset faults")

            self._logger.debug("Successfully reset faults")
        except Exception as error:
            self._logger.error("Cannot reset faults! %s", error)

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

    def control_channel(self, channel: int, state: bool):
        """
        Control output by channel number
        """
        self._logger.debug(
            "Control channel %d for %s to %r", channel, OUTPUT_NAMES[channel], state
        )
        if channel < 0 or channel > OUTPUT_NUMBER - 1:
            raise ValueError(
                f"Channel number must be between 0 and {OUTPUT_NUMBER - 1}!"
            )

        # set the state by channel
        with state_lock:
            self._states[channel] = 1 if state else 0

        self._write_states()

    def _write_states(self):
        self._enable.off()
        self._latch.off()
        self._clock.off()
        self._data_in.off()

        for state in self._states:
            self._clock.off()
            if state:
                self._data_in.on()
            else:
                self._data_in.off()
            self._clock.on()

        self._clock.off()
        self._latch.on()
        self._enable.on()

    def _cleanup(self):
        """
        Cleanup the output adapter
        """
        if self._latch:
            self._latch.close()
            self._latch = None
        if self._enable:
            self._enable.close()
            self._enable = None
        if self._clock:
            self._clock.close()
            self._clock = None
        if self._data_in:
            self._data_in.close()
            self._data_in = None
        if self._data_out:
            self._data_out.close()
            self._data_out = None
        self._logger.debug("Output adapter cleanup finished")
