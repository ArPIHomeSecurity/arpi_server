from abc import ABC, abstractmethod


class KeypadBase(ABC):
    def __init__(self):
        self.enabled = True
        self._keys = []

    def get_last_key(self):
        if self._keys:
            return self._keys.pop(0)
        else:
            return None

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
