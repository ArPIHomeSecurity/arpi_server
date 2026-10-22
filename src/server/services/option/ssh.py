import os
from dataclasses import asdict

from monitor.config.helper import load_config, save_config
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
        return load_config(SSHConfig)

    def set_ssh_config(self, config: SSHConfig) -> dict | None:
        """
        Set the SSH configuration
        """
        if not self.are_changes_allowed:
            raise ConfigChangesNotAllowed()

        db_config = load_config(SSHConfig)
        if db_config and db_config == config:
            # No changes needed
            return

        save_config(
            SSHConfig.OPTION_NAME,
            SSHConfig.SECTION_NAME,
            asdict(config),
        )

        if os.environ.get("USE_SSH_CONNECTION", "true").lower() == "true":
            return IPCClient().update_ssh()

        return
