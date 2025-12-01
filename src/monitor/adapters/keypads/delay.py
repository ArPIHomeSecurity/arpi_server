import logging
from datetime import datetime as dt, timedelta
from enum import Enum

from utils.constants import LOG_ADKEYPAD


class DelayPhase(Enum):
    NO_DELAY = 0
    NO_BEEP = 1
    NORMAL = 2
    LAST_5_SECS = 3


class Handler():

    def __init__(self, start, delay) -> None:
        self._start = start
        self._delay = delay
        self._step = 0
        self._logger = logging.getLogger(LOG_ADKEYPAD)

    def do(self) -> bool:
        self._logger.debug("Start: %s delay: %s step: %s", self._start, self._delay, self._step)
        now = dt.now()
        if self._start.replace(tzinfo=None) + timedelta(seconds=self._delay) > now:
            if (now - self._start.replace(tzinfo=None)).total_seconds() > self._step:
                self._step += 1
                if self._delay - 5 < self._step:
                    return DelayPhase.LAST_5_SECS

                return DelayPhase.NORMAL

            return DelayPhase.NO_BEEP

        return DelayPhase.NO_DELAY
