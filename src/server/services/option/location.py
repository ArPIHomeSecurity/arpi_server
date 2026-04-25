from dataclasses import asdict

from monitor.config.helper import save_config
from monitor.config.models import LocationConfig
from server.services.base import BaseService, ConfigChangesNotAllowed


class LocationConfigService(BaseService):
    """
    Service for handling location options.
    """

    def get_location_config(self) -> LocationConfig:
        """
        Get the current location configuration
        """
        config = LocationConfig.load_config(session=self._db_session)
        if config is None:
            # create new config with default values if not exists
            config = LocationConfig()

        return config

    def set_location_config(self, config: LocationConfig) -> None:
        """
        Set the location configuration
        """
        if not self.are_changes_allowed:
            raise ConfigChangesNotAllowed()

        db_config = LocationConfig.load_config(session=self._db_session)
        if db_config and db_config == config:
            # No changes needed
            return

        save_config(
            LocationConfig.OPTION_NAME,
            LocationConfig.SECTION_NAME,
            asdict(config),
            session=self._db_session,
        )
