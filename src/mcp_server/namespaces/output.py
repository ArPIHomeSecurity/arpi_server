# pylint: disable=raise-missing-from
from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field
from typing_extensions import Annotated

from mcp_server.errors import ToolChangesNotAllowed, ToolObjectNotFound
from monitor.database import get_database_session
from monitor.output import OUTPUT_NAMES
from server.services.area import AreaService
from server.services.base import (
    ChannelConflictError,
    ConfigChangesNotAllowed,
    InvalidConfiguration,
    ObjectNotChanged,
    ObjectNotFound,
)
from server.services.output import OutputService
from utils.models import Output, OutputTriggerType

output_mcp = FastMCP("ArPI - output service")


@output_mcp.resource(
    uri="outputs://list",
    name="all",
    mime_type="application/json",
)
def get_outputs():
    """
    Retrieve all existing outputs.
    """
    output_service = OutputService(get_database_session())
    return [output.serialized for output in output_service.get_outputs()]


@output_mcp.tool(
    name="get_all_outputs",
)
def get_outputs_tool():
    """
    Tool to retrieve all existing outputs.
    """
    output_service = OutputService(get_database_session())
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
        output_service = OutputService(get_database_session())
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
        output_service = OutputService(get_database_session())
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
async def create_output(
    ctx: Context,
    name: Annotated[
        str, Field(description="The name of the output", max_length=Output.NAME_LENGTH)
    ],
    description: Annotated[str, "The description of the output"] = "",
    channel: Annotated[int | None, "The channel number for the output"] = None,
    trigger_type: Annotated[
        OutputTriggerType, "The trigger type for the output"
    ] = OutputTriggerType.BUTTON,
    area_id: Annotated[int | None, "The area ID the output belongs to"] = None,
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
    if trigger_type == OutputTriggerType.AREA and area_id is None:
        area_service = AreaService(get_database_session())
        # TODO: use titled elicit responses once supported in the UI to avoid showing IDs to users
        result = await ctx.elicit(
            "Which area is the sensor located in?",
            response_type=[f"{area.name} ({area.id})" for area in area_service.get_areas()],
        )
        if result.action == "accept":
            area_id = int(result.data.split("(")[-1].rstrip(")"))
        else:
            area_id = None

    if channel is None:
        # skip the first output name since it's for channel 0 which is reserved for the siren
        result = await ctx.elicit(
            "Which channel is the sensor connected to?",
            response_type=[
                f"{output} ({channel_id})"
                for channel_id, output in OUTPUT_NAMES.items()
                if channel_id != 0
            ],
        )
        if result.action == "accept":
            channel = int(result.data.split("(")[-1].rstrip(")"))
        else:
            channel = None

    try:
        output_service = OutputService(get_database_session())
        new_output = output_service.create_output(
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
    except InvalidConfiguration as e:
        raise ToolError(str(e))
    except ChannelConflictError:
        raise ToolError("Channel conflict with existing outputs.")
    except AssertionError as e:
        raise ToolError(str(e))


@output_mcp.tool(
    name="update",
)
async def update_output(
    ctx: Context,
    output_id: int,
    name: Annotated[
        str, Field(description="The new name of the output", max_length=Output.NAME_LENGTH)
    ] = None,
    description: Annotated[str | None, "The new description of the output"] = None,
    channel: Annotated[int | None, "The new channel number for the output"] = None,
    trigger_type: Annotated[OutputTriggerType | None, "The new trigger type for the output"] = None,
    area_id: Annotated[int | None, "The new area ID the output belongs to"] = None,
    delay: Annotated[int | None, "The new delay before the output is activated"] = None,
    duration: Annotated[int | None, "The new duration the output remains active"] = None,
    default_state: Annotated[bool | None, "The new default state of the output"] = None,
    enabled: Annotated[bool | None, "Whether the output is enabled"] = None,
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

    if trigger_type == OutputTriggerType.AREA and area_id is None:
        area_service = AreaService(get_database_session())
        # TODO: use titled elicit responses once supported in the UI to avoid showing IDs to users
        result = await ctx.elicit(
            "Which area is the sensor located in?",
            response_type=[f"{area.name} ({area.id})" for area in area_service.get_areas()],
        )
        if result.action == "accept":
            area_id = int(result.data.split("(")[-1].rstrip(")"))
        else:
            area_id = None

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
        output_service = OutputService(get_database_session())
        updated_output = output_service.update_output(output_id, **kwargs)
        return updated_output.serialized
    except ConfigChangesNotAllowed:
        raise ToolChangesNotAllowed()
    except ObjectNotFound:
        raise ToolObjectNotFound("Output")
    except ObjectNotChanged:
        raise ToolError("No changes made to the output")
    except InvalidConfiguration as e:
        raise ToolError(str(e))
    except ChannelConflictError:
        raise ToolError("Channel conflict with existing outputs.")
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
        output_service = OutputService(get_database_session())
        output_service.delete_output(output_id)
        return "Success"
    except ConfigChangesNotAllowed:
        raise ToolChangesNotAllowed()
    except ObjectNotFound:
        raise ToolObjectNotFound("Output")


@output_mcp.tool(
    name="activate",
)
def activate_output(output_id: int):
    """
    Activate an output by its ID.
    Args:
        output_id: The ID of the output to activate
    """
    try:
        output_service = OutputService(get_database_session())
        response = output_service.activate_output(output_id)
    except ObjectNotFound:
        raise ToolObjectNotFound("Output")
    except ObjectNotChanged as error:
        raise ToolError(str(error))

    if not response or not response.get("result"):
        raise ToolError(
            response.get("message", "Failed to activate output")
            if response
            else "No response from monitoring service"
        )

    return "Success"


@output_mcp.tool(
    name="deactivate",
)
def deactivate_output(output_id: int):
    """
    Deactivate an output by its ID.
    Args:
        output_id: The ID of the output to deactivate
    """
    try:
        output_service = OutputService(get_database_session())
        response = output_service.deactivate_output(output_id)
    except ObjectNotFound:
        raise ToolObjectNotFound("Output")
    except ObjectNotChanged as error:
        raise ToolError(str(error))

    if not response or not response.get("result"):
        raise ToolError(
            response.get("message", "Failed to deactivate output")
            if response
            else "No response from monitoring service"
        )

    return "Success"
