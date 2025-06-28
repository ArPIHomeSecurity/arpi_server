import logging
import json
import fcntl

from constants import LOG_ADSENSOR

class MockMCP3008:
    """
    Mock MCP3008 interface for simulator mode.
    Accepts channel and device (or just device), provides .value property (float 0-1).
    Reads from simulator_input.json using CH01...CH15 keys.
    """
    def __init__(self, channel=0, device=0):
        self.channel = channel
        self.device = device
        self._logger = logging.getLogger(LOG_ADSENSOR)

    @property
    def value(self):
        # Map device/channel to CHxx (same as in v3 adapter)
        # device: 0 or 1 (AD1 or AD2), channel: 0-7
        ch_index = self.device * 8 + self.channel  # 0-based index
        ch_key = f"CH{ch_index+1:02d}"
        try:
            with open("simulator_input.json", "r", encoding="utf-8") as input_file:
                fcntl.flock(input_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                channels_data = json.load(input_file)
                fcntl.flock(input_file, fcntl.LOCK_UN)
                raw_value = channels_data.get(ch_key, 0)
                # MCP3008 is 10-bit (0-1023), normalize to 0-1 float
                value = float(raw_value) / 1023.0
                self._logger.debug("MockMCP3008 value for %s: %s", ch_key, value)
                return value
        except (OSError, FileNotFoundError, json.JSONDecodeError):
            self._logger.warning("MockMCP3008: Could not read simulator_input.json, returning 0.0 for %s", ch_key)
            return 0.0

    def close(self):
        self._logger.debug("Closing MockMCP3008 instance (device=%d, channel=%d)", self.device, self.channel)
