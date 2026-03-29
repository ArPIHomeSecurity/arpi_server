import os
from dataclasses import asdict

from monitor.config.helper import save_config
from monitor.config.models import SSHConfig
from server.ipc import IPCClient
from server.services.base import BaseService, ConfigChangesNotAllowed


class SSHService(BaseService):
    """
    Service for handling options.
    """

    def get_ssh_config(self) -> SSHConfig:
        """
        Get the current SSH configuration
        """
        config = SSHConfig.load_config(session=self._db_session)
        if config is None:
            # create new config with default values if not exists
            config = SSHConfig()

        return config

    def set_ssh_config(self, config: SSHConfig) -> dict | None:
        """
        Set the SSH configuration
        """
        if not self.are_changes_allowed:
            raise ConfigChangesNotAllowed()

        db_config = SSHConfig.load_config(session=self._db_session)
        if db_config and db_config == config:
            # No changes needed
            return

        save_config(
            SSHConfig.OPTION_NAME,
            SSHConfig.SECTION_NAME,
            asdict(config),
            session=self._db_session,
        )

        if os.environ.get("USE_SSH_CONNECTION", "true").lower() == "true":
            return IPCClient().update_ssh()

        return
