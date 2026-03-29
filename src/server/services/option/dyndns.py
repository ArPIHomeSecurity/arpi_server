import os
from dataclasses import asdict

from monitor.config.helper import save_config
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
        config = DyndnsConfig.load_config(session=self._db_session)
        if config is None:
            # create new config with default values if not exists
            config = DyndnsConfig()

        return config

    def set_dyndns_config(self, config: DyndnsConfig) -> dict | None:
        """
        Set the dynamic DNS configuration
        """
        if not self.are_changes_allowed:
            raise ConfigChangesNotAllowed()

        db_config = DyndnsConfig.load_config(session=self._db_session)
        if db_config and db_config == config:
            # No changes needed
            return

        save_config(
            DyndnsConfig.OPTION_NAME,
            DyndnsConfig.SECTION_NAME,
            asdict(config),
            session=self._db_session,
        )

        if os.environ.get("USE_SSH_CONNECTION", "true").lower() == "true":
            return IPCClient().update_dyndns()

        return
