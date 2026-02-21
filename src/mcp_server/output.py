# pylint: disable=raise-missing-from
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field
from typing_extensions import Annotated

from mcp_server.errors import ToolChangesNotAllowed, ToolObjectNotFound
from monitor.database import get_database_session
from server.services.base import ConfigChangesNotAllowed, ObjectNotChanged, ObjectNotFound
from server.services.output import OutputService
from utils.models import Output, OutputTriggerType

output_mcp = FastMCP("ArPI - output service")


session = get_database_session()


@output_mcp.resource(
    uri="outputs://list",
    name="all",
    mime_type="application/json",
)
def get_outputs():
    """
    Retrieve all existing outputs.
    """
    output_service = OutputService(session)
    return [output.serialized for output in output_service.get_outputs()]


@output_mcp.tool(
    name="get_all_outputs",
)
def get_outputs_tool():
    """
    Tool to retrieve all existing outputs.
    """
    output_service = OutputService(session)
    return [output.serialized for output in output_service.get_outputs()]


@output_mcp.resource(
    uri="outputs://{output_id}",
    name="output_by_id",
    mime_type="application/json",
)
def get_output_by_id(output_id: int):
    """
    Retrieve an output by its ID.
    """
    try:
        output_service = OutputService(session)
        output = output_service.get_output_by_id(output_id)
        return output.serialized if output else None
    except ObjectNotFound:
        raise ToolObjectNotFound("Output")


@output_mcp.tool(
    name="get_output_by_id",
)
def get_output_tool(output_id: int):
    """
    Tool to retrieve an output by its ID.
    Args:
        output_id: The ID of the output to retrieve
    """
    try:
        output_service = OutputService(session)
        output = output_service.get_output_by_id(output_id)
        return output.serialized if output else None
    except ObjectNotFound:
        raise ToolObjectNotFound("Output")


@output_mcp.resource(
    uri="outputsTriggerTypes://list",
    name="output_trigger_type_names",
    description="Retrieve list of output trigger type names",
    mime_type="application/json",
)
def get_output_trigger_type_names():
    """
    Retrieve list of output trigger type names.
    """
    return [
        f"Name: {trigger_type.name} - value: {trigger_type.value}"
        for trigger_type in OutputTriggerType
    ]


@output_mcp.tool(
    name="create",
)
def create_output(
    name: Annotated[str, Field(description="The name of the output", length=Output.NAME_LENGTH)],
    description: Annotated[str, "The description of the output"] = "",
    channel: Annotated[int, "The channel number for the output"] = 0,
    trigger_type: Annotated[
        OutputTriggerType, "The trigger type for the output"
    ] = OutputTriggerType.BUTTON,
    area_id: Annotated[int, "The area ID the output belongs to"] = None,
    delay: Annotated[int, "The delay before the output is activated"] = 0,
    duration: Annotated[int, "The duration the output remains active"] = 0,
    default_state: Annotated[bool, "The default state of the output"] = False,
    enabled: Annotated[bool, "Whether the output is enabled"] = True,
):
    """
    Create a new output in the database.
    Args:
        name: The name of the output
        description: The description of the output
        channel: The channel number for the output
        trigger_type: The trigger type for the output
        area_id: The area ID the output belongs to
        delay: The delay before the output is activated
        duration: The duration the output remains active
        default_state: The default state of the output
        enabled: Whether the output is enabled
    """
    try:
        new_output = OutputService(session).create_output(
            name=name,
            description=description,
            channel=channel,
            trigger_type=trigger_type,
            area_id=area_id,
            delay=delay,
            duration=duration,
            default_state=default_state,
            enabled=enabled,
        )
        return new_output.serialized
    except ConfigChangesNotAllowed:
        raise ToolChangesNotAllowed()
    except AssertionError as e:
        raise ToolError(str(e))


@output_mcp.tool(
    name="update",
)
def update_output(
    output_id: int,
    name: Annotated[
        str, Field(description="The new name of the output", length=Output.NAME_LENGTH)
    ] = None,
    description: Annotated[str, "The new description of the output"] = None,
    channel: Annotated[int, "The new channel number for the output"] = None,
    trigger_type: Annotated[OutputTriggerType, "The new trigger type for the output"] = None,
    area_id: Annotated[int, "The new area ID the output belongs to"] = None,
    delay: Annotated[int, "The new delay before the output is activated"] = None,
    duration: Annotated[int, "The new duration the output remains active"] = None,
    default_state: Annotated[bool, "The new default state of the output"] = None,
    enabled: Annotated[bool, "Whether the output is enabled"] = None,
):
    """
    Update an existing output in the database.
    Args:
        output_id: The ID of the output to update
        name: The new name of the output (optional)
        description: The new description of the output (optional)
        channel: The new channel number for the output (optional)
        trigger_type: The new trigger type for the output (optional)
        area_id: The new area ID the output belongs to (optional)
        delay: The new delay before the output is activated (optional)
        duration: The new duration the output remains active (optional)
        default_state: The new default state of the output (optional)
        enabled: Whether the output is enabled (optional)
    """
    kwargs = {}
    params = {
        "name": name,
        "description": description,
        "channel": channel,
        "trigger_type": trigger_type,
        "area_id": area_id,
        "delay": delay,
        "duration": duration,
        "default_state": default_state,
        "enabled": enabled,
    }

    for key, value in params.items():
        if value is not None:
            kwargs[key] = value

    try:
        output_service = OutputService(session)
        updated_output = output_service.update_output(output_id, **kwargs)
        return updated_output.serialized
    except ConfigChangesNotAllowed:
        raise ToolChangesNotAllowed()
    except ObjectNotFound:
        raise ToolObjectNotFound("Output")
    except ObjectNotChanged:
        raise ToolError("No changes made to the output")
    except AssertionError as e:
        raise ToolError(str(e))


@output_mcp.tool(
    name="delete",
)
def delete_output(output_id: int):
    """
    Delete an output by its ID.
    Args:
        output_id: The ID of the output to delete
    """
    try:
        OutputService(session).delete_output(output_id)
        return "Success"
    except ConfigChangesNotAllowed:
        raise ToolChangesNotAllowed()
    except ObjectNotFound:
        raise ToolObjectNotFound("Output")
