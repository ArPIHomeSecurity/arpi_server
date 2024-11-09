import logging
from abc import ABC, abstractmethod
from enum import Enum

from constants import LOG_ADKEYPAD
from monitor.adapters.keypads.delay import DelayPhase, Handler


class Action(Enum):
    """Actions of the keypad"""
    KEY = 0
    FUNCTION = 1
    CARD = 2


class Function(Enum):
    """Functions keys"""
    AWAY = 1
    STAY = 2


class KeypadBase(ABC):
    """Base class for the keypads"""

    def __init__(self):
        self.id = None
        self._armed = False
        self._keys = []
        self._card = None
        self._function: Action = None
        self._delay: Handler = None
        self._logger = logging.getLogger(LOG_ADKEYPAD)

    def close(self):
        pass

    def get_last_key(self):
        return self._keys.pop(0) if self._keys else None

    def get_card(self):
        card = self._card
        self._card = None
        return card

    def get_function(self):
        function = self._function
        self._function = None
        return function

    def last_action(self) -> Action:
        """Last identified action on the keypad"""
        if self._card is not None:
            return Action.CARD
        elif self._keys:
            return Action.KEY
        elif self._function:
            return Action.FUNCTION

    def initialise(self):
        pass

    def beeps(self, count, beep, mute):
        pass

    @abstractmethod
    def set_error(self, state: bool):
        pass

    @abstractmethod
    def set_ready(self, state: bool):
        pass

    def set_armed(self, state: bool):
        self._armed = state

    def get_armed(self):
        return self._armed

    def start_delay(self, start, delay):
        self._delay = Handler(start, delay)

    def stop_delay(self):
        self._delay = None

    @abstractmethod
    def communicate(self):
        pass

    def manage_delay(self):
        if self._delay:
            beep = self._delay.do()
            self._logger.debug("Beep type: %s", beep)
            if beep == DelayPhase.NORMAL:
                self.beeps(1, 0.1, 0.1)
            elif beep == DelayPhase.LAST_5_SECS:
                self.beeps(2, 0.1, 0.1)
            elif beep == DelayPhase.NO_BEEP:
                pass
            elif beep == DelayPhase.NO_DELAY:
                self._delay = None
                self.beeps(3, 0.1, 0.1)
            else:
                self._logger.error("Unknown beep type!")
