import logging
import os

from time import sleep, time

from monitoring.adapters.keypads.base import Function, KeypadBase
from constants import LOG_ADKEYPAD


class MockKeypad(KeypadBase):

    # ACTIONS = "1234    1111      9876   65       C0C1"
    # ACTIONS = "                                    C1"
    # ACTIONS = "                                                            1234"
    ACTIONS = "                                                                  A"
    # ACTIONS = " "
    CARDS = [
        "305419896",  # 12:34:56:78   <== C0
        "272625547",  # 10:3F:EF:8B   <== C1
    ]

    def __init__(self, clock_pin, data_pin):
        super(MockKeypad, self).__init__()
        self._logger = logging.getLogger(LOG_ADKEYPAD)
        self._armed = False
        self._error = False
        self._ready = False
        self._index = 0
        self._start = time()

    def initialise(self):
        self._logger.debug("Keypad initialized")

    def beeps(self, count, beep, mute):
        for _ in range(count):
            os.system(f"play -nq -t alsa synth {beep} sine 1340")
            sleep(mute)

    def set_armed(self, state):
        self._armed = state
        self._logger.debug("Armed: %s", state)
        self.beeps(2, 0.1, 0.1)

    def set_error(self, state):
        self._error = state
        self._logger.debug("Error: %s", state)
        self.beeps(3, 0.1, 0.1)

    def set_ready(self, state):
        self._ready = state
        self._logger.debug("Ready: %s", state)

    def communicate(self):
        self._logger.debug("Start communication MOCK...")
        # start 10 seconds after the start
        if time() - self._start > 10 and self._index is None:
            self._index = 0

        self.manage_delay()

        if self._index is not None:
            if self.ACTIONS[self._index] == 'C':
                self._card = self.CARDS[int(self.ACTIONS[self._index+1])]
                self._index += 1
            elif self.ACTIONS[self._index] == 'A':
                self._logger.debug("Function: %s", self.ACTIONS[self._index])
                self._function = Function.AWAY
                self.ACTIONS = " "
                # avoid repeating the test action
            elif self.ACTIONS[self._index] == 'S':
                self._logger.debug("Function: %s", self.ACTIONS[self._index])
                self._function = Function.STAY
                self.ACTIONS = " "
                # avoid repeating the test action
            elif self.ACTIONS[self._index] != ' ':
                self._logger.debug("Pressed: %s", self.ACTIONS[self._index])
                self._keys.append(self.ACTIONS[self._index])

            self._index += 1
            if self._index >= len(self.ACTIONS):
                self._index = 0
