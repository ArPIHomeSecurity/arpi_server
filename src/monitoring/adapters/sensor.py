# -*- coding: utf-8 -*-
# @Author: Gábor Kovács
# @Date:   2021-02-25 20:08:54
# @Last Modified by:   Gábor Kovács
# @Last Modified time: 2021-02-25 20:08:57

import os
import logging

from monitoring.adapters import SPI_CLK, SPI_MISO, SPI_MOSI
from constants import LOG_ADSENSOR

# check if running on Raspberry
if os.uname()[4][:3] == "arm":
    from gpiozero import MCP3008
else:
    # from monitoring.adapters.mock import TimeBasedMockMCP3008 as MCP3008
    from monitoring.adapters.mock.MCP3008 import DoubleAlertMCP3008 as MCP3008


class SensorAdapter(object):
    """
    Load sensor values.
    """

    SPI_CS = [12, 1]
    # number of channels on MCP3008
    CHANNEL_COUNT = 8
    # total number of channels on the board
    IO_NUMBER = int(os.environ["INPUT_NUMBER"])

    def __init__(self):
        self._channels = []
        self._logger = logging.getLogger(LOG_ADSENSOR)

        for i in range(SensorAdapter.IO_NUMBER):
            self._logger.debug(
                "Channel (index:{:2} channel:{:2}<=CH{:0>2} on BCM{:0>2} ({})) creating...".format(
                    i,
                    i % SensorAdapter.CHANNEL_COUNT,
                    i + 1,
                    SensorAdapter.SPI_CS[i // SensorAdapter.CHANNEL_COUNT],
                    MCP3008.__name__,
                )
            )
            self._channels.append(
                MCP3008(
                    channel=i % SensorAdapter.CHANNEL_COUNT,
                    clock_pin=SPI_CLK,
                    mosi_pin=SPI_MOSI,
                    miso_pin=SPI_MISO,
                    select_pin=SensorAdapter.SPI_CS[i // SensorAdapter.CHANNEL_COUNT],
                )
            )

    def get_value(self, channel):
        """Get the value from one channel"""
        if 0 <= channel <= 14:
            # !!! channel numbering correction board numbering CH1..CH15 => array 0..14
            return self._channels[channel].value
        else:
            return 0

    def get_values(self):
        """Get the values from all the channels"""
        values = []
        for channel in self._channels:
            values.append(channel.value)
        return values

    @property
    def channel_count(self):
        """Retrieve the number of the handled channels"""
        return SensorAdapter.IO_NUMBER
