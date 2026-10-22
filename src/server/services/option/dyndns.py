import os
from dataclasses import asdict

from monitor.config.helper import load_config, save_config
from monitor.config.models import DyndnsConfig
from server.ipc import IPCClient
from server.services.base import BaseService, ConfigChangesNotAllowed


class DyndnsService(BaseService):
    """
    Service for handling dynamic DNS options.
    """

    def get_dyndns_config(self) -> DyndnsConfig:
        """
        Get the current dynamic DNS configuration
        """
        return load_config(DyndnsConfig)

    def set_dyndns_config(self, config: DyndnsConfig) -> dict | None:
        """
        Set the dynamic DNS configuration
        """
        if not self.are_changes_allowed:
            raise ConfigChangesNotAllowed()

        db_config = load_config(DyndnsConfig)
        if db_config and db_config == config:
            # No changes needed
            return

        save_config(
            DyndnsConfig.OPTION_NAME,
            DyndnsConfig.SECTION_NAME,
            asdict(config),
        )

        if os.environ.get("USE_SSH_CONNECTION", "true").lower() == "true":
            return IPCClient().update_dyndns()

        return
