# pylint: disable=raise-missing-from
from dataclasses import asdict
from fastmcp import FastMCP

from fastmcp.exceptions import ToolError

from mcp_server.errors import ToolChangesNotAllowed
from monitor.config.models import GSMConfig
from monitor.database import get_database_session
from server.services.base import ConfigChangesNotAllowed, TestingNotAllowed
from server.services.option import GSMService
from server.tools import evaluate_ipc_response

gsm_option_mcp = FastMCP("ArPI - GSM configuration service")




@gsm_option_mcp.tool(
    name="get_config",
    description="Get the current GSM configuration",
)
def get_config() -> dict:
    """
    Get the current GSM configuration
    """
    gsm_service = GSMService(get_database_session())
    config = gsm_service.get_gsm_config()
    return asdict(config)


@gsm_option_mcp.tool(
    name="set_config",
    description="Set the GSM configuration",
)
def set_config(config: GSMConfig) -> str:
    """
    Set the GSM configuration
    """
    try:
        gsm_service = GSMService(get_database_session())
        response = gsm_service.set_gsm_config(config)

        if response is not None:
            _, success = evaluate_ipc_response(response)
            return "Success" if success else "Failed"

        return "Success"
    except ConfigChangesNotAllowed:
        raise ToolChangesNotAllowed()


@gsm_option_mcp.tool(
    name="test_sms",
    description="Send a test SMS message",
)
def test_sms() -> str:
    """
    Send a test SMS message
    """
    try:
        gsm_service = GSMService(get_database_session())
        response = gsm_service.test_sms()
        if response is not None:
            _, success = evaluate_ipc_response(response)
            return "Success" if success else "Failed"

        return "Success"
    except TestingNotAllowed:
        raise ToolError("Testing is not allowed currently.")


@gsm_option_mcp.tool(
    name="test_call",
    description="Make a test phone call",
)
def test_call() -> str:
    """
    Make a test phone call
    """
    try:
        gsm_service = GSMService(get_database_session())
        response = gsm_service.test_call()
        if response is not None:
            _, success = evaluate_ipc_response(response)
            return "Success" if success else "Failed"

        return "Success"
    except TestingNotAllowed:
        raise ToolError("Testing is not allowed currently.")
