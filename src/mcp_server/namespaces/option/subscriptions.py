# pylint: disable=raise-missing-from
from dataclasses import asdict
from fastmcp import FastMCP

from mcp_server.errors import ToolChangesNotAllowed
from monitor.config.models import SubscriptionsConfig
from monitor.database import get_database_session
from server.services.base import ConfigChangesNotAllowed
from server.services.option import SubscriptionsService
from server.tools import evaluate_ipc_response

subscriptions_option_mcp = FastMCP("ArPI - notification subscriptions configuration service")




@subscriptions_option_mcp.tool(
    name="get_config",
    description="Get the current notification subscriptions configuration",
)
def get_config() -> dict:
    """
    Get the current notification subscriptions configuration
    """
    subscriptions_service = SubscriptionsService(get_database_session())
    config = subscriptions_service.get_subscriptions_config()
    return asdict(config)


@subscriptions_option_mcp.tool(
    name="set_config",
    description="Set the notification subscriptions configuration",
)
def set_config(config: SubscriptionsConfig) -> str:
    """
    Set the notification subscriptions configuration
    """
    try:
        subscriptions_service = SubscriptionsService(get_database_session())
        response = subscriptions_service.set_subscriptions_config(config)

        if response is not None:
            _, success = evaluate_ipc_response(response)
            return "Success" if success else "Failed"

        return "Success"
    except ConfigChangesNotAllowed:
        raise ToolChangesNotAllowed()
