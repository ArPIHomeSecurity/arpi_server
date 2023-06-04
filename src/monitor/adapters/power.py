# -*- coding: utf-8 -*-
# @Author: Gábor Kovács
# @Date:   2021-02-25 20:09:04
# @Last Modified by:   Gábor Kovács
# @Last Modified time: 2021-02-25 20:09:05

import os
import logging

from monitor.adapters import SPI_CLK, SPI_MISO, SPI_MOSI
from constants import LOG_ADPOWER

# check if running on Raspberry
if os.environ.get("USE_SIMULATOR", "false").lower() == "false":
    from gpiozero import MCP3008
else:
    # from monitoring.adapters.mock import TimeBasedMockMCP3008 as MCP3008
    from monitor.adapters.mock.MCP3008 import Power as MCP3008


class PowerAdapter(object):
    """
    Determine the source of the power (network or battery)
    """

    SOURCE_NETWORK = "network"
    SOURCE_BATTERY = "battery"

    # MCP3008/2 chip select BCM pin
    SPI_CS = 1

    def __init__(self):
        """
        Constructor
        """
        self._sense = None
        self._logger = logging.getLogger(LOG_ADPOWER)

        self._logger.debug("Power sense on BCM1 creating...")
        # the sense is on the last channel
        self._sense = MCP3008(
            channel=7,
            clock_pin=SPI_CLK,
            mosi_pin=SPI_MOSI,
            miso_pin=SPI_MISO,
            select_pin=PowerAdapter.SPI_CS
        )

    @property
    def source_type(self):
        if self._sense.value > 0.2:
            return PowerAdapter.SOURCE_NETWORK

        return PowerAdapter.SOURCE_BATTERY
