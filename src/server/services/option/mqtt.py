from dataclasses import asdict

from monitor.config.helper import load_config, save_config
from monitor.config.models import (
    MQTTConfigExternalPublish,
    MQTTConfigInternalControl,
    MQTTConfigInternalRead,
    MQTTConnection,
)
from server.ipc import IPCClient
from server.services.base import BaseService, ConfigChangesNotAllowed


class MQTTService(BaseService):
    """
    Service for handling MQTT options.
    """

    def get_connection_config(self) -> MQTTConnection:
        """
        Get the current MQTT connection configuration
        """
        return load_config(MQTTConnection)

    def set_connection_config(self, config: MQTTConnection) -> dict | None:
        """
        Set the MQTT connection configuration (enable/disable, internal vs external broker)
        """
        if not self.are_changes_allowed:
            raise ConfigChangesNotAllowed()

        db_config = load_config(MQTTConnection)
        if db_config and db_config == config:
            return

        save_config(
            MQTTConnection.OPTION_NAME,
            MQTTConnection.SECTION_NAME,
            asdict(config),
        )

        return IPCClient().update_configuration()

    def get_internal_read_config(self) -> MQTTConfigInternalRead:
        """
        Get the internal MQTT broker read configuration (read-only)
        """
        return load_config(MQTTConfigInternalRead)

    def get_internal_control_config(self) -> MQTTConfigInternalControl:
        """
        Get the internal MQTT broker read and control configuration (read-only)
        """
        return load_config(MQTTConfigInternalControl)

    def get_external_publish_config(self) -> MQTTConfigExternalPublish:
        """
        Get the external MQTT broker publish configuration
        """
        return load_config(MQTTConfigExternalPublish)

    def set_external_publish_config(self, config: MQTTConfigExternalPublish) -> dict | None:
        """
        Set the external MQTT broker publish configuration
        """
        if not self.are_changes_allowed:
            raise ConfigChangesNotAllowed()

        db_config = load_config(MQTTConfigExternalPublish)
        if db_config and db_config == config:
            return

        save_config(
            MQTTConfigExternalPublish.OPTION_NAME,
            MQTTConfigExternalPublish.SECTION_NAME,
            asdict(config),
        )

        return IPCClient().update_configuration()
