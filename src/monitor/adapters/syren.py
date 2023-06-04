# -*- coding: utf-8 -*-
# @Author: Gábor Kovács
# @Date:   2021-02-25 20:08:45
# @Last Modified by:   Gábor Kovács
# @Last Modified time: 2021-02-25 20:08:46

import logging
import os

from monitor.adapters import SYREN_OUT
from constants import LOG_ADSYREN

# check if running on Raspberry
if os.environ.get("USE_SIMULATOR", "false").lower() == "false":
    from gpiozero.output_devices import DigitalOutputDevice
else:
    from monitor.adapters.mock.output import Output as DigitalOutputDevice


class SyrenAdapter(object):
    """
    classdocs
    """

    def __init__(self):
        """
        Constructor
        """
        self._channels = []
        self._logger = logging.getLogger(LOG_ADSYREN)
        self._is_alerting = False
        self._output = DigitalOutputDevice(pin=SYREN_OUT)

    def alert(self, start=True):
        if start:
            self._logger.info("Syren on")
            self._is_alerting = True
            self._output.on()
        else:
            self._logger.info("Syren off")
            self._is_alerting = False
            self._output.off()

    @property
    def is_alerting(self):
        return self._is_alerting
