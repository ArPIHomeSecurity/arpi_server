"""
This module defines the base class for all configuration dataclasses used in the monitor.
"""

from dataclasses import asdict

from monitor.config.helper import load_config, save_config
from monitor.config.registry import register_config_option


class BaseConfig:
    """
    Base class for all configs, provides common methods for loading and saving configs.
    We use class methods for option and section to avoid conflicts with dataclass fields.
    """

    OPTION_NAME = None
    SECTION_NAME = None

    def __post_init__(self):
        register_config_option(self.__class__)

    @classmethod
    def load_config(cls, cleanup=False, session=None):
        """
        Load the config from the database and return it as a dataclass or the default values
        if it doesn't exist.

        Args:
            cleanup (bool): If True, save the values back to the database to ensure they are stored
            session: The database session to use for loading and saving the config
        """
        if cls.OPTION_NAME is None or cls.SECTION_NAME is None:
            raise NotImplementedError(
                "Option name and section name must be defined in the subclass"
            )

        config = load_config(cls.OPTION_NAME, cls.SECTION_NAME, cls, session) or cls()
        if cleanup:
            save_config(cls.OPTION_NAME, cls.SECTION_NAME, asdict(config), session=session)

        return config
