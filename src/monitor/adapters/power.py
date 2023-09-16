# -*- coding: utf-8 -*-
# @Author: Gábor Kovács
# @Date:   2021-02-25 20:09:04
# @Last Modified by:   Gábor Kovács
# @Last Modified time: 2021-02-25 20:09:05

import os
import logging

from monitor.adapters import POWER_PIN
from constants import LOG_ADPOWER

# check if running on Raspberry
if os.environ.get("USE_SIMULATOR", "false").lower() == "false":
    from gpiozero import DigitalInputDevice
else:
    # from monitoring.adapters.mock import TimeBasedMockMCP3008 as MCP3008
    from monitor.adapters.mock.MCP3008 import Power as DigitalInputDevice


class PowerAdapter(object):
    """
    Determine the source of the power (network or battery)
    """

    SOURCE_NETWORK = "network"
    SOURCE_BATTERY = "battery"

    def __init__(self):
        """
        Constructor
        """
        self._sense = None
        self._logger = logging.getLogger(LOG_ADPOWER)

        self._logger.debug("Power sense creating...")
        # the sense is on the last channel
        self._sense = DigitalInputDevice(POWER_PIN)

    @property
    def source_type(self):
        if self._sense.value:
            return PowerAdapter.SOURCE_NETWORK

        return PowerAdapter.SOURCE_BATTERY
