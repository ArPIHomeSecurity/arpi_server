from fastmcp import FastMCP

from monitor.database import get_database_session
from server.ipc import IPCClient
from server.tools import get_ipc_response
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
        raise Exception("Cannot update configuration while system is armed.")

    result,_ = get_ipc_response(IPCClient().update_configuration())
    return result

@monitoring_mcp.tool(
    name="get_arm_state",
)
def get_arm_state_tool():
    """
    Tool to retrieve the current arm state.
    """
    return get_arm_state(session=session)
