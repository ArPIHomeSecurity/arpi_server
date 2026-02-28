# pylint: disable=raise-missing-from
from dataclasses import asdict

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from mcp_server.errors import ToolChangesNotAllowed
from monitor.database import get_database_session
from server.services.base import ConfigChangesNotAllowed, TestingNotAllowed
from server.services.option import SyrenService
from server.tools import evaluate_ipc_response

syren_option_mcp = FastMCP("ArPI - syren configuration service")


OPTION_NAME = "syren"
OPTION_SECTION = "timing"

session = get_database_session()

@syren_option_mcp.tool(
    name="get_config",
    description="Get the current syren configuration, silent=null means that it can be overridden on the sensor level",
)
def get_config() -> dict:
    """
    Get the current syren configuration
    """
    syren_service = SyrenService(session)
    config = syren_service.get_syren_config()
    return asdict(config)


@syren_option_mcp.tool(
    name="siren_silent_mode",
    description="Change the mode of the syren (silent, normal)",
)
def change_volume(silent: bool) -> str:
    """
    Change the mode of the syren (silent, normal)
    """
    try:
        syren_service = SyrenService(session)
        config = syren_service.get_syren_config()
        config.silent = silent
        syren_service.set_syren_config(config)
        return "Success"
    except ConfigChangesNotAllowed:
        raise ToolChangesNotAllowed()


@syren_option_mcp.tool(
    name="siren_timing",
    description="Change the timing of the syren (delay and duration)",
)
def change_timing(delay: int, duration: int) -> str:
    """
    Change the timing of the syren (delay and duration)

    Duration of 0 means that the syren will not stop until disarmed.
    """
    try:
        syren_service = SyrenService(session)
        config = syren_service.get_syren_config()
        config.delay = delay
        config.duration = duration
        syren_service.set_syren_config(config)
        return "Success"
    except ConfigChangesNotAllowed:
        raise ToolChangesNotAllowed()


@syren_option_mcp.tool(
    name="test",
    description="Execute a test syren activation",
)
def test_syren(duration: int = 5) -> str:
    """
    Execute a test syren activation
    """
    try:
        option_service = SyrenService(session)
        response = option_service.test_syren(duration)
        if response is not None:
            _, success = evaluate_ipc_response(response)
            return "Success" if success else "Failed"

        return "Success"
    except TestingNotAllowed:
        raise ToolError("Testing is not allowed currently.")

