import json
import logging
import threading

from constants import LOG_ADSENSOR


class SimulatorBasedMockInput(object):

    def __init__(self, channel=None):
        self._logger = logging.getLogger(LOG_ADSENSOR)
        self._channel = channel
        self._logger.debug("Created mock input %s on channel %s", self.__class__, self._channel)

    @property
    def value(self):

        lock = threading.Lock()

        with lock:
            # write+create if not exists
            try:
                with open("simulator_input.json") as channels_file:
                    channels_data = json.load(channels_file)
                    self._logger.trace("Channel[%s] value simulator: %s", self._channel, channels_data.get(self._channel, 0))
                    # simulate random noise
                    # if time() % 10 > 5:
                    #     return 0
                    return channels_data[self._channel]
            except FileNotFoundError:
                return 0

    @property
    def is_pressed(self):
        return self.value == 1

    def close(self):
        self._logger.debug("Closing mock input %s on channel %s", self.__class__, self._channel)


class Channels(SimulatorBasedMockInput):

    CHANNEL_MAPPING = {
        19: "CH01",
        20: "CH02",
        26: "CH03",
        21: "CH04",
        12: "CH05",
        6:  "CH06",
        13: "CH07",
        16: "CH08",
        7:  "CH09",
        1:  "CH10",
        0:  "CH11",
        5:  "CH12",
        23: "CH13",
        24: "CH14",
        25: "CH15"
    }

    def __init__(self, channel=None, pull_up=None):
        super().__init__(channel=Channels.CHANNEL_MAPPING[channel])

    def close(self):
        pass


class Power(SimulatorBasedMockInput):

    def __init__(self, channel=None):
        super().__init__(channel="POWER")
