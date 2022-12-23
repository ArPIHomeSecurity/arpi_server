import logging

from constants import LOG_ADSYREN


class Output(object):
    def __init__(self, pin):
        self._pin = pin
        self._logger = logging.getLogger(LOG_ADSYREN)

    def on(self):
        self._logger.debug("Pin(%s) ON", self._pin)

    def off(self):
        self._logger.debug("Pin(%s) OFF", self._pin)
