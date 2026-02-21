"""
This module provides helper functions to load configuration settings from the database.
"""

import json

from utils.models import Option
from monitor.database import get_database_session


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


def delete_config(name: str, section: str, session=None):
    """
    Generic function to delete a config from the database
    """
    new_session = False
    if session is None:
        new_session = True
        session = get_database_session()

    config = session.query(Option).filter_by(name=name, section=section).first()
    if config:
        session.delete(config)
        session.commit()

    if new_session:
        session.close()
