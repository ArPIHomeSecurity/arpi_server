from dataclasses import asdict

from monitor.config.helper import save_config
from monitor.config.models import GSMConfig, SMSActionConfig, SMSCommandConfig
from server.ipc import IPCClient
from server.services.base import BaseService, ConfigChangesNotAllowed, TestingNotAllowed


class GSMService(BaseService):
    """
    Service for handling GSM options.
    """

    def get_gsm_config(self) -> GSMConfig:
        """
        Get the current GSM configuration
        """
        config = GSMConfig.load_config(session=self._db_session)
        if config is None:
            # create new config with default values if not exists
            config = GSMConfig()

        return config

    def set_gsm_config(self, config: GSMConfig) -> dict | None:
        """
        Set the GSM configuration
        """
        if not self.are_changes_allowed:
            raise ConfigChangesNotAllowed()

        db_config = GSMConfig.load_config(session=self._db_session)
        if db_config and db_config == config:
            # No changes needed
            return

        save_config(
            GSMConfig.OPTION_NAME,
            GSMConfig.SECTION_NAME,
            asdict(config),
            session=self._db_session,
        )

        return IPCClient().update_configuration()

    def get_sms_action_config(self) -> SMSActionConfig:
        """
        Get the current SMS action configuration
        """
        config = SMSActionConfig.load_config(session=self._db_session)
        if config is None:
            # create new config with default values if not exists
            config = SMSActionConfig()

        return config

    def set_sms_action_config(self, config: SMSActionConfig) -> dict | None:
        """
        Set the SMS action configuration
        """
        if not self.are_changes_allowed:
            raise ConfigChangesNotAllowed()

        db_config = SMSActionConfig.load_config(session=self._db_session)
        if db_config and db_config == config:
            # No changes needed
            return

        save_config(
            SMSActionConfig.OPTION_NAME,
            SMSActionConfig.SECTION_NAME,
            asdict(config),
            session=self._db_session,
        )

        return IPCClient().update_configuration()

    def get_sms_command_config(self) -> SMSCommandConfig:
        """
        Get the current SMS command configuration
        """
        config = SMSCommandConfig.load_config(session=self._db_session)
        if config is None:
            # create new config with default values if not exists
            config = SMSCommandConfig()

        return config

    def set_sms_command_config(self, config: SMSCommandConfig) -> dict | None:
        """
        Set the SMS command configuration
        """
        if not self.are_changes_allowed:
            raise ConfigChangesNotAllowed()

        db_config = SMSCommandConfig.load_config(session=self._db_session)
        if db_config and db_config == config:
            # No changes needed
            return

        save_config(
            SMSCommandConfig.OPTION_NAME,
            SMSCommandConfig.SECTION_NAME,
            asdict(config),
            session=self._db_session,
        )

        return IPCClient().update_configuration()

    def test_sms(self) -> dict:
        """
        Send a test SMS message
        """
        if not self.is_testing_allowed:
            raise TestingNotAllowed()

        return IPCClient().send_test_sms()

    def test_call(self) -> dict:
        """
        Make a test phone call
        """
        if not self.is_testing_allowed:
            raise TestingNotAllowed()

        return IPCClient().make_test_call()
