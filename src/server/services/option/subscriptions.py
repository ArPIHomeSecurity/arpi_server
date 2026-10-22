from dataclasses import asdict

from monitor.config.helper import load_config, save_config
from monitor.config.models import SubscriptionsConfig
from server.ipc import IPCClient
from server.services.base import BaseService, ConfigChangesNotAllowed


class SubscriptionsService(BaseService):
    """
    Service for handling notification subscriptions options.
    """

    def get_subscriptions_config(self) -> SubscriptionsConfig:
        """
        Get the current subscriptions configuration
        """
        return load_config(SubscriptionsConfig)

    def set_subscriptions_config(self, config: SubscriptionsConfig) -> dict | None:
        """
        Set the subscriptions configuration
        """
        if not self.are_changes_allowed:
            raise ConfigChangesNotAllowed()

        db_config = load_config(SubscriptionsConfig)
        if db_config and db_config == config:
            # No changes needed
            return

        save_config(
            SubscriptionsConfig.OPTION_NAME,
            SubscriptionsConfig.SECTION_NAME,
            asdict(config),
        )

        return IPCClient().update_configuration()
