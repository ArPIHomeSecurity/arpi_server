from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from server.services.clock import ClockService

clock_mcp = FastMCP("ArPI - clock service")


@clock_mcp.resource(
    uri="clock://info",
    name="info",
    description="Retrieve current clock and uptime information",
    mime_type="application/json",
)
def get_clock_resource():
    """
    Retrieve current clock and uptime information.
    """
    return ClockService().get_clock_info()


@clock_mcp.tool(
    name="get_clock_info",
)
def get_clock_tool():
    """
    Tool to retrieve current clock information including timezone, system time,
    hardware clock, NTP time, and system/service uptimes.
    """
    return ClockService().get_clock_info()


@clock_mcp.tool(
    name="set_clock",
)
def set_clock_tool(timezone: str = None, datetime: str = None):
    """
    Tool to set the system timezone and/or datetime.

    Args:
        timezone: Timezone name (e.g. 'Europe/Budapest')
        datetime: Datetime string to set (e.g. '2026-03-14 12:00:00')
    """
    settings = {}
    if timezone is not None:
        settings["timezone"] = timezone
    if datetime is not None:
        settings["datetime"] = datetime

    if not settings:
        raise ToolError("At least one of 'timezone' or 'datetime' must be provided.")

    response = ClockService().set_clock(settings)
    if not response or not response.get("result"):
        raise ToolError(
            response.get("message", "Failed to set clock")
            if response
            else "No response from monitoring service"
        )
    return "Success"
