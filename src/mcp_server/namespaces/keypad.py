# pylint: disable=raise-missing-from
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from mcp_server.errors import ToolObjectNotFound
from monitor.database import get_database_session
from server.services.base import ObjectNotChanged, ObjectNotFound
from server.services.keypad import KeypadService

keypad_mcp = FastMCP("ArPI - keypad service")


@keypad_mcp.resource(
    uri="keypads://list",
    name="all",
    description="Retrieve all existing keypads",
    mime_type="application/json",
)
def get_keypads():
    """
    Retrieve all existing keypads.
    """
    keypad_service = KeypadService(get_database_session())
    return [keypad.serialized for keypad in keypad_service.get_keypads()]


@keypad_mcp.tool(
    name="get_all_keypads",
    description="Tool to retrieve all existing keypads",
)
def get_keypads_tool():
    """
    Tool to retrieve all existing keypads.
    """
    keypad_service = KeypadService(get_database_session())
    return [keypad.serialized for keypad in keypad_service.get_keypads()]


@keypad_mcp.resource(
    uri="keypads://{keypad_id}",
    name="get_by_id",
    description="Retrieve a keypad by its ID",
    mime_type="application/json",
)
def get_keypad(keypad_id: int):
    """
    Retrieve a keypad by its ID.
    """
    try:
        keypad_service = KeypadService(get_database_session())
        return keypad_service.get_keypad(keypad_id).serialized
    except ObjectNotFound:
        raise ToolObjectNotFound("Keypad")


@keypad_mcp.tool(
    name="get_by_id",
    description="Tool to retrieve a keypad by its ID",
)
def get_keypad_tool(keypad_id: int):
    """
    Tool to retrieve a keypad by its ID.

    Args:
        keypad_id: The ID of the keypad to retrieve
    """
    try:
        keypad_service = KeypadService(get_database_session())
        return keypad_service.get_keypad(keypad_id).serialized
    except ObjectNotFound:
        raise ToolObjectNotFound("Keypad")


@keypad_mcp.resource(
    uri="keypadTypes://list",
    name="keypad_type_mappings",
    description="Retrieve all keypad types",
    mime_type="application/json",
)
def get_keypad_types():
    """
    Retrieve all keypad types.
    """
    keypad_service = KeypadService(get_database_session())
    return [kt.serialized for kt in keypad_service.get_keypad_types()]


@keypad_mcp.tool(
    name="get_keypad_type_mappings",
    description="Tool to retrieve all keypad types",
)
def get_keypad_types_tool():
    """
    Tool to retrieve all keypad types.
    """
    keypad_service = KeypadService(get_database_session())
    return [kt.serialized for kt in keypad_service.get_keypad_types()]


@keypad_mcp.tool(
    name="create",
)
def create_keypad(type_id: int, enabled: bool = True):
    """
    Create a new keypad.

    Args:
        type_id: ID of the keypad type
        enabled: Whether the keypad is enabled
    """
    keypad_service = KeypadService(get_database_session())
    return keypad_service.create_keypad(type_id=type_id, enabled=enabled)


@keypad_mcp.tool(
    name="update",
)
def update_keypad(keypad_id: int, type_id: int = None, enabled: bool = None):
    """
    Update an existing keypad.

    Args:
        keypad_id: ID of the keypad to update
        type_id: New keypad type ID
        enabled: Whether the keypad is enabled
    """
    keypad_data = {}
    if type_id is not None:
        keypad_data["type_id"] = type_id
    if enabled is not None:
        keypad_data["enabled"] = enabled

    try:
        keypad_service = KeypadService(get_database_session())
        return keypad_service.update_keypad(keypad_id=keypad_id, **keypad_data)
    except ObjectNotFound:
        raise ToolObjectNotFound("Keypad")
    except ObjectNotChanged:
        raise ToolError("No changes made to the keypad")


@keypad_mcp.tool(
    name="delete",
)
def delete_keypad(keypad_id: int):
    """
    Delete a keypad.

    Args:
        keypad_id: ID of the keypad to delete
    """
    try:
        keypad_service = KeypadService(get_database_session())
        return keypad_service.delete_keypad(keypad_id)
    except ObjectNotFound:
        raise ToolObjectNotFound("Keypad")
