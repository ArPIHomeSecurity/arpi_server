# pylint: disable=raise-missing-from
from dataclasses import asdict
from fastmcp import FastMCP

from mcp_server.errors import ToolChangesNotAllowed
from monitor.config.models import DyndnsConfig
from monitor.database import get_database_session
from server.services.base import ConfigChangesNotAllowed
from server.services.option.dyndns import DyndnsService
from server.tools import evaluate_ipc_response

dyndns_option_mcp = FastMCP("ArPI - dynamic DNS configuration service")


session = get_database_session()


@dyndns_option_mcp.tool(
    name="get_config",
    description="Get the current dynamic DNS configuration",
)
def get_config() -> dict:
    """
    Get the current dynamic DNS configuration
    """
    dyndns_service = DyndnsService(session)
    config = dyndns_service.get_dyndns_config()
    return asdict(config)


@dyndns_option_mcp.tool(
    name="set_config",
    description="Set the dynamic DNS configuration",
)
def set_config(config: DyndnsConfig) -> str:
    """
    Set the dynamic DNS configuration
    """
    try:
        dyndns_service = DyndnsService(session)
        response = dyndns_service.set_dyndns_config(config)

        if response is not None:
            _, success = evaluate_ipc_response(response)
            return "Success" if success else "Failed"
        
        return "Success"
    except ConfigChangesNotAllowed:
        raise ToolChangesNotAllowed()
