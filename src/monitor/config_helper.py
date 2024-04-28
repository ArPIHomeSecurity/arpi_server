import json

from dataclasses import dataclass

from models import Option
from monitor.database import Session


@dataclass
class DyndnsConfig:
    username: str
    password: str
    hostname: str
    provider: str
    restrict_host: str


def load_dyndns_config() -> DyndnsConfig:
    return load_config("network", "dyndns", DyndnsConfig)


#####################
@dataclass
class SshConfig:
    service_enabled: bool = False
    restrict_local_network: bool = False
    password_authentication_enabled: bool = True


def load_ssh_config() -> SshConfig:
    return load_config("network", "access", SshConfig)


#####################
@dataclass
class SyrenConfig:
    silent: bool
    delay: int
    stop_time: int


def load_syren_config() -> SyrenConfig:
    return load_config("syren", "timing", SyrenConfig)


#####################
@dataclass
class AlertSensitivityConfig:
    monitor_period: int
    monitor_threshold: int


def load_alert_sensitivity_config(session=None) -> AlertSensitivityConfig:
    return load_config("alert", "sensitivity", AlertSensitivityConfig, session)


#####################
def load_config(name, section, config_type, session=None):
    """
    Generic function to load a config from the database and return it as a dataclass
    """

    new_session = False
    if session is None:
        new_session = True
        session = Session()

    config = session.query(Option).filter_by(name=name, section=section).first()

    if new_session:
        session.close()

    if config:
        config = json.loads(config.value)
        return config_type(**config)
