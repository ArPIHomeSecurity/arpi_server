from abc import ABC, abstractmethod


class BaseInstaller(ABC):
    """Base class for all component installers"""

    def __init__(self, config: dict):
        self.config = config
        self.warnings = []

    @abstractmethod
    def install(self):
        """Install the component"""
        pass

    @abstractmethod
    def get_status(self) -> dict:
        """Get component status information"""
        pass
