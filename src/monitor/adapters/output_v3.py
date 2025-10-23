""" """

from enum import Enum
import logging
import os
from threading import Lock
from time import sleep
from typing import List

import lgpio
from constants import LOG_ADOUTPUT
from gpiozero import DigitalOutputDevice, DigitalInputDevice

from monitor.output import OUTPUT_NAMES

OUTPUT_NUMBER = int(os.environ.get("OUTPUT_NUMBER", 8))


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


class OutputAdapter:
    """
    Class for controlling outputs with DRV8860
    """

    FAULT_REGISTER_SIZE = 16
    DATA_REGISTER_SIZE = 8

    def __init__(
        self, latch_pin=None, enable_pin=None, clock_pin=None, data_in_pin=None, data_out_pin=None
    ):
        self._logger = logging.getLogger(LOG_ADOUTPUT)
        if OutputAdapter.DATA_REGISTER_SIZE != OUTPUT_NUMBER:
            raise ValueError(
                f"Data register size {OutputAdapter.DATA_REGISTER_SIZE} does not match output number {OUTPUT_NUMBER}"
            )
        self._states = [0] * OUTPUT_NUMBER

        # Allow pins to be set after instantiation (for get_output_adapter)
        try:
            self._latch = DigitalOutputDevice(latch_pin)
            self._enable = DigitalOutputDevice(enable_pin)
            self._clock = DigitalOutputDevice(clock_pin)
            self._data_in = DigitalInputDevice(data_in_pin)
            self._data_out = DigitalOutputDevice(data_out_pin)
        except lgpio.error as error:
            self._latch = None
            self._enable = None
            self._clock = None
            self._data_in = None
            self._data_out = None
            self._logger.error(f"Error initializing digital devices: {error}")

        if all([self._latch, self._enable, self._clock, self._data_in, self._data_out]):
            self._logger.debug(
                "Digital devices: %s",
                [self._latch, self._enable, self._clock, self._data_in, self._data_out],
            )
            self._latch.on()
            self._enable.off()
            self._clock.off()
            self._reset_faults()
            self._enable.on()

    def is_initialized(self) -> bool:
        return all([self._latch, self._enable, self._clock, self._data_in, self._data_out])

    def __del__(self):
        with state_lock:
            if self.is_initialized():
                self._states = [0] * OUTPUT_NUMBER
                self._write_states()
                self._read_states()
                self._reset_faults()
                self._read_faults()
                self._cleanup()

    @property
    def states(self):
        return self._states

    def _reset_faults(self):
        faults = self._read_faults()
        if any(faults):
            self._logger.debug("Resetting faults")
            self._write_command(*Commands.RESET_FAULT_REGISTER.value)

            faults = self._read_faults()
            if any(faults):
                self._logger.error("Failed to reset faults")
                return

        self._logger.debug("Successfully reset faults")

    def _read_faults(self) -> List[int]:
        self._latch.off()
        self._clock.off()
        sleep(0.001)  # small delay to allow data to stabilize
        self._latch.on()

        buffer: List[int] = []
        for _ in range(OutputAdapter.FAULT_REGISTER_SIZE):
            self._clock.on()
            sleep(0.001)  # small delay to allow data to stabilize
            self._clock.off()
            sleep(0.001)  # small delay to allow data to stabilize
            buffer.append(self._data_in.value)

        # bits are in reverse order F16 -> F1
        buffer = list(reversed(buffer))
        if any(buffer):
            self._logger.debug(
                "Read faults: %s", ", ".join(f"F{idx + 1}: {bit}" for idx, bit in enumerate(buffer))
            )
            self._logger.debug("OCP=Overcurrent Detection, OLP=Open Load Protection")
            self._logger.warning(
                "Read faults: %s",
                ", ".join(
                    f"OUTP{idx + 1:02d}/{OUTPUT_NAMES[idx]}: {'OLP' if buffer[idx] else '-'}|{'OCP' if buffer[idx + 8] else '-'}"
                    for idx in range(OUTPUT_NUMBER)
                ),
            )
        else:
            self._logger.debug("No faults detected")

        self._latch.on()

        return buffer

    def _write_command(self, part1, part2, part3, part4):
        self._clock.off()
        self._latch.off()

        for idx, part in enumerate([part1, part2, part3, part4]):
            for _ in range(part):
                # send control bits
                sleep(0.001)
                self._clock.on()
                self._clock.off()

            # start next frame
            sleep(0.001)
            self._latch.on()
            if idx < 3:
                self._latch.off()

        self._latch.on()

    def control_channel(self, channel: int, state: bool):
        """
        Control output by channel number
        """
        self._logger.debug(
            "Control channel %d for %s to %r",
            channel,
            OUTPUT_NAMES[channel],
            "ON" if state else "OFF",
        )
        if channel < 0 or channel > OUTPUT_NUMBER - 1:
            raise ValueError(f"Channel number must be between 0 and {OUTPUT_NUMBER - 1}!")

        # set the state by channel
        with state_lock:
            if self.is_initialized():
                self._states[channel] = 1 if state else 0
                self._write_states()
                self._read_states()
                self._read_faults()

    def _write_states(self):
        self._latch.off()
        self._clock.off()

        # send bits in reverse order
        for state in reversed(self._states):
            self._clock.off()
            if state:
                self._data_out.on()
            else:
                self._data_out.off()
            self._clock.on()
            sleep(0.001)  # small delay to allow data to stabilize

        self._latch.on()

    def _read_states(self) -> List[int]:
        self._write_command(*Commands.READ_DATA_REGISTER.value)

        self._latch.on()
        buffer: List[int] = []
        for _ in range(OutputAdapter.DATA_REGISTER_SIZE):
            self._clock.on()
            sleep(0.001)
            buffer.append(self._data_in.value)
            self._clock.off()
            sleep(0.001)

        # bits are in reverse order OUT8 -> OUT1
        self._logger.debug("States:  %s", list(reversed(buffer)))
        return buffer

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
