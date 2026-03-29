# pylint: disable=raise-missing-from
from fastmcp import FastMCP, Context
from fastmcp.exceptions import ToolError

from mcp_server.errors import ToolChangesNotAllowed, ToolObjectNotFound
from mcp_server.models.arm import ArmType
from monitor.database import get_database_session
from server.services.area import AreaService
from server.services.base import ConfigChangesNotAllowed, ObjectNotChanged, ObjectNotFound
from server.tools import evaluate_ipc_response

area_mcp = FastMCP("ArPI - area service")




@area_mcp.resource(
    uri="areas://list",
    name="all",
    mime_type="application/json",
)
def get_areas():
    """
    Retrieve all existing areas.
    """
    area_service = AreaService(get_database_session())
    return [area.serialized for area in area_service.get_areas()]


@area_mcp.tool(
    name="get_all_areas",
)
def get_areas_tool():
    """
    Tool to retrieve all existing areas.
    """
    area_service = AreaService(get_database_session())
    return [area.serialized for area in area_service.get_areas()]


@area_mcp.resource(
    uri="areas://{area_id}",
    name="area_by_id",
    mime_type="application/json",
)
def get_area(area_id: int):
    """
    Retrieve an area by its ID.
    """
    try:
        area_service = AreaService(get_database_session())
        area = area_service.get_area(area_id)
        return area.serialized if area else None
    except ObjectNotFound:
        raise ToolObjectNotFound("Area")


@area_mcp.tool(
    name="get_area_by_id",
)
def get_area_tool(area_id: int):
    """
    Tool to retrieve an area by its ID.

    Args:
        area_id: ID of the area to retrieve
    """
    try:
        area_service = AreaService(get_database_session())
        area = area_service.get_area(area_id)
        return area.serialized if area else None
    except ObjectNotFound:
        raise ToolObjectNotFound("Area")


@area_mcp.tool(
    name="create",
)
def create_area(name: str):
    """
    Create a new area in the database.

    Args:
        name: Name of the new area
    """
    try:
        db_session = get_database_session()
        new_area = AreaService(db_session).create_area(name=name)
        return new_area.serialized
    except ConfigChangesNotAllowed:
        raise ToolChangesNotAllowed()
    except AssertionError as e:
        raise ToolError(str(e))


@area_mcp.tool(
    name="update",
)
def update_area(area_id: int, area_name: str):
    """
    Update an existing area in the database.

    Args:
        area_id: ID of the area to update
        area_name: New name for the area
    """
    try:
        area_service = AreaService(get_database_session())
        updated_area = area_service.update_area(area_id, area_name)
        return updated_area.serialized if updated_area else None
    except ConfigChangesNotAllowed:
        raise ToolChangesNotAllowed()
    except ObjectNotFound:
        raise ToolObjectNotFound("Area")
    except ObjectNotChanged:
        raise ToolError("No changes made to the area")
    except AssertionError as e:
        raise ToolError(str(e))


@area_mcp.tool(
    name="delete",
    description="Tool to delete an area by its ID",
)
def delete_area(area_id: int):
    """
    Delete an area by its ID.
    Args:
        area_id: The ID of the area to delete
    """
    try:
        area_service = AreaService(get_database_session())
        area_service.delete_area(area_id)
        return "Success"
    except ConfigChangesNotAllowed:
        raise ToolChangesNotAllowed()
    except ObjectNotFound:
        raise ToolObjectNotFound("Area")


@area_mcp.tool(
    name="arm",
    description="Tool to arm an area by its ID",
)
def arm_area(area_id: int, arm_type: ArmType, ctx: Context):
    """
    Arm an area by its ID.

    Args:
        area_id: The ID of the area to arm
        arm_type: The type of arming to perform (stay, away, mixed, disarm)
    """
    try:
        area_service = AreaService(get_database_session())
        return evaluate_ipc_response(area_service.arm(area_id, arm_type.value, ctx.client_id))
    except ConfigChangesNotAllowed:
        raise ToolChangesNotAllowed()
    except ObjectNotFound:
        raise ToolObjectNotFound("Area")


@area_mcp.tool(
    name="disarm",
    description="Tool to disarm an area by its ID",
)
def disarm_area(area_id: int, ctx: Context):
    """
    Disarm an area by its ID.

    Args:
        area_id: The ID of the area to disarm
    """
    try:
        area_service = AreaService(get_database_session())
        return evaluate_ipc_response(area_service.disarm(area_id, ctx.client_id))
    except ConfigChangesNotAllowed:
        raise ToolChangesNotAllowed()
    except ObjectNotFound:
        raise ToolObjectNotFound("Area")
