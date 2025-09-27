import logging

from gpiozero import DigitalInputDevice

from constants import LOG_ADSENSOR
from monitor.adapters.sensor_base import SensorAdapterBase
from monitor.adapters import V2BoardPin

CHANNEL_GPIO_PINS = [
    V2BoardPin.CH01_PIN,
    V2BoardPin.CH02_PIN,
    V2BoardPin.CH03_PIN,
    V2BoardPin.CH04_PIN,
    V2BoardPin.CH05_PIN,
    V2BoardPin.CH06_PIN,
    V2BoardPin.CH07_PIN,
    V2BoardPin.CH08_PIN,
    V2BoardPin.CH09_PIN,
    V2BoardPin.CH10_PIN,
    V2BoardPin.CH11_PIN,
    V2BoardPin.CH12_PIN,
    V2BoardPin.CH13_PIN,
    V2BoardPin.CH14_PIN,
    V2BoardPin.CH15_PIN,
]

class SensorAdapter(SensorAdapterBase):
    """
    GPIO-based sensor adapter (board version 2)
    """
    def __init__(self):
        self._logger = logging.getLogger(LOG_ADSENSOR)
        self._channels = []
        for pin in CHANNEL_GPIO_PINS:
            self._logger.debug("Creating sensor adapter for GPIO pin: %s", pin)
            self._channels.append(DigitalInputDevice(pin, pull_up=False))

    def __del__(self):
        self._cleanup()

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

    def _cleanup(self):
        for channel in self._channels:
            channel.close()

    @property
    def channel_count(self):
        return len(self._channels)
