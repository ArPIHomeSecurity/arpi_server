import os
import logging

from monitoring.adapters import SPI_CLK, SPI_MISO, SPI_MOSI
from constants import LOG_ADSENSOR

# check if running on Raspberry
if os.environ.get("USE_SIMULATOR", "false").lower() == "false":
    from gpiozero import MCP3008
else:
    # from monitoring.adapters.mock import TimeBasedMockMCP3008 as MCP3008
    from monitoring.adapters.mock.MCP3008 import Channels as MCP3008


class SensorAdapter(object):
    """
    Load sensor values.
    """

    SPI_CHIP_SELECT = [12, 1]
    # number of channels on MCP3008
    MCP3008_CHANNEL_COUNT = 8
    # total number of channels on the board
    INPUT_CHANNELS_NUMBER = int(os.environ["INPUT_NUMBER"])

    def __init__(self):
        self._channels = []
        self._logger = logging.getLogger(LOG_ADSENSOR)

        for i in range(SensorAdapter.INPUT_CHANNELS_NUMBER):
            self._logger.debug(
                "Channel (index:{:2} channel:{:2}<=CH{:0>2} on BCM{:0>2} ({})) creating...".format(
                    i,
                    i % SensorAdapter.MCP3008_CHANNEL_COUNT,
                    i + 1,
                    SensorAdapter.SPI_CHIP_SELECT[i // SensorAdapter.MCP3008_CHANNEL_COUNT],
                    MCP3008.__name__,
                )
            )
            self._channels.append(
                MCP3008(
                    channel=i % SensorAdapter.MCP3008_CHANNEL_COUNT,
                    clock_pin=SPI_CLK,
                    mosi_pin=SPI_MOSI,
                    miso_pin=SPI_MISO,
                    select_pin=SensorAdapter.SPI_CHIP_SELECT[i // SensorAdapter.MCP3008_CHANNEL_COUNT],
                )
            )

    def get_value(self, channel):
        """
        Get the value from one channel

        We have IO_NUMBER of channels we can use for sensors,
        the last channel is for sensing the battery mode.
        """
        self._logger.debug("Value[%s]: %.4f", channel, self._channels[channel].value)
        return self._channels[channel].value if 0 <= channel <= (self.INPUT_CHANNELS_NUMBER - 1) else 0

    def get_values(self):
        """
        Get the values from all the channels
        """
        values = [channel.value for channel in self._channels]
        self._logger.debug("Values: %s", [f"{v:.4f}" for v in values])
        return values

    @property
    def channel_count(self):
        """Retrieve the number of the handled channels"""
        return SensorAdapter.INPUT_CHANNELS_NUMBER
