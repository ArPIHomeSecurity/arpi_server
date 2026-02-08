# pylint: disable=raise-missing-from
import os

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from monitor.database import get_database_session
from server.services.base import ConfigChangesNotAllowed, ObjectNotChanged, ObjectNotFound
from server.services.sensor import ChannelConflictError, SensorService
from utils.models import ChannelTypes, SensorContactTypes, SensorEOLCount

sensor_mcp = FastMCP("ArPI - sensor service")


session = get_database_session()


@sensor_mcp.resource(
    uri="sensors://list",
    name="all",
    mime_type="application/json",
)
def get_sensors():
    """
    Retrieve all existing sensors.
    """
    sensor_service = SensorService(session)
    return [sensor.serialized for sensor in sensor_service.get_sensors()]


@sensor_mcp.tool(
    name="get_all_sensors",
)
def get_sensors_tool():
    """
    Tool to retrieve all existing sensors.
    """
    try:
        sensor_service = SensorService(session)
        return [sensor.serialized for sensor in sensor_service.get_sensors()]
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
        return sensor_service.get_sensor(sensor_id)
    except ObjectNotFound:
        raise ToolError("Sensor not found")


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
        return sensor_service.get_sensor(sensor_id)
    except ObjectNotFound:
        raise ToolError("Sensor not found")


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
    return {f"CH{i + 1:02}": i for i in range(int(channel_count))}


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
def create_sensor(
    channel: int,
    sensor_type_id: int,
    name: str,
    area_id: int,
    zone_id: int,
    description: str = None,
    enabled: bool = True,
    silent_alert: bool = False,
    monitor_period: int = 0,
    monitor_threshold: int = 100,
    channel_type: ChannelTypes = ChannelTypes.BASIC,
    sensor_contact_type: SensorContactTypes = SensorContactTypes.NO,
    sensor_eol_count: SensorEOLCount = SensorEOLCount.SINGLE,
):
    """
    Create a new sensor in the database.

    Args:
        channel: The channel number for the sensor
        sensor_type_id: The type ID of the sensor
        name: The name of the sensor
        area_id: The area ID where the sensor is located
        zone_id: The zone ID where the sensor is located
        description: Optional description of the sensor
        enabled: Whether the sensor is enabled
        silent_alert: Whether the sensor has silent alerts enabled
        monitor_period: Monitoring period for the sensor
        monitor_threshold: Monitoring threshold for the sensor
        channel_type: The channel type of the sensor
        sensor_contact_type: The contact type of the sensor
        sensor_eol_count: The end-of-line count of the sensor
    """
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
        raise ToolError("Configuration changes are not allowed currently")
    except ChannelConflictError:
        raise ToolError("Channel conflict with existing sensors")
    except AssertionError as e:
        raise ToolError(str(e))


@sensor_mcp.tool(
    name="update",
)
def update_sensor(
    sensor_id,
    name=None,
    description=None,
    channel=None,
    channel_type=None,
    sensor_contact_type=None,
    sensor_eol_count=None,
    enabled=None,
    zone_id=None,
    area_id=None,
    type_id=None,
    ui_hidden=None,
    monitor_period=None,
    monitor_threshold=None,
    silent_alert=None,
):
    """
    Update an existing sensor in the database.
    Attributes we don't want to update can be left as None.

    Args:
        sensor_id: ID of the sensor to update
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
        updated_sensor = SensorService(session).update_sensor(
            sensor_id=sensor_id, sensor_data=sensor_data
        )
        return updated_sensor.serialized
    except ConfigChangesNotAllowed:
        raise ToolError("Configuration changes are not allowed currently")
    except ObjectNotChanged:
        raise ToolError("No changes made to the sensor")
    except ObjectNotFound:
        raise ToolError("Sensor not found")
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
        updated_sensor = SensorService(session).update_sensor(
            sensor_id=sensor_id, sensor_data=sensor_data
        )
        return updated_sensor.serialized
    except ConfigChangesNotAllowed:
        raise ToolError("Configuration changes are not allowed currently")
    except ObjectNotChanged:
        raise ToolError("No changes made to the sensor")
    except ObjectNotFound:
        raise ToolError("Sensor not found")
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
        raise ToolError("Configuration changes are not allowed currently")
    except ObjectNotFound:
        raise ToolError("Sensor not found")
