import logging
import os

from constants import LOG_ADRELAYS

# check if running on Raspberry
if os.environ.get("USE_SIMULATOR", "false").lower() == "false":
    from monitor.adapters.relay import RelayAdapter
else:
    from monitor.adapters.mock.relay import RelayAdapter


class SyrenAdapter(object):
    """
    SyrenAdapter class for controlling the syren 
    """
    RELAY_ID = 0

    def __init__(self):
        """
        Constructor
        """
        self._channels = []
        self._logger = logging.getLogger(LOG_ADRELAYS)
        self._is_alerting = False
        self._relayAdapter = RelayAdapter()

    def alert(self, start=True):
        if start:
            self._logger.info("Syren on")
            self._is_alerting = True
            self._relayAdapter.control_relay(self.RELAY_ID, 1)
        elif not start:
            self._logger.info("Syren off")
            self._is_alerting = False
            self._relayAdapter.control_relay(self.RELAY_ID, 0)
        elif start is not None:
            self._logger.error("Syren invalid state")

    @property
    def is_alerting(self):
        return self._is_alerting
