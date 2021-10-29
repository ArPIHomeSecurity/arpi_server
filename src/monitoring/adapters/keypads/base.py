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
        self._keys = []
        self._card = None
        self._function: Action = None

    def get_last_key(self):
        if self._keys:
            return self._keys.pop(0)
        else:
            return None

    @abstractmethod
    def get_card(self):
        """Return the last identified card"""
        pass

    @abstractmethod
    def get_function(self):
        """Return the last identified function"""
        pass

    @abstractmethod
    def last_action(self) -> Action:
        """Last identified action on the keypad"""
        pass

    @abstractmethod
    def initialise(self):
        pass

    @abstractmethod
    def set_error(self, state: bool):
        pass

    @abstractmethod
    def set_ready(self, state: bool):
        pass

    @abstractmethod
    def set_armed(self, state: bool):
        pass

    @abstractmethod
    def communicate(self):
        pass
