import json
from dataclasses import asdict, dataclass
from unittest.mock import MagicMock

import pytest

from monitor.config.helper import delete_config, load_config, save_config
from monitor.config.registry import register_config_option
from utils.models import Option


@dataclass
class OptionConfig:
	OPTION_NAME = "test"
	SECTION_NAME = "unit"

	enabled: bool = True

register_config_option(OptionConfig)


@pytest.fixture
def session(monkeypatch):
	session = MagicMock()
	monkeypatch.setattr("monitor.config.helper.get_database_session", lambda: session)
	return session


def test_load_config_creates_missing_option(session):
	session.scalar.return_value = None

	config = load_config(OptionConfig)

	assert config == OptionConfig()
	added_option = session.add.call_args.args[0]
	assert added_option.name == OptionConfig.OPTION_NAME
	assert added_option.section == OptionConfig.SECTION_NAME
	assert json.loads(added_option.value) == asdict(OptionConfig())
	session.commit.assert_called_once()
	session.close.assert_called_once()


def test_load_config_resets_invalid_option(session):
	option = Option(
		name=OptionConfig.OPTION_NAME,
		section=OptionConfig.SECTION_NAME,
		value="not valid JSON",
	)
	session.scalar.return_value = option

	config = load_config(OptionConfig)

	assert config == OptionConfig()
	assert json.loads(option.value) == asdict(OptionConfig())
	session.commit.assert_called_once()
	session.close.assert_called_once()


def test_save_config_updates_existing_option(session):
	option = Option(name="test", section="unit", value="{}")
	session.scalar.return_value = option
	value = {"enabled": False}

	save_config("test", "unit", value)

	assert json.loads(option.value) == value
	session.commit.assert_called_once()
	session.close.assert_called_once()


def test_save_config_creates_missing_option(session):
	session.scalar.return_value = None
	value = {"enabled": False}

	save_config("test", "unit", value)

	added_option = session.add.call_args.args[0]
	assert added_option.name == "test"
	assert added_option.section == "unit"
	assert json.loads(added_option.value) == value
	session.begin_nested.assert_called_once()
	session.flush.assert_called_once()
	session.commit.assert_called_once()
	session.close.assert_called_once()


def test_delete_config_removes_existing_option(session):
	option = Option(name="test", section="unit", value="{}")
	session.scalar.return_value = option

	delete_config("test", "unit")

	session.delete.assert_called_once_with(option)
	session.commit.assert_called_once()
	session.close.assert_called_once()


def test_delete_config_skips_missing_option(session):
	session.scalar.return_value = None

	delete_config("test", "unit")

	session.delete.assert_not_called()
	session.commit.assert_not_called()
	session.close.assert_called_once()
