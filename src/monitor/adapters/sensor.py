import os
import logging

from monitor.adapters import CHANNEL_GPIO_PINS
from constants import LOG_ADSENSOR

# check if running on Raspberry
if os.environ.get("USE_SIMULATOR", "false").lower() == "false":
    from gpiozero import LED
else:
    # from monitoring.adapters.mock import TimeBasedMockMCP3008 as MCP3008
    from monitor.adapters.mock.MCP3008 import Channels as LED


class SensorAdapter(object):
    """
    Load sensor values.
    """

    def __init__(self):
        self._logger = logging.getLogger(LOG_ADSENSOR)

        self._channels = [LED(pin) for pin in CHANNEL_GPIO_PINS]
        self._logger.debug("Created sensor adapter for GPIO pins: %s", CHANNEL_GPIO_PINS)

    def get_value(self, channel):
        """
        Get the value from one channel

        We have IO_NUMBER of channels we can use for sensors,
        the last channel is for sensing the battery mode.
        """
        if not (0 <= channel <= (len(CHANNEL_GPIO_PINS) - 1)):
            self._logger.error("Invalid channel number: %s", channel)
            return 0

        value = 1 if self._channels[channel].is_pressed else 0
        self._logger.debug("Value[CH%02d]: %s", channel+1, value)
        return value

    def get_values(self):
        """
        Get the values from all the channels
        """
        values = [1 if channel.value else 0 for channel in self._channels]
        self._logger.debug("Values: %s", [f"{v}" for v in values])
        return values

    @property
    def channel_count(self):
        """Retrieve the number of the handled channels"""
        return len(self._channels)
