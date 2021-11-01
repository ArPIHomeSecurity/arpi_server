from abc import ABC, abstractmethod
from enum import Enum


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
        self.enabled = True
        self._armed = False
        self._keys = []
        self._card = None
        self._function: Action = None

    def get_last_key(self):
        if self._keys:
            return self._keys.pop(0)
        else:
            return None

    def get_card(self):
        card = self._card
        self._card = None
        return card

    @abstractmethod
    def get_function(self):
        """Return the last identified function"""
        pass

    def last_action(self) -> Action:
        """Last identified action on the keypad"""
        if self._card is not None:
            return Action.CARD
        elif self._keys:
            return Action.KEY

    @abstractmethod
    def initialise(self):
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

    @abstractmethod
    def communicate(self):
        pass
