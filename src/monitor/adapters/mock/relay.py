
import logging

from constants import LOG_ADRELAYS


class RelayAdapter:
    _states = [0, 0, 0, 0, 0, 0, 0, 0]

    def __init__(self):
        self._logger = logging.getLogger(LOG_ADRELAYS)

    def setup(self):
        self._logger.debug("Relay adapter setup finished")

    def control_relay(self, relay_number, state):
        # set the relay number position in states array
        self._logger.debug("Control relay %d to %d, %s",
                           relay_number,
                           state,
                           self._states
                           )

    def cleanup(self):
        self._logger.debug("Relay adapter cleanup finished")

    def __del__(self):
        self.cleanup()
