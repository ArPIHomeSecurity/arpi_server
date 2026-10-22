from dataclasses import asdict

from monitor.config.helper import load_config, save_config
from monitor.config.models import SyrenConfig
from server.ipc import IPCClient
from server.services.base import BaseService, ConfigChangesNotAllowed, TestingNotAllowed


class SyrenService(BaseService):
    """
    Service for handling options.
    """

    def get_syren_config(self) -> SyrenConfig:
        """
        Get the current siren configuration
        """
        return load_config(SyrenConfig)

    def set_syren_config(self, config: SyrenConfig):
        """
        Set the siren configuration
        """
        if not self.are_changes_allowed:
            raise ConfigChangesNotAllowed()

        save_config(
            SyrenConfig.OPTION_NAME,
            SyrenConfig.SECTION_NAME,
            asdict(config),
        )

    def test_syren(self, duration: int = 5) -> dict:
        """
        Test the syren with the given duration (in seconds max 30 seconds)

        Arguments:
            duration: Duration of the syren in seconds
        """
        if not self.is_testing_allowed:
            raise TestingNotAllowed()

        duration = max(5, duration)  # Ensure minimum duration of 5 seconds
        duration = min(30, duration)  # Cap duration to a reasonable maximum (e.g., 30 seconds)
        return IPCClient().send_test_syren(duration)
