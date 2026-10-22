from dataclasses import asdict

from monitor.config.helper import load_config, save_config
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
        return load_config(AlertSensitivityConfig)

    def set_alert_sensitivity_config(self, config: AlertSensitivityConfig):
        """
        Set the alert sensitivity configuration
        """
        if not self.are_changes_allowed:
            raise ConfigChangesNotAllowed()

        db_config = load_config(AlertSensitivityConfig)
        if db_config and db_config == config:
            return

        save_config(OPTION_NAME, OPTION_SECTION, asdict(config))

        IPCClient().update_configuration()

    def remove_custom_sensitivity(self) -> str:
        """
        Remove the custom alert sensitivity configuration and reset it to default values
        """
        save_config(
            OPTION_NAME,
            OPTION_SECTION,
            asdict(AlertSensitivityConfig()),
        )
        return "Success"
