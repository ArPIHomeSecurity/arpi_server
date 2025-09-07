import logging

from gpiozero import DigitalInputDevice

from constants import LOG_ADSENSOR
from monitor.adapters.sensor_base import SensorAdapterBase

# Input channel pins
CH01_PIN = 19
CH02_PIN = 20
CH03_PIN = 26
CH04_PIN = 21
CH05_PIN = 12
CH06_PIN = 6
CH07_PIN = 13
CH08_PIN = 16
CH09_PIN = 7
CH10_PIN = 1
CH11_PIN = 0
CH12_PIN = 5
CH13_PIN = 23
CH14_PIN = 24
CH15_PIN = 25

CHANNEL_GPIO_PINS = [
    CH01_PIN,
    CH02_PIN,
    CH03_PIN,
    CH04_PIN,
    CH05_PIN,
    CH06_PIN,
    CH07_PIN,
    CH08_PIN,
    CH09_PIN,
    CH10_PIN,
    CH11_PIN,
    CH12_PIN,
    CH13_PIN,
    CH14_PIN,
    CH15_PIN,
]

class SensorAdapterV2(SensorAdapterBase):
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
