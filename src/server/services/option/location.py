from dataclasses import asdict

from monitor.config.helper import load_config, save_config
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
        return load_config(LocationConfig)

    def set_location_config(self, config: LocationConfig) -> None:
        """
        Set the location configuration
        """
        if not self.are_changes_allowed:
            raise ConfigChangesNotAllowed()

        db_config = load_config(LocationConfig)
        if db_config and db_config == config:
            # No changes needed
            return

        save_config(
            LocationConfig.OPTION_NAME,
            LocationConfig.SECTION_NAME,
            asdict(config),
        )
