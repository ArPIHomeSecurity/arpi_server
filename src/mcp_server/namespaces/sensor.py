# pylint: disable=raise-missing-from
import os
from typing import Annotated

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from mcp_server.errors import ToolChangesNotAllowed, ToolObjectNotFound
from monitor.database import get_database_session
from server.services.area import AreaService
from server.services.base import ConfigChangesNotAllowed, ObjectNotChanged, ObjectNotFound
from server.services.sensor import ChannelConflictError, SensorService
from server.services.zone import ZoneService
from utils.models import ChannelTypes, Sensor, SensorContactTypes, SensorEOLCount

sensor_mcp = FastMCP("ArPI - sensor service")


session = get_database_session()


@sensor_mcp.resource(
    uri="sensors://list/{alerting_only}",
    name="all",
    mime_type="application/json",
)
def get_sensors(alerting_only: bool):
    """
    Retrieve all existing sensors.
    """
    sensor_service = SensorService(session)
    return [sensor.serialized for sensor in sensor_service.get_sensors(alerting=alerting_only)]


@sensor_mcp.tool(
    name="get_all_sensors",
)
def get_sensors_tool(alerting_only: bool = False):
    """
    Tool to retrieve all existing sensors.
    """
    try:
        sensor_service = SensorService(session)
        return [sensor.serialized for sensor in sensor_service.get_sensors(alerting=alerting_only)]
    except ObjectNotFound:
        raise ToolError("No sensors found")


@sensor_mcp.resource(
    uri="sensors://{sensor_id}",
    name="sensor_by_id",
    mime_type="application/json",
)
def get_sensor(sensor_id: int):
    """
    Retrieve a specific sensor by ID.
    """
    try:
        sensor_service = SensorService(session)
        sensor = sensor_service.get_sensor(sensor_id)
        return sensor.serialized if sensor else None
    except ObjectNotFound:
        raise ToolObjectNotFound("Sensor")


@sensor_mcp.tool(
    name="get_sensor_by_id",
)
def get_sensor_tool(sensor_id: int):
    """
    Tool to retrieve a specific sensor by ID.

    Args:
        sensor_id: The ID of the sensor to retrieve
    """
    try:
        sensor_service = SensorService(session)
        sensor = sensor_service.get_sensor(sensor_id)
        return sensor.serialized if sensor else None
    except ObjectNotFound:
        raise ToolObjectNotFound("Sensor")


@sensor_mcp.resource(
    uri="channels://list",
    name="channel_mappings",
    mime_type="application/json",
)
def get_channel_mappings():
    """
    Retrieve mapping of channel names to their IDs.
    """
    channel_count = os.environ["INPUT_NUMBER"]
    return [{"name": f"CH{i + 1:02}", "id": i} for i in range(int(channel_count))]


@sensor_mcp.tool(
    name="get_channel_mappings",
)
def get_channel_mappings_tool():
    """
    Tool to retrieve mapping of channel names to their IDs.
    """
    channel_count = os.environ["INPUT_NUMBER"]
    return [{"name": f"CH{i + 1:02}", "id": i} for i in range(int(channel_count))]


@sensor_mcp.resource(
    uri="sensorTypes://list",
    name="sensor_type_mappings",
    mime_type="application/json",
)
def get_sensor_type_mappings():
    """
    Retrieve mapping of sensor type names to their IDs.
    """
    sensor_service = SensorService(session)
    return {sensor_type.name: sensor_type.id for sensor_type in sensor_service.get_sensor_types()}


@sensor_mcp.tool(
    name="get_sensor_type_mappings",
)
def get_sensor_type_mappings_tool():
    """
    Tool to retrieve mapping of sensor type names to their IDs.
    """
    try:
        sensor_service = SensorService(session)
        return {
            sensor_type.name: sensor_type.id for sensor_type in sensor_service.get_sensor_types()
        }
    except ObjectNotFound:
        raise ToolError("No sensor types found")


@sensor_mcp.resource(
    uri="channelTypes://list",
    name="channel_type_names",
    mime_type="application/json",
)
def get_channel_type_names():
    """
    Retrieve list of channel type names.
    """
    return [
        f"Name: {channel_type.name} - value: {channel_type.value}" for channel_type in ChannelTypes
    ]


@sensor_mcp.resource(
    uri="sensorContactTypes://list",
    name="sensor_contact_type_names",
    mime_type="application/json",
)
def get_sensor_contact_type_names():
    """
    Retrieve list of sensor contact type names.
    """
    return [
        f"Name: {sensor_contact_type.name} - value: {sensor_contact_type.value}"
        for sensor_contact_type in SensorContactTypes
    ]


@sensor_mcp.resource(
    uri="sensorEOLCounts://list",
    name="sensor_eol_count_names",
    mime_type="application/json",
)
def get_sensor_eol_count_names():
    """
    Retrieve list of sensor end-of-line count names.
    """
    return [
        f"Name: {sensor_eol_count.name} - value: {sensor_eol_count.value}"
        for sensor_eol_count in SensorEOLCount
    ]


