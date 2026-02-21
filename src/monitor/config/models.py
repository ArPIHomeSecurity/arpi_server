"""
This module defines the dataclasses for configurations used in the monitor.

"""

from dataclasses import asdict, dataclass

from monitor.config.helper import load_config, save_config


class BaseConfig:
    """
    Base class for all configs, provides common methods for loading and saving configs
    We use class methods for option and section to avoid conflicts with dataclass fields.
    """

    OPTION_NAME = None
    SECTION_NAME = None

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


@dataclass
class DyndnsConfig(BaseConfig):
    OPTION_NAME = "network"
    SECTION_NAME = "dyndns"

    username: str = None
    password: str = None
    hostname: str = None
    provider: str = None
    restrict_host: str = False
    certbot_email: str = None


@dataclass
class SyrenConfig(BaseConfig):
    OPTION_NAME = "syren"
    SECTION_NAME = "timing"

    silent: bool | None = False
    delay: int = 0
    duration: int = 0


@dataclass
class SSHConfig(BaseConfig):
    OPTION_NAME = "network"
    SECTION_NAME = "access"

    service_enabled: bool = True
    restrict_local_network: bool = False
    password_authentication_enabled: bool = True


@dataclass
class AlertSensitivityConfig(BaseConfig):
    OPTION_NAME = "alert"
    SECTION_NAME = "sensitivity"

    monitor_period: int | None = None
    monitor_threshold: int | None = None


@dataclass
class MQTTConnection(BaseConfig):
    OPTION_NAME = "mqtt"
    SECTION_NAME = "connection"

    enabled: bool
    external: bool


@dataclass
class MQTTConfigInternalRead(BaseConfig):
    OPTION_NAME = "mqtt"
    SECTION_NAME = "internal_read"

    hostname: str
    port: int
    username: str
    password: str
    tls_enabled: bool
    tls_insecure: bool


@dataclass
class MQTTConfigInternalPublish(BaseConfig):
    OPTION_NAME = "mqtt"
    SECTION_NAME = "internal_publish"

    hostname: str
    port: int
    username: str
    password: str
    tls_enabled: bool
    tls_insecure: bool


@dataclass
class MQTTConfigExternalPublish(BaseConfig):
    OPTION_NAME = "mqtt"
    SECTION_NAME = "external_publish"

    hostname: str
    port: int
    username: str
    password: str
    tls_enabled: bool
    tls_insecure: bool
