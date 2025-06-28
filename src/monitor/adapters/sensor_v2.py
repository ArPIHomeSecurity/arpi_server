import logging
from monitor.adapters import CHANNEL_GPIO_PINS
from constants import LOG_ADSENSOR
import os

# check if running with simulator
if os.environ.get("USE_SIMULATOR", "false").lower() == "false":
    from gpiozero import DigitalInputDevice
else:
    from monitor.adapters.mock.input import Channels as DigitalInputDevice

from .sensor_base import BaseSensorAdapter

class SensorAdapterV2(BaseSensorAdapter):
    """
    GPIO-based sensor adapter (board version 2)
    """
    def __init__(self):
        self._logger = logging.getLogger(LOG_ADSENSOR)
        self._channels = []
        for pin in CHANNEL_GPIO_PINS:
            self._logger.debug("Creating sensor adapter for GPIO pin: %s", pin)
            self._channels.append(DigitalInputDevice(pin, pull_up=False))

    def get_value(self, channel):
        if not (0 <= channel <= (len(CHANNEL_GPIO_PINS) - 1)):
            self._logger.error("Invalid channel number: %s", channel)
            return 0
        value = int(self._channels[channel].value)
        self._logger.trace("Value[CH%02d]: %s", channel+1, value)
        return value

    def get_values(self):
        values = [int(channel.value) for channel in self._channels]
        self._logger.debug("Values: %s", [f"{v}" for v in values])
        return values

    def close(self):
        for channel in self._channels:
            channel.close()

    @property
    def channel_count(self):
        return len(self._channels)
