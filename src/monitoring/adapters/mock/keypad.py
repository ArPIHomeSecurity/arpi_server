# -*- coding: utf-8 -*-
# @Author: Gábor Kovács
# @Date:   2021-02-25 20:09:51
# @Last Modified by:   Gábor Kovács
# @Last Modified time: 2021-02-25 20:09:51

import logging
from time import time

from monitoring.adapters.keypads.base import Action, KeypadBase
from monitoring.constants import LOG_ADKEYPAD


class MockKeypad(KeypadBase):

    # ACTIONS = "1234    1111      9876   65       C0C1"
    ACTIONS = "                                  C1"
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
        self._index = None
        self._start = time()

    def initialise(self):
        self._logger.debug("Keypad initialised")

    def get_card(self):
        card = self._card
        self._card = None
        return card

    def get_function(self):
        pass

    def last_action(self) -> Action:
        if self._card is not None:
            return Action.CARD
        elif self._keys:
            return Action.KEY

    def set_armed(self, state):
        self._armed = state
        self._logger.debug("Armed: %s", state)

    def set_error(self, state):
        self._error = state
        self._logger.debug("Error: %s", state)

    def set_ready(self, state):
        self._ready = state
        self._logger.debug("Ready: %s", state)

    def communicate(self):
        self._logger.debug("Start communication MOCK...")

        # start 10 seconds after the start
        if time() - self._start > 10 and self._index is None:
            self._index = 0

        if self._index is not None:
            if self.ACTIONS[self._index] == 'C':
                self._card = self.CARDS[int(self.ACTIONS[self._index+1])]
                self._index += 1
            elif self.ACTIONS[self._index] != ' ':
                self._logger.debug("Pressed: %s", self.ACTIONS[self._index])
                self._keys.append(self.ACTIONS[self._index])

            self._index += 1
            if self._index == len(self.ACTIONS):
                self._index = None
