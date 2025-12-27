import logging

import lgpio
from gpiozero import MCP3008

from utils.constants import LOG_ADSENSOR
from monitor.adapters import V3BoardPin

from monitor.adapters.sensor_base import SensorAdapterBase


class SensorAdapter(SensorAdapterBase):
    """
    SPI/AD converter-based sensor adapter (board version 3)
    """

    def __init__(self):
        self._logger = logging.getLogger(LOG_ADSENSOR)
        # NOTE: We have two MCP3008 chips on CE0 (GPIO8) and CE1 (GPIO7)
        self._channel_map = [
            # (AD chip, AD channel)
            (1, 7), # CH01 
            (1, 6), # CH02
            (1, 5), # CH03
            (1, 4), # CH04
            (1, 3), # CH05
            (1, 2), # CH06
            (1, 1), # CH07
            (1, 0), # CH08
            (2, 7), # CH09
            (2, 6), # CH10
            (2, 5), # CH11
            (2, 4), # CH12
            (2, 3), # CH13
            (2, 2), # CH14
            (2, 1), # CH15
        ]

        self._channels = {}
        for idx, (ad_chip, ad_channel) in enumerate(self._channel_map):
            LATCH_GPIO = {1: V3BoardPin.SENSOR_LATCH_PIN_AD1, 2: V3BoardPin.SENSOR_LATCH_PIN_AD2}
            select_pin = LATCH_GPIO[ad_chip]
            try:
                self._channels[idx] = MCP3008(
                    clock_pin=V3BoardPin.SENSOR_CLOCK_PIN,
                    mosi_pin=V3BoardPin.SENSOR_MOSI_PIN,
                    miso_pin=V3BoardPin.SENSOR_MISO_PIN,
                    select_pin=select_pin,
                    channel=ad_channel
                )
            except (OSError, ValueError, RuntimeError, lgpio.error) as e:
                self._logger.error("Failed to init MCP3008 output=%s: %s", ad_chip, self._channels[idx], e)

    def is_initialized(self) -> bool:
        """
        Check if the sensor adapter is initialized properly.
        """
        return len(self._channels) == len(self._channel_map)

    def __del__(self):
        self._cleanup()

    def get_value(self, channel) -> float:
        if not (0 <= channel < len(self._channel_map)):
            self._logger.error("Invalid channel number: %s", channel)
            return 0.0

        try:
            value = self._channels.get(channel).value
        except (OSError, ValueError, RuntimeError, lgpio.error) as e:
            self._logger.error("Read error MCP3008 chip=%s ch=%s: %s", self._channel_map[channel][0], self._channel_map[channel][1], e)
            return 0.0
        else:
            # use trace (custom low level) to avoid flooding normal logs
            self._logger.trace("ADC Value[CH%02d]: %.5f", channel + 1, value)
            return value

    def get_values(self):
        return [self.get_value(i) for i in range(len(self._channel_map))]

    def _cleanup(self):
        # Explicitly close all MCP3008 channel objects to release pins promptly
        for key, channel in list(self._channels.items()):
            try:
                channel.close()
            except (OSError, ValueError, RuntimeError, lgpio.error) as e:
                self._logger.warning("Error closing channel %s: %s", key, e)

        self._channels.clear()

    @property
    def channel_count(self):
        return len(self._channel_map)
