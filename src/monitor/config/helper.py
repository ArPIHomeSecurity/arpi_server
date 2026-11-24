"""
This module provides helper functions to load configuration settings from the database.
"""

import json
import logging
from dataclasses import asdict
from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from monitor.database import create_database_session
from utils.models import Option

T = TypeVar("T")
logger = logging.getLogger(__name__)


def _config_identity(config_type) -> tuple[str, str]:
    """
    Retrieve the identity of a configuration class.
    """
    name = getattr(config_type, "OPTION_NAME", None)
    section = getattr(config_type, "SECTION_NAME", None)
    if name is None or section is None:
        raise NotImplementedError(
            "Option name and section name must be defined on the config class"
        )

    return name, section


def _deserialize_config(value, config_type) -> T | None:
    """
    Deserialize a configuration option from the database into a config dataclass.
    """
    try:
        value = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Invalid JSON data for config %s", config_type.__name__)
        return None

    # attempt to initialize the config with the deserialized values
    try:
        return config_type(**value)
    except TypeError:
        logger.warning("Failed to initialize config %s for option", config_type.__name__)

    return None


def load_config(config_type: type[T]) -> T:
    """
    Load a config dataclass, creating and persisting its defaults when absent.

    Returns:
        An instance of the config dataclass populated with values from the database or defaults.
    """
    with create_database_session() as session:
        changed = False
        name, section = _config_identity(config_type)
        option = session.scalar(
            select(Option).where(Option.name == name, Option.section == section)
        )

        # if the option exists, deserialize it into the config dataclass
        if option is not None:
            config = _deserialize_config(option.value, config_type)
            if config is None:
                # attempt to convert the deserialized values by the config class
                try:
                    raw_value = json.loads(option.value)
                    config = config_type.from_dict(raw_value)
                except (json.JSONDecodeError, TypeError):
                    logger.error("Invalid JSON data for config %s", config_type.__name__)
                except NotImplementedError:
                    logger.error("Failed to deserialize config %s for option", config_type.__name__)

                if config is None:
                    config = config_type()
                option.value = json.dumps(asdict(config))
                changed = True

        # add the option to the session if it didn't exist before
        if option is None:
            config = config_type()
            option = Option(name=name, section=section, value=json.dumps(asdict(config)))
            session.add(option)
            changed = True

        if changed:
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                option = session.scalar(
                    select(Option).where(Option.name == name, Option.section == section)
                )
                config = config_type(**json.loads(option.value))

        return config


def save_config(name: str, section: str, value: dict):
    """
    Generic function to save a config to the database
    """
    with create_database_session() as session:
        config = session.scalar(
            select(Option).where(Option.name == name, Option.section == section)
        )
        if config is None:
            try:
                with session.begin_nested():
                    config = Option(name=name, section=section, value=json.dumps(value))
                    session.add(config)
                    session.flush()
            except IntegrityError:
                config = session.scalar(
                    select(Option).where(Option.name == name, Option.section == section)
                )
                if config is None:
                    raise
                config.value = json.dumps(value)
        else:
            config.value = json.dumps(value)

        session.commit()


def delete_config(name: str, section: str):
    """
    Generic function to delete a config from the database
    """
    with create_database_session() as session:
        config = session.scalar(
            select(Option).where(Option.name == name, Option.section == section)
        )
        if config:
            session.delete(config)
            session.commit()
