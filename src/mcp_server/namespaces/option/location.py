# pylint: disable=raise-missing-from
from dataclasses import asdict
from fastmcp import FastMCP

from mcp_server.errors import ToolChangesNotAllowed
from monitor.config.models import LocationConfig
from monitor.database import get_database_session
from server.services.base import ConfigChangesNotAllowed
from server.services.option import LocationConfigService
from server.tools import evaluate_ipc_response

location_option_mcp = FastMCP("ArPI - Subscription location configuration service")


@location_option_mcp.tool(
    name="get_config",
    description="Get the current subscription location configuration",
)
def get_config() -> dict:
    """
    Get the current subscription location configuration
    """
    location_service = LocationConfigService(get_database_session())
    config = location_service.get_location_config()
    return asdict(config)


@location_option_mcp.tool(
    name="set_config",
    description="Set the subscription location configuration",
)
def set_config(config: LocationConfig) -> str:
    """
    Set the subscription location configuration
    """
    try:
        location_service = LocationConfigService(get_database_session())
        response = location_service.set_location_config(config)

        if response is not None:
            _, success = evaluate_ipc_response(response)
            return "Success" if success else "Failed"

        return "Success"
    except ConfigChangesNotAllowed:
        raise ToolChangesNotAllowed()
