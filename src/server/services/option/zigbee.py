from attr import asdict

from monitor.config.helper import save_config
from monitor.config.models import ZigbeeCoordinatorConfig
from server.services.base import BaseService, ConfigChangesNotAllowed


class ZigbeeService(BaseService):
    def get_zigbee_coordinator_config(self):
        """
        Get the current Zigbee coordinator configuration
        """
        from monitor.config.models import ZigbeeCoordinatorConfig

        config = ZigbeeCoordinatorConfig.load_config(session=self._db_session)
        if config is None:
            # create new config with default values if not exists
            config = ZigbeeCoordinatorConfig()

        return config

    def set_zigbee_coordinator_config(self, config):
        """
        Set the Zigbee coordinator configuration
        """
        if not self.are_changes_allowed:
            raise ConfigChangesNotAllowed()

        save_config(
            ZigbeeCoordinatorConfig.OPTION_NAME,
            ZigbeeCoordinatorConfig.SECTION_NAME,
            asdict(config),
            session=self._db_session,
        )
