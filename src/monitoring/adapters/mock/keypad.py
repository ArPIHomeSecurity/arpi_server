# -*- coding: utf-8 -*-
# @Author: Gábor Kovács
# @Date:   2021-02-25 20:09:51
# @Last Modified by:   Gábor Kovács
# @Last Modified time: 2021-02-25 20:09:51

import logging
from time import time

from monitoring.adapters.keypads.base import KeypadBase
from monitoring.constants import LOG_ADKEYPAD


class MockKeypad(KeypadBase):

    CODES = "1234    1111      9876   65        "

    def __init__(self, clock_pin, data_pin):
        super(MockKeypad, self).__init__(clock_pin, data_pin)
        self._logger = logging.getLogger(LOG_ADKEYPAD)
        self._armed = False
        self._error = False
        self._ready = False
        self._index = None
        self._start = time()

    def initialise(self):
        self._logger.debug("Keypad initialised")

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

        if time() - self._start > 10 and self._index is None:
            self._index = 0

        if self._index is not None:
            self.pressed = self.CODES[self._index]
            self._index += 1

        if self._index == len(self.CODES):
            self._index = None
