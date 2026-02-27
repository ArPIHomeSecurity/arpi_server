from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from monitor.database import get_database_session
from server.ipc import IPCClient
from server.tools import evaluate_ipc_response
from utils.constants import ARM_DISARM
from utils.queries import get_arm_state

monitoring_mcp = FastMCP("ArPI - monitoring service")


session = get_database_session()


@monitoring_mcp.tool(
    name="update_configuration",
)
def update_configuration_tool():
    """
    Tool to trigger configuration update.
    """
    arm_state = get_arm_state(session=session)
    if arm_state != ARM_DISARM:
        raise ToolError("Cannot update configuration while system is armed.")

    response = IPCClient().update_configuration()
    if response is not None:
        _, success = evaluate_ipc_response(response)
        return "Success" if success else "Failed"

    return "Success"

@monitoring_mcp.tool(
    name="get_arm_state",
)
def get_arm_state_tool():
    """
    Tool to retrieve the current arm state.
    """
    return get_arm_state(session=session)
