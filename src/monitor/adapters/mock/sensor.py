import logging
from os import environ

from utils.constants import LOG_ADSENSOR
from monitor.adapters.sensor_base import SensorAdapterBase
from monitor.adapters.mock.utils import get_input_state


class SensorAdapter(SensorAdapterBase):
    """
    Mock MCP3008 interface for simulator mode.
    Accepts channel and device (or just device), provides .value property (float 0-1).
    Reads from simulator_input.json using CH01...CH15 keys.
    """

    def __init__(self):
        self._logger = logging.getLogger(LOG_ADSENSOR)
        self._logger.debug("Mock SensorAdapter initialized")

    def is_initialized(self) -> bool:
        return True

    def get_values(self):
        return [self.get_value(channel) for channel in range(self.channel_count)]

    def get_value(self, channel):
        ch_key = f"CH{channel + 1:02d}"
        return get_input_state(ch_key)

    @property
    def channel_count(self):
        return int(environ.get("INPUT_NUMBER", 8))

    def close(self):
        self._logger.debug("Mock SensorAdapter closed")
