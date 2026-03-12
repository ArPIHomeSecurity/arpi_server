from typing import Optional

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from monitor.database import get_database_session
from server.services.arm import ArmService

arm_mcp = FastMCP("ArPI - arm service")




@arm_mcp.resource(
    uri="arms://list",
    name="all",
    mime_type="application/json",
)
def get_arms_resource():
    """
    Retrieve arm/disarm events with default parameters.
    """
    arm_service = ArmService(get_database_session())
    return arm_service.get_arms()


@arm_mcp.tool(
    name="get_all",
)
def get_arms_tool(
    has_alert: Optional[bool] = None,
    user_id: Optional[int] = None,
    keypad_id: Optional[int] = None,
    arm_type: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = 10,
    offset: int = 0,
):
    """
    Tool to retrieve arm/disarm events with optional filters.

    Args:
        has_alert: filter events that have (True) or don't have (False) an alert
        user_id: filter by the ID of the user who armed or disarmed
        keypad_id: filter events involving a keypad
        arm_type: filter by arm type; use 'disarm' for disarm-only events
        start: start date in YYYY-MM-DD format (inclusive)
        end: end date in YYYY-MM-DD format (inclusive)
        limit: maximum number of results to return (default 10)
        offset: number of results to skip (default 0)
    """
    try:
        arm_service = ArmService(get_database_session())
        return arm_service.get_arms(
            has_alert=has_alert,
            user_id=user_id,
            keypad_id=keypad_id,
            arm_type=arm_type,
            start=start,
            end=end,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise ToolError(str(exc)) from exc


@arm_mcp.tool(
    name="get_arms_count",
)
def get_arms_count_tool(
    has_alert: Optional[bool] = None,
    user_id: Optional[int] = None,
    keypad_id: Optional[int] = None,
    arm_type: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
):
    """
    Tool to get the count of arm/disarm events matching the given filters.

    Args:
        has_alert: filter events that have (True) or don't have (False) an alert
        user_id: filter by the ID of the user who armed or disarmed
        keypad_id: filter events involving a keypad
        arm_type: filter by arm type; use 'disarm' for disarm-only events
        start: start date in YYYY-MM-DD format (inclusive)
        end: end date in YYYY-MM-DD format (inclusive)
    """
    try:
        arm_service = ArmService(get_database_session())
        return arm_service.get_arms_count(
            has_alert=has_alert,
            user_id=user_id,
            keypad_id=keypad_id,
            arm_type=arm_type,
            start=start,
            end=end,
        )
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
