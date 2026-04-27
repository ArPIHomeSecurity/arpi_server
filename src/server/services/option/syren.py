from dataclasses import asdict
from monitor.config.helper import save_config
from monitor.config.models import SyrenConfig
from monitor.syren import Syren
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
        config = SyrenConfig.load_config(session=self._db_session)
        if config is None:
            # create new config with default values if not exists
            config = SyrenConfig(silent=Syren.SILENT, delay=Syren.DELAY, duration=Syren.DURATION)

        return config

    def set_syren_config(self, config: SyrenConfig):
        """
        Set the siren configuration
        """
        if not self.are_changes_allowed:
            raise ConfigChangesNotAllowed()

        save_config(
            SyrenConfig.OPTION_NAME,
            SyrenConfig.OPTION_SECTION,
            asdict(config),
            session=self._db_session,
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
