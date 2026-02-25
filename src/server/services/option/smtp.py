from dataclasses import asdict

from monitor.config.helper import save_config
from monitor.config.models import SMTPConfig
from server.ipc import IPCClient
from server.services.base import BaseService, ConfigChangesNotAllowed, TestingNotAllowed


class SMTPService(BaseService):
    """
    Service for handling SMTP options.
    """

    def get_smtp_config(self) -> SMTPConfig:
        """
        Get the current SMTP configuration
        """
        config = SMTPConfig.load_config(session=self._db_session)
        if config is None:
            # create new config with default values if not exists
            config = SMTPConfig()

        return config

    def set_smtp_config(self, config: SMTPConfig) -> dict | None:
        """
        Set the SMTP configuration
        """
        if not self.are_changes_allowed:
            raise ConfigChangesNotAllowed()

        db_config = SMTPConfig.load_config(session=self._db_session)
        if db_config and db_config == config:
            # No changes needed
            return

        save_config(
            SMTPConfig.OPTION_NAME,
            SMTPConfig.SECTION_NAME,
            asdict(config),
            session=self._db_session,
        )

        return IPCClient().update_configuration()

    def test_email(self) -> dict:
        """
        Send a test email
        """
        if not self.is_testing_allowed:
            raise TestingNotAllowed()

        return IPCClient().send_test_email()
