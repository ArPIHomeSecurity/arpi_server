# pylint: disable=raise-missing-from
from typing import Annotated

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from mcp_server.models.zone import ArmType
from monitor.database import get_database_session
from server.services.base import (ConfigChangesNotAllowed, ObjectNotChanged,
                                  ObjectNotFound)
from server.services.zone import ZoneService
from utils.models import Zone

zone_mcp = FastMCP("ArPI - zone service")


session = get_database_session()


@zone_mcp.resource(
    uri="zones://list",
    name="all",
    description="Retrieve all existing zones",
    mime_type="application/json",
)
def get_zones():
    """
    Retrieve all existing zones.
    """
    zone_service = ZoneService(session)
    return [zone.serialized for zone in zone_service.get_zones()]


@zone_mcp.tool(
    name="get_all_zones",
    description="Tool to retrieve all existing zones",
)
def get_zones_tool():
    """
    Tool to retrieve all existing zones.
    """
    zone_service = ZoneService(session)
    return [zone.serialized for zone in zone_service.get_zones()]


@zone_mcp.resource(
    uri="zones://{zone_id}",
    name="get_by_id",
    description="Retrieve a zone by its ID",
    mime_type="application/json",
)
def get_zone(zone_id: int):
    """
    Retrieve a zone by its ID.
    """
    zone_service = ZoneService(session)
    zone = zone_service.get_zone(zone_id)
    return zone.serialized if zone else None


@zone_mcp.tool(
    name="get_by_id",
    description="Tool to retrieve a zone by its ID",
)
def get_zone_tool(zone_id: int):
    """
    Tool to retrieve a zone by its ID.
    Args:
        zone_id: The ID of the zone to retrieve
    """
    zone_service = ZoneService(session)
    zone = zone_service.get_zone(zone_id)
    return zone.serialized if zone else None


@zone_mcp.tool(
    name="create",
)
def create_zone(
    name: Annotated[
        str,
        Field(description="The new name of the zone", min_length=1, max_length=Zone.NAME_LENGTH),
    ],
    description: Annotated[
        str | None, Field(description="The new description of the zone, can be a long text")
    ] = None,
    disarmed_delay: Annotated[int | None, Field(description="The new disarmed delay", ge=0)] = None,
    away_alert_delay: Annotated[int | None, Field(description="The new away alert delay", ge=0)] = None,
    stay_alert_delay: Annotated[int | None, Field(description="The new stay alert delay", ge=0)] = None,
    away_arm_delay: Annotated[int | None, Field(description="The new away arm delay", ge=0)] = None,
    stay_arm_delay: Annotated[int | None, Field(description="The new stay arm delay", ge=0)] = None,
):
    """
    Create a new zone in the database.

    Args:
        name: The name of the new zone
        description: The description of the new zone
        disarmed_delay: The disarmed delay
        away_alert_delay: The away alert delay
        stay_alert_delay: The stay alert delay
        away_arm_delay: The away arm delay
        stay_arm_delay: The stay arm delay
    """
    try:
        new_zone = ZoneService(session).create_zone(
            name=name,
            description=description,
            disarmed_delay=disarmed_delay,
            away_alert_delay=away_alert_delay,
            stay_alert_delay=stay_alert_delay,
            away_arm_delay=away_arm_delay,
            stay_arm_delay=stay_arm_delay,
        )
        return new_zone.serialized
    except ConfigChangesNotAllowed:
        raise ToolError("Configuration changes are not allowed currently")
    except AssertionError as e:
        raise ToolError(str(e))


@zone_mcp.tool(
    name="update",
)
def update_zone(
    zone_id: int,
    name: Annotated[
        str | None,
        Field(description="The new name of the zone", min_length=1, max_length=Zone.NAME_LENGTH),
    ] = None,
    description: Annotated[
        str | None, Field(description="The new description of the zone, can be a long text")
    ] = None,
    disarmed_delay: Annotated[int | None, Field(description="The new disarmed delay", ge=0)] = None,
    away_alert_delay: Annotated[int | None, Field(description="The new away alert delay", ge=0)] = None,
    stay_alert_delay: Annotated[int | None, Field(description="The new stay alert delay", ge=0)] = None,
    away_arm_delay: Annotated[int | None, Field(description="The new away arm delay", ge=0)] = None,
    stay_arm_delay: Annotated[int | None, Field(description="The new stay arm delay", ge=0)] = None,
):
    """
    Update an existing zone in the database.
    Attributes we don't want to update can be left as None.

    Args:
        zone_id: ID of the zone to update
        name: The new name of the zone
        description: The new description of the zone
        disarmed_delay: The new disarmed delay
        away_alert_delay: The new away alert delay
        stay_alert_delay: The new stay alert delay
        away_arm_delay: The new away arm delay
        stay_arm_delay: The new stay arm delay
    """
    zone_service = ZoneService(session)

    zone_data = {
        "name": name,
        "description": description,
        "disarmed_delay": disarmed_delay,
        "away_alert_delay": away_alert_delay,
        "stay_alert_delay": stay_alert_delay,
        "away_arm_delay": away_arm_delay,
        "stay_arm_delay": stay_arm_delay,
    }

    for key in list(zone_data.keys()):
        if zone_data[key] is None:
            del zone_data[key]

    try:
        updated_zone = zone_service.update_zone(zone_id=zone_id, zone_data=zone_data)
        return updated_zone.serialized if updated_zone else None
    except ConfigChangesNotAllowed:
        raise ToolError("Configuration changes are not allowed currently")
    except ObjectNotChanged:
        raise ToolError("No changes made to the zone")
    except ObjectNotFound:
        raise ToolError("Zone not found")
    except AssertionError as e:
        raise ToolError(str(e))


@zone_mcp.tool(
    name="disable_alarm",
)
def disable_zone_alarm(zone_id: int, arm_type: ArmType):
    """
    Disable the alarm for a specific zone for a given arm type.

    Args:
        zone_id: ID of the zone to disable the alarm for
        arm_type: The arm type to set after disabling the alarm
    """
    zone_service = ZoneService(session)
    zone_data = {}
    if arm_type == ArmType.STAY:
        zone_data["stay_arm_delay"] = None
        zone_data["stay_alert_delay"] = None
    elif arm_type == ArmType.AWAY:
        zone_data["away_arm_delay"] = None
        zone_data["away_alert_delay"] = None
    elif arm_type == ArmType.DISARM:
        zone_data["disarmed_delay"] = None

    updated_zone = zone_service.update_zone(zone_id=zone_id, zone_data=zone_data)
    return updated_zone.serialized if updated_zone else None


@zone_mcp.tool(
    name="delete",
    description="Tool to delete a zone by its ID",
)
def delete_zone(zone_id: int):
    """
    Delete a zone by its ID.

    Args:
        zone_id: ID of the zone to delete
    """
    try:
        ZoneService(session).delete_zone(zone_id)
        return "Success"
    except ConfigChangesNotAllowed:
        raise ToolError("Configuration changes are not allowed currently")
    except ObjectNotFound:
        raise ToolError("Zone not found")
