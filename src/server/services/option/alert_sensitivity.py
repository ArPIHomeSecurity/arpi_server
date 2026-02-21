from dataclasses import asdict

from monitor.config.helper import save_config
from monitor.config.models import AlertSensitivityConfig
from server.ipc import IPCClient
from server.services.base import BaseService, ConfigChangesNotAllowed

OPTION_NAME = "alert"
OPTION_SECTION = "sensitivity"


class AlertSensitivityService(BaseService):
    """
    Service for handling options.
    """

    def get_alert_sensitivity_config(self) -> AlertSensitivityConfig:
        """
        Get the current alert sensitivity configuration
        """
        return AlertSensitivityConfig.load_config(session=self._db_session)

    def set_alert_sensitivity_config(self, config: AlertSensitivityConfig):
        """
        Set the alert sensitivity configuration
        """
        if not self.are_changes_allowed:
            raise ConfigChangesNotAllowed()

        db_config = AlertSensitivityConfig.load_config(session=self._db_session)
        if db_config and db_config == config:
            return

        save_config(
            OPTION_NAME,
            OPTION_SECTION,
            asdict(config),
            session=self._db_session
        )

        IPCClient().update_configuration()

    def remove_custom_sensitivity(self) -> str:
        """
        Remove the custom alert sensitivity configuration and reset it to default values
        """
        AlertSensitivityConfig.load_config(cleanup=True, session=self._db_session)
        return "Success"
