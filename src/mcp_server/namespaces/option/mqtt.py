# pylint: disable=raise-missing-from
from dataclasses import asdict
from fastmcp import FastMCP

from mcp_server.errors import ToolChangesNotAllowed
from monitor.config.models import MQTTConfigExternalPublish, MQTTConnection
from monitor.database import get_database_session
from server.services.base import ConfigChangesNotAllowed
from server.services.option import MQTTService
from server.tools import evaluate_ipc_response

mqtt_option_mcp = FastMCP("ArPI - MQTT configuration service")


@mqtt_option_mcp.tool(
    name="get_connection_config",
    description="Get the current MQTT connection configuration (enabled/disabled, internal vs external broker)",
)
def get_connection_config() -> dict:
    """
    Get the current MQTT connection configuration
    """
    mqtt_service = MQTTService(get_database_session())
    config = mqtt_service.get_connection_config()
    return asdict(config) if config else {}


@mqtt_option_mcp.tool(
    name="set_connection_config",
    description="Enable or disable the MQTT interface and select internal or external broker",
)
def set_connection_config(config: MQTTConnection) -> str:
    """
    Set the MQTT connection configuration
    """
    try:
        mqtt_service = MQTTService(get_database_session())
        response = mqtt_service.set_connection_config(config)

        if response is not None:
            _, success = evaluate_ipc_response(response)
            return "Success" if success else "Failed"

        return "Success"
    except ConfigChangesNotAllowed:
        raise ToolChangesNotAllowed()


@mqtt_option_mcp.tool(
    name="get_internal_read_config",
    description="Get the internal MQTT broker read configuration (read-only, system-managed)",
)
def get_internal_read_config() -> dict:
    """
    Get the internal MQTT broker read configuration
    """
    mqtt_service = MQTTService(get_database_session())
    config = mqtt_service.get_internal_read_config()
    return asdict(config) if config else {}


@mqtt_option_mcp.tool(
    name="get_external_publish_config",
    description="Get the external MQTT broker publish configuration",
)
def get_external_publish_config() -> dict:
    """
    Get the external MQTT broker publish configuration
    """
    mqtt_service = MQTTService(get_database_session())
    config = mqtt_service.get_external_publish_config()
    return asdict(config) if config else {}


@mqtt_option_mcp.tool(
    name="set_external_publish_config",
    description="Set the external MQTT broker publish configuration",
)
def set_external_publish_config(config: MQTTConfigExternalPublish) -> str:
    """
    Set the external MQTT broker publish configuration
    """
    try:
        mqtt_service = MQTTService(get_database_session())
        response = mqtt_service.set_external_publish_config(config)

        if response is not None:
            _, success = evaluate_ipc_response(response)
            return "Success" if success else "Failed"

        return "Success"
    except ConfigChangesNotAllowed:
        raise ToolChangesNotAllowed()
