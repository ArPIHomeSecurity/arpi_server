"""
This module provides helper functions to load configuration settings from the database.
"""
import json

from dataclasses import asdict, dataclass

from models import Option
from monitor.database import get_database_session


@dataclass
class DyndnsConfig:
    username: str = None
    password: str = None
    hostname: str = None
    provider: str = None
    restrict_host: str = False
    certbot_email: str = None


def load_dyndns_config(cleanup=False, session=None) -> DyndnsConfig:
    c = load_config("network", "dyndns", DyndnsConfig) or DyndnsConfig()
    if cleanup:
        save_config("network", "dyndns", asdict(c))

    return c

#####################
@dataclass
class SshConfig:
    service_enabled: bool = True
    restrict_local_network: bool = False
    password_authentication_enabled: bool = True


def load_ssh_config(cleanup=False, session=None) -> SshConfig:
    c = load_config("network", "access", SshConfig) or SshConfig()
    if cleanup:
        save_config("network", "access", asdict(c))
    return c


#####################
@dataclass
class SyrenConfig:
    silent: bool = False
    delay: int = 0
    duration: int = 0


def load_syren_config(cleanup=False, session=None) -> SyrenConfig:
    c = load_config("syren", "timing", SyrenConfig) or SyrenConfig()
    if cleanup:
        save_config("syren", "timing", asdict(c))
    return c


#####################
@dataclass
class AlertSensitivityConfig:
    monitor_period: int = 1
    monitor_threshold: int = 0


def load_alert_sensitivity_config(cleanup=False, session=None) -> AlertSensitivityConfig:
    c= load_config("alert", "sensitivity", AlertSensitivityConfig, session) or AlertSensitivityConfig()
    if cleanup:
        save_config("alert", "sensitivity", asdict(c), session)
    return c


#####################
def load_config(name, section, config_type, session=None):
    """
    Generic function to load a config from the database and return it as a dataclass
    """

    new_session = False
    if session is None:
        new_session = True
        session = get_database_session()

    config = session.query(Option).filter_by(name=name, section=section).first()

    if new_session:
        session.close()

    if config:
        config = json.loads(config.value)
        try:
            return config_type(**config)
        except TypeError:
            pass

    return None


def save_config(name: str, section: str, value: dict, session=None):
    """
    Generic function to save a config to the database
    """
    new_session = False
    if session is None:
        new_session = True
        session = get_database_session()

    config = session.query(Option).filter_by(name=name, section=section).first()
    if not config:
        config = Option(name=name, section=section, value=json.dumps(value))
        session.add(config)
    else:
        config.value = json.dumps(value)

    session.commit()

    if new_session:
        session.close()
