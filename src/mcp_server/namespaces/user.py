# pylint: disable=raise-missing-from
from fastmcp import FastMCP

from mcp_server.errors import ToolChangesNotAllowed, ToolObjectNotFound
from monitor.database import get_database_session
from server.services.base import ConfigChangesNotAllowed, ObjectNotFound
from server.services.user import UserService


user_mcp = FastMCP("ArPI - user service")




@user_mcp.resource(
    uri="users://all",
    name="all",
    description="Retrieve all existing users",
    mime_type="application/json",
)
def get_users():
    """
    Retrieve all users from the database.
    """
    user_service = UserService(get_database_session())
    return [user.serialized for user in user_service.get_users()]


@user_mcp.tool(
    name="get_all_users",
)
def get_users_tool():
    """
    Tool to retrieve all users from the database.
    """
    user_service = UserService(get_database_session())
    return [user.serialized for user in user_service.get_users()]


@user_mcp.resource(
    uri="users://{user_id}",
    name="User by ID",
    description="Retrieve a specific user by their ID",
    mime_type="application/json",
)
def get_user(user_id: int):
    """
    Retrieve a specific user from the database.

    Args:
        user_id: The ID of the user to retrieve
    """
    try:
        user_service = UserService(get_database_session())
        return user_service.get_user(user_id).serialized
    except ObjectNotFound:
        raise ToolObjectNotFound("User")


@user_mcp.tool(
    name="get_user_by_id",
)
def get_user_tool(user_id: int):
    """
    Tool to retrieve a specific user from the database.

    Args:
        user_id: The ID of the user to retrieve
    """
    try:
        user_service = UserService(get_database_session())
        return user_service.get_user(user_id).serialized
    except ObjectNotFound:
        raise ToolObjectNotFound("User")


@user_mcp.tool()
def create_user(name: str, role: str, access_code: str, comment: str = None) -> dict:
    """
    Create a new user in the database.

    Args:
        name: The name of the new user
        role: The role of the new user (e.g. admin, user)
        access_code: The numeric access code for the new user (4-12 digits)
        comment: Optional comment for the user
    """
    try:
        user_service = UserService(get_database_session())
        new_user = user_service.create_user(
            name=name, role=role, access_code=access_code, comment=comment
        )
        return new_user.serialized
    except ConfigChangesNotAllowed:
        raise ToolChangesNotAllowed()


@user_mcp.tool
def update_user(
    user_id: int, name: str = None, role: str = None, comment: str = None
):
    """
    Update an existing user in the database.

    Args:
        user_id: The ID of the user to update
        name: The new name of the user (optional)
        role: The new role of the user (optional)
        comment: The new comment of the user (optional)
    """
    try:
        user_service = UserService(get_database_session())
        updated_user = user_service.update_user(
            user_id=user_id, name=name, role=role, comment=comment
        )
        return updated_user.serialized
    except ObjectNotFound:
        raise ToolObjectNotFound("User")
    except ConfigChangesNotAllowed:
        raise ToolChangesNotAllowed()


@user_mcp.tool
def delete_user(user_id: int):
    """
    Delete a user from the database.

    Args:
        user_id: The ID of the user to delete
    """
    try:
        user_service = UserService(get_database_session())
        user_service.delete_user(user_id=user_id)
        return "Success"
    except ObjectNotFound:
        raise ToolObjectNotFound("User")
    except ConfigChangesNotAllowed:
        raise ToolChangesNotAllowed()