@sensor_mcp.tool(
    name="create",
)
async def create_sensor(
    ctx: Context,
    name: Annotated[
        str, Field(description="The name of the sensor", max_length=Sensor.NAME_LENGTH)
    ],
    description: Annotated[str, "Optional description of the sensor"] = "",
    enabled: Annotated[
        bool, "Whether the sensor is enabled and can participate in monitoring"
    ] = True,
    silent_alert: Annotated[bool, "Whether the sensor has silent alerts enabled"] = False,
    monitor_period: Annotated[
        int | None, Field(description="Monitoring period for the sensor", gt=0)
    ] = None,
    monitor_threshold: Annotated[int, "Monitoring threshold for the sensor"] = 100,
    channel_type: Annotated[ChannelTypes, "The channel type of the sensor"] = ChannelTypes.BASIC,
    sensor_contact_type: Annotated[
        SensorContactTypes, "The contact type of the sensor"
    ] = SensorContactTypes.NO,
    sensor_eol_count: Annotated[
        SensorEOLCount, "The end-of-line count of the sensor"
    ] = SensorEOLCount.SINGLE,
    area_id: Annotated[
        int | None, "The ID of the area where the sensor is located (elicited if not provided)"
    ] = None,
    zone_id: Annotated[
        int | None, "The ID of the zone where the sensor is located (elicited if not provided)"
    ] = None,
    sensor_type_id: Annotated[
        int | None, "The ID of the sensor type (elicited if not provided)"
    ] = None,
    channel: Annotated[
        int | None, "The channel number the sensor is connected to (elicited if not provided)"
    ] = None,
):
    """
    Create a new sensor in the database.

    Args:
        name: The name of the sensor
        description: Optional description of the sensor
        enabled: Whether the sensor is enabled
        silent_alert: Whether the sensor has silent alerts enabled
        monitor_period: Monitoring period for the sensor
        monitor_threshold: Monitoring threshold for the sensor
        channel_type: The channel type of the sensor
        sensor_contact_type: The contact type of the sensor
        sensor_eol_count: The end-of-line count of the sensor

        area_id: The ID of the area where the sensor is located (will be elicited if not provided)
        zone_id: The ID of the zone where the sensor is located (will be elicited if not provided)
        sensor_type_id: The ID of the sensor type (will be elicited if not provided)
        channel: The channel number the sensor is connected to (will be elicited if not provided)
    """
    if area_id is None:
        area_service = AreaService(session)
        # TODO: use titled elicit responses once supported in the UI to avoid showing IDs to users
        result = await ctx.elicit(
            "Which area is the sensor located in?",
            response_type=[f"{area.name} ({area.id})" for area in area_service.get_areas()],
        )
        if result.action == "accept":
            area_id = int(result.data.split("(")[-1].rstrip(")"))
        else:
            area_id = None

    if zone_id is None:
        zone_service = ZoneService(session)
        result = await ctx.elicit(
            "Which zone is the sensor located in?",
            response_type=[f"{zone.name} ({zone.id})" for zone in zone_service.get_zones()],
        )
        if result.action == "accept":
            zone_id = int(result.data.split("(")[-1].rstrip(")"))
        else:
            zone_id = None

    if sensor_type_id is None:
        sensor_service = SensorService(session)
        result = await ctx.elicit(
            "What type of sensor is this?",
            response_type=[
                f"{sensor_type.name} ({sensor_type.id})"
                for sensor_type in sensor_service.get_sensor_types()
            ],
        )
        if result.action == "accept":
            sensor_type_id = int(result.data.split("(")[-1].rstrip(")"))
        else:
            sensor_type_id = None

    if channel is None:
        result = await ctx.elicit(
            "Which channel is the sensor connected to?",
            response_type=[f"CH{i + 1:02} ({i})" for i in range(int(os.environ["INPUT_NUMBER"]))],
        )
        if result.action == "accept":
            channel = int(result.data.split("(")[-1].rstrip(")"))
        else:
            channel = None

    if area_id is None or zone_id is None or sensor_type_id is None or channel is None:
        raise ToolError("Missing required information to create sensor")

    try:
        new_sensor = SensorService(session).create_sensor(
            channel=channel,
            sensor_type_id=sensor_type_id,
            area_id=area_id,
            name=name,
            zone_id=zone_id,
            description=description,
            enabled=enabled,
            silent_alert=silent_alert,
            monitor_period=monitor_period,
            monitor_threshold=monitor_threshold,
            channel_type=channel_type,
            sensor_contact_type=sensor_contact_type,
            sensor_eol_count=sensor_eol_count,
        )
        return new_sensor.serialized
    except ConfigChangesNotAllowed:
        raise ToolChangesNotAllowed()
    except ChannelConflictError:
        raise ToolError("Channel conflict with existing sensors")
    except AssertionError as e:
        raise ToolError(str(e))


