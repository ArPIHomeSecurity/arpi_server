# pylint: disable=raise-missing-from
from dataclasses import asdict

from fastmcp import FastMCP

from mcp_server.errors import ToolChangesNotAllowed
from monitor.config.models import AlertSensitivityConfig
from monitor.database import get_database_session
from server.services.base import ConfigChangesNotAllowed
from server.services.option.alert_sensitivity import AlertSensitivityService

alert_sensitivity_option_mcp = FastMCP("ArPI - alert sensitivity service")


OPTION_NAME = "alert"
OPTION_SECTION = "sensitivity"

session = get_database_session()


@alert_sensitivity_option_mcp.tool(
    name="get_custom_sensitivity",
    description="Get the current alert sensitivity configuration",
)
def get_custom_sensitivity() -> dict:
    """
    Get the current alert sensitivity configuration
    """
    alert_sensitivity_service = AlertSensitivityService(session)
    config = alert_sensitivity_service.get_alert_sensitivity_config()
    return asdict(config)


@alert_sensitivity_option_mcp.tool(
    name="set_custom_sensitivity",
    description="Change the alert sensitivity configuration to custom values",
)
def set_custom_sensitivity(period: int, threshold: int) -> str:
    """
    Change the alert sensitivity configuration to custom values
    """
    try:
        alert_sensitivity_service = AlertSensitivityService(session)
        alert_sensitivity_service.set_alert_sensitivity_config(
            AlertSensitivityConfig(monitor_period=period, monitor_threshold=threshold)
        )
        return "Success"
    except ConfigChangesNotAllowed:
        raise ToolChangesNotAllowed()


@alert_sensitivity_option_mcp.tool(
    name="remove_custom_sensitivity",
    description="Remove the custom alert sensitivity configuration and reset it to default values",
)
def remove_custom_sensitivity() -> str:
    """
    Remove the custom alert sensitivity configuration and reset it to default values
    """
    try:
        AlertSensitivityService(session).remove_custom_sensitivity()
        return "Success"
    except ConfigChangesNotAllowed:
        raise ToolChangesNotAllowed()
