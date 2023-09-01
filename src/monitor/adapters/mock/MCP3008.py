# -*- coding: utf-8 -*-
# @Author: Gábor Kovács
# @Date:   2021-02-25 20:09:45
# @Last Modified by:   Gábor Kovács
# @Last Modified time: 2021-02-25 20:09:47

import json
import logging
import threading

from time import time
from constants import LOG_ADSENSOR


class TimeBasedMockMCP3008(object):
    CHANGE_TIME = 11
    DEFAULT_VALUE = 0.1

    def __init__(self, channel=None, clock_pin=None, mosi_pin=None, miso_pin=None, select_pin=None):
        self._channel = channel
        self._logger = logging.getLogger(LOG_ADSENSOR)
        self._starttime = None
        self._logger.debug("Created mock MCP3008 %s", self.__class__)

    @property
    def value(self):
        # working only on channel 0
        if self._channel == 0:
            if self._starttime and self._starttime + TimeBasedMockMCP3008.CHANGE_TIME > time():
                return 1
            else:
                self._starttime = None

            if int(time()) % 10 == 0:
                self._starttime = time()
                return 1

        return TimeBasedMockMCP3008.DEFAULT_VALUE


class PatternBasedMockMCP3008(object):
    def __init__(self, channel=None, clock_pin=None, mosi_pin=None, miso_pin=None, select_pin=None):
        self._channel = channel
        self._logger = logging.getLogger(LOG_ADSENSOR)
        self._alert_source = []
        # clock
        self.step = 0
        self._logger.debug("Created mock MCP3008 %s on channel: %s", self.__class__.__name__, self._channel)

    @property
    def value(self):
        try:
            self._logger.debug(
                "Values from %s (channel: %s): %s", self.__class__.__name__, self._channel, self._alert_source[self.step]
            )
            value = self._alert_source[self.step][self._channel]
        except (KeyError, TypeError, IndexError):
            value = 0
            self._logger.debug(
                "No value for channel=%s on clock=%s in %s!", self._channel, self.step, self.__class__.__name__
            )

        # next step
        self.step += 1
        if self.step == len(self._alert_source):
            self.step = 0

        return value


class ShortAlertMCP3008(PatternBasedMockMCP3008):

    SHORT_ALERT = [
        [0],
        [0],
        [0],
        [0],
        [0],
        [0],
        [0],
        [0],
        [0],
        [0],
        [1],
        [1],
        [1],
        [1],
        [1],
        [1],
        [1],
        [1],
        [1],
        [1],
        [0],
        [0],
        [0],
        [0],
        [0],
        [0],
        [0],
        [0],
        [0],
        [0],
    ]

    def __init__(self, *args, **kwargs):
        super(ShortAlertMCP3008, self).__init__(*args, **kwargs)
        self._alert_source = ShortAlertMCP3008.SHORT_ALERT


class DoubleAlertMCP3008(PatternBasedMockMCP3008):

    DOUBLE_ALERT = [
        [0, 0],
        [0, 0],
        [0, 0],
        [0, 0],
        [0, 0],
        [0, 0],
        [0, 0],
        [0, 0],
        [0, 0],
        [0, 0],
        [1, 0],
        [1, 0],
        [1, 0],
        [1, 0],
        [1, 0],
        [1, 0],
        [1, 1],
        [1, 1],
        [1, 1],
        [1, 1],
        [1, 1],
        [1, 1],
        [0, 1],
        [0, 1],
        [0, 1],
        [0, 0],
        [0, 0],
        [0, 0],
        [0, 0],
        [0, 0],
    ]

    def __init__(self, *args, **kwargs):
        super(DoubleAlertMCP3008, self).__init__(*args, **kwargs)
        self._alert_source = DoubleAlertMCP3008.DOUBLE_ALERT


class PowerMCP3008(PatternBasedMockMCP3008):

    POWER_ALERT = [
        [0, 0, 0, 0, 0, 0, 0, 1],
        [0, 0, 0, 0, 0, 0, 0, 1],
        [0, 0, 0, 0, 0, 0, 0, 1],
        [0, 0, 0, 0, 0, 0, 0, 1],
        [0, 0, 0, 0, 0, 0, 0, 1],
        [0, 0, 0, 0, 0, 0, 0, 1],
        [0, 0, 0, 0, 0, 0, 0, 1],
        [0, 0, 0, 0, 0, 0, 0, 1],
        [0, 0, 0, 0, 0, 0, 0, 1],
        [0, 0, 0, 0, 0, 0, 0, 1],
        [0, 0, 0, 0, 0, 0, 0, 1],
        [0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0],
    ]

    def __init__(self, *args, **kwargs):
        super(PowerMCP3008, self).__init__(*args, **kwargs)
        self._alert_source = PowerMCP3008.POWER_ALERT


class SimulatorBasedMockLED(object):

    def __init__(self, channel=None):
        self._logger = logging.getLogger(LOG_ADSENSOR)
        self._channel = channel
        self._logger.debug("Created mock LED %s on channel %s", self.__class__, self._channel)
        self._input_file = ""

    @property
    def value(self):

        lock = threading.Lock()

        with lock:
            with open(self._input_file) as channels_file:
                channels_data = json.load(channels_file)
                self._logger.debug("Channel[%s] value simulator: %s", self._channel, channels_data.get(self._channel, 0))
                return channels_data[self._channel]
            
    @property
    def is_pressed(self):
        return self.value == 1


class Channels(SimulatorBasedMockLED):

    CHANNEL_MAPPING = {
        19: "CH01",
        20: "CH02",
        26: "CH03",
        21: "CH04",
        12: "CH05",
        31: "CH06",
        33: "CH07",
        16: "CH08",
        7:  "CH09",
        1:  "CH10",
        0:  "CH11",
        5:  "CH12",
        23: "CH13",
        24: "CH14",
        25: "CH15",
    }

    def __init__(self, channel=None):
        super().__init__(channel=Channels.CHANNEL_MAPPING[channel])
        self._input_file = "channels.json"


class Power(SimulatorBasedMockLED):

    def __init__(self, channel=None):
        super().__init__(channel="POWER")
        self._input_file = "power.json"