@sensor_mcp.tool(
    name="update",
)
def update_sensor(
    sensor_id,
    name: Annotated[
        str, Field(description="The new name of the sensor", max_length=Sensor.NAME_LENGTH)
    ] = None,
    description: Annotated[str, Field(description="The new description of the sensor")] = None,
    channel: Annotated[int, Field(description="The new channel number for the sensor")] = None,
    channel_type: Annotated[str, Field(description="The new channel type of the sensor")] = None,
    sensor_contact_type: Annotated[
        str, Field(description="The new contact type of the sensor")
    ] = None,
    sensor_eol_count: Annotated[
        int, Field(description="The new end-of-line count of the sensor")
    ] = None,
    enabled: Annotated[bool, Field(description="Whether the sensor is enabled")] = None,
    zone_id: Annotated[
        int, Field(description="The new zone ID where the sensor is located")
    ] = None,
    area_id: Annotated[
        int, Field(description="The new area ID where the sensor is located")
    ] = None,
    type_id: Annotated[int, Field(description="The new type ID of the sensor")] = None,
    ui_hidden: Annotated[bool, Field(description="Whether the sensor is hidden in the UI")] = None,
    monitor_period: Annotated[
        int, Field(description="The new monitoring period for the sensor")
    ] = None,
    monitor_threshold: Annotated[
        int, Field(description="The new monitoring threshold for the sensor")
    ] = None,
    silent_alert: Annotated[
        bool, Field(description="Whether the sensor has silent alerts enabled")
    ] = None,
):
    """
    Update an existing sensor in the database.
    Attributes we don't want to update can be left as None.

    Args:
        sensor_id: The ID of the sensor to update
        name: The new name of the sensor
        description: The new description of the sensor
        channel: The new channel number for the sensor
        channel_type: The new channel type of the sensor
        sensor_contact_type: The new contact type of the sensor
        sensor_eol_count: The new end-of-line count of the sensor
        enabled: Whether the sensor is enabled
        zone_id: The new zone ID where the sensor is located
        area_id: The new area ID where the sensor is located
        type_id: The new type ID of the sensor
        ui_hidden: Whether the sensor is hidden in the UI
        monitor_period: The new monitoring period for the sensor
        monitor_threshold: The new monitoring threshold for the sensor
        silent_alert: Whether the sensor has silent alerts enabled
    """
    sensor_data = {}
    params = {
        "name": name,
        "description": description,
        "channel": channel,
        "channel_type": channel_type,
        "sensor_contact_type": sensor_contact_type,
        "sensor_eol_count": sensor_eol_count,
        "zone_id": zone_id,
        "area_id": area_id,
        "type_id": type_id,
        "enabled": enabled,
        "ui_hidden": ui_hidden,
        "monitor_period": monitor_period,
        "monitor_threshold": monitor_threshold,
        "silent_alert": silent_alert,
    }

    for key, value in params.items():
        if value is not None:
            sensor_data[key] = value

    try:
        updated_sensor = SensorService(session).update_sensor(sensor_id=sensor_id, **sensor_data)
        return updated_sensor.serialized
    except ConfigChangesNotAllowed:
        raise ToolChangesNotAllowed()
    except ObjectNotChanged:
        raise ToolError("No changes made to the sensor")
    except ObjectNotFound:
        raise ToolObjectNotFound("Sensor")
    except ChannelConflictError:
        raise ToolError("Channel conflict with existing sensors")
    except AssertionError as e:
        raise ToolError(str(e))


@sensor_mcp.tool(
    name="disable_custom_sensitivity",
)
def disable_sensor_custom_sensitivity(sensor_id: int):
    """
    Disable custom sensitivity settings for a specific sensor.

    Args:
        sensor_id: ID of the sensor to disable custom sensitivity for
    """
    sensor_data = {
        "monitor_period": None,
        "monitor_threshold": 100,
    }

    try:
        updated_sensor = SensorService(session).update_sensor(sensor_id=sensor_id, **sensor_data)
        return updated_sensor.serialized
    except ConfigChangesNotAllowed:
        raise ToolChangesNotAllowed()
    except ObjectNotChanged:
        raise ToolError("No changes made to the sensor")
    except ObjectNotFound:
        raise ToolObjectNotFound("Sensor")
    except ChannelConflictError:
        raise ToolError("Channel conflict with existing sensors")


@sensor_mcp.tool(
    name="delete",
)
def delete_sensor(sensor_id):
    """
    Delete a sensor from the database.
    """
    try:
        SensorService(session).delete_sensor(sensor_id=sensor_id)
        return "Success"
    except ConfigChangesNotAllowed:
        raise ToolChangesNotAllowed()
    except ObjectNotFound:
        raise ToolObjectNotFound("Sensor")
