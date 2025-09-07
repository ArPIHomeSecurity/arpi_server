import logging
import json
import fcntl

from constants import LOG_ADSENSOR
from monitor.adapters.sensor_base import SensorAdapterBase


class SensorAdapter(SensorAdapterBase):
    """
    Mock MCP3008 interface for simulator mode.
    Accepts channel and device (or just device), provides .value property (float 0-1).
    Reads from simulator_input.json using CH01...CH15 keys.
    """

    def __init__(self):
        self._logger = logging.getLogger(LOG_ADSENSOR)
        self._logger.debug("Mock SensorAdapter initialized")

    def get_values(self):
        return [self.get_value(channel) for channel in range(self.channel_count)]

    def get_value(self, channel):
        ch_key = f"CH{channel + 1:02d}"
        try:
            with open("simulator_input.json", "r", encoding="utf-8") as input_file:
                fcntl.flock(input_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                channels_data = json.load(input_file)
                fcntl.flock(input_file, fcntl.LOCK_UN)
                raw_value = channels_data.get(ch_key, 0)
                self._logger.debug("Value for %s: %s", ch_key, raw_value)
                return raw_value
        except (OSError, FileNotFoundError, json.JSONDecodeError):
            self._logger.warning(
                "Could not read simulator_input.json, returning 0.0 for %s", ch_key
            )
            return 0.0

    @property
    def channel_count(self):
        return 8

    def close(self):
        self._logger.debug("Mock SensorAdapter closed")
