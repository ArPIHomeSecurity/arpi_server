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

    def __init__(self, clock_pin, mosi_pin, miso_pin, cs_pin, channel):
        self.clock_pin = clock_pin
        self.mosi_pin = mosi_pin
        self.miso_pin = miso_pin
        self.cs_pin = cs_pin
        self.channel = channel
        self._logger = logging.getLogger(LOG_ADSENSOR)
        self._logger.trace(
            "MockMCP3008 initialized (clock_pin=%d, mosi_pin=%d, miso_pin=%d, cs_pin=%d)",
            clock_pin,
            mosi_pin,
            miso_pin,
            cs_pin,
        )

    @property
    def value(self):
        # Map device/channel to CHxx (same as in v3 adapter)
        # device: 0 or 1 (AD1 or AD2), channel: 0-7
        device = 0  # Default to AD1
        if self.cs_pin == 8:  # AD1
            device = 0
        elif self.cs_pin == 7:  # AD2
            device = 1

        ch_index = device * 8 + self.channel  # 0-based index
        ch_key = f"CH{ch_index + 1:02d}"
        try:
            with open("simulator_input.json", "r", encoding="utf-8") as input_file:
                fcntl.flock(input_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                channels_data = json.load(input_file)
                fcntl.flock(input_file, fcntl.LOCK_UN)
                raw_value = channels_data.get(ch_key, 0)
                self._logger.debug("MockMCP3008 value for %s: %s", ch_key, raw_value)
                return raw_value
        except (OSError, FileNotFoundError, json.JSONDecodeError):
            self._logger.warning(
                "MockMCP3008: Could not read simulator_input.json, returning 0.0 for %s", ch_key
            )
            return 0.0

    def close(self):
        self._logger.debug(
            "Closing MockMCP3008 instance (cs_pin=%d, channel=%d)", self.cs_pin, self.channel
        )
