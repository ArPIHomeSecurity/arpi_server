import os
import logging

from monitor.adapters import CHANNEL_GPIO_PINS
from constants import LOG_ADSENSOR

# check if running with simulator
if os.environ.get("USE_SIMULATOR", "false").lower() == "false":
    from gpiozero import DigitalInputDevice
else:
    # from monitoring.adapters.mock import TimeBasedMockMCP3008 as MCP3008
    from monitor.adapters.mock.input import Channels as DigitalInputDevice


class SensorAdapter(object):
    """
    Load sensor values.
    """

    def __init__(self):
        self._logger = logging.getLogger(LOG_ADSENSOR)

        self._channels = []
        for pin in CHANNEL_GPIO_PINS:
            self._logger.debug("Creating sensor adapter for GPIO pin: %s", pin)
            self._channels.append(DigitalInputDevice(pin, pull_up=False))

    def get_value(self, channel):
        """
        Get the value from one channel

        We have IO_NUMBER of channels we can use for sensors,
        the last channel is for sensing the battery mode.
        """
        if not (0 <= channel <= (len(CHANNEL_GPIO_PINS) - 1)):
            self._logger.error("Invalid channel number: %s", channel)
            return 0

        value = int(self._channels[channel].value)
        self._logger.trace("Value[CH%02d]: %s", channel+1, value)
        return value

    def get_values(self):
        """
        Get the values from all the channels
        """
        values = [int(channel.value) for channel in self._channels]
        self._logger.debug("Values: %s", [f"{v}" for v in values])
        return values

    def close(self):
        """
        Close all the channels.
        """
        for channel in self._channels:
            channel.close()

    @property
    def channel_count(self):
        """Retrieve the number of the handled channels"""
        return len(self._channels)
