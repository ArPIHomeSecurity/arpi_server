# pylint: disable=raise-missing-from
from dataclasses import asdict
from fastmcp import FastMCP

from mcp_server.errors import ToolChangesNotAllowed
from monitor.database import get_database_session
from server.services.base import ConfigChangesNotAllowed
from server.services.option.ssh import SSHService
from server.tools import evaluate_ipc_response

ssh_option_mcp = FastMCP("ArPI - SSH configuration service")


session = get_database_session()


@ssh_option_mcp.tool(
    name="get_config",
    description="Get the current SSH configuration",
)
def get_config() -> dict:
    """
    Get the current SSH configuration
    """
    ssh_service = SSHService(session)
    config = ssh_service.get_ssh_config()
    return asdict(config)


@ssh_option_mcp.tool(
    name="enable_connection",
    description="Enable or disable the SSH connection",
)
def enable_connection(enabled: bool) -> str:
    """
    Enable or disable the SSH connection
    """
    try:
        ssh_service = SSHService(session)
        config = ssh_service.get_ssh_config()
        config.service_enabled = enabled
        response = ssh_service.set_ssh_config(config)
        if response is not None:
            _, success = evaluate_ipc_response(response)
            return "Success" if success else "Failed"

        return "Success"
    except ConfigChangesNotAllowed:
        raise ToolChangesNotAllowed()


@ssh_option_mcp.tool(
    name="restrict_local_network",
    description="Restrict SSH access to local network only",
)
def restrict_local_network(restrict: bool) -> str:
    """
    Restrict SSH access to local network only
    """
    try:
        ssh_service = SSHService(session)
        config = ssh_service.get_ssh_config()
        config.restrict_local_network = restrict
        response = ssh_service.set_ssh_config(config)
        if response is not None:
            _, success = evaluate_ipc_response(response)
            return "Success" if success else "Failed"

        return "Success"
    except ConfigChangesNotAllowed:
        raise ToolChangesNotAllowed()


@ssh_option_mcp.tool(
    name="enable_password_authentication",
    description="Enable or disable password authentication for SSH",
)
def enable_password_authentication(enabled: bool) -> str:
    """
    Enable or disable password authentication for SSH
    """
    try:
        ssh_service = SSHService(session)
        config = ssh_service.get_ssh_config()
        config.password_authentication_enabled = enabled
        response = ssh_service.set_ssh_config(config)
        if response is not None:
            _, success = evaluate_ipc_response(response)
            return "Success" if success else "Failed"

        return "Success"
    except ConfigChangesNotAllowed:
        raise ToolChangesNotAllowed()
