# pylint: disable=raise-missing-from
from dataclasses import asdict
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from mcp_server.errors import ToolChangesNotAllowed
from monitor.config.models import SMTPConfig
from monitor.database import get_database_session
from server.services.base import ConfigChangesNotAllowed
from server.services.option.smtp import SMTPService, TestingNotAllowed
from server.tools import evaluate_ipc_response

smtp_option_mcp = FastMCP("ArPI - SMTP configuration service")


session = get_database_session()


@smtp_option_mcp.tool(
    name="get_config",
    description="Get the current SMTP configuration",
)
def get_config() -> dict:
    """
    Get the current SMTP configuration
    """
    smtp_service = SMTPService(session)
    config = smtp_service.get_smtp_config()
    return asdict(config)


@smtp_option_mcp.tool(
    name="set_config",
    description="Set the SMTP configuration",
)
def set_config(config: SMTPConfig) -> str:
    """
    Set the SMTP configuration
    """
    try:
        smtp_service = SMTPService(session)
        response = smtp_service.set_smtp_config(config)

        if response is not None:
            _, success = evaluate_ipc_response(response)
            return "Success" if success else "Failed"

        return "Success"
    except ConfigChangesNotAllowed:
        raise ToolChangesNotAllowed()


@smtp_option_mcp.tool(
    name="test_email",
    description="Send a test email",
)
def test_email() -> str:
    """
    Send a test email
    """
    try:
        smtp_service = SMTPService(session)
        response = smtp_service.test_email()
        if response is not None:
            _, success = evaluate_ipc_response(response)
            return "Success" if success else "Failed"

        return "Success"
    except TestingNotAllowed:
        raise ToolError("Testing is not allowed currently.")
