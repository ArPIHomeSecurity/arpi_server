from fastmcp import FastMCP

from monitor.database import get_database_session
from server.services.user import UserService


user_mcp = FastMCP("ArPI - user service")


session = get_database_session()


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
    user_service = UserService(session)
    return [user.serialized for user in user_service.get_users()]


@user_mcp.tool(
    name="get_all_users",
)
def get_users_tool():
    """
    Tool to retrieve all users from the database.
    """
    user_service = UserService(session)
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
    user_service = UserService(session)
    user = user_service.get_user(user_id)
    return user.serialized if user else None


@user_mcp.tool(
    name="get_user_by_id",
)
def get_user_tool(user_id: int):
    """
    Tool to retrieve a specific user from the database.
    Args:
        user_id: The ID of the user to retrieve
    """
    user_service = UserService(session)
    user = user_service.get_user(user_id)
    return user.serialized if user else None


# @user_mcp.tool
# def create_user(username, email):
#     """
#     Create a new user in the database.
#     Args:
#         username: The username of the new user
#         email: The email of the new user
#     """
#     user_service = UserService(session)
#     new_user = user_service.create_user(username=username, email=email)
#     return new_user.serialized


# @user_mcp.tool
# def update_user(user_id, username=None, email=None):
#     """
#     Update an existing user in the database.
#     Args:
#         user_id: The ID of the user to update
#         username: The new username of the user (optional)
#         email: The new email of the user (optional)
#     """
#     user_service = UserService(session)
#     updated_user = user_service.update_user(user_id=user_id, username=username, email=email)
#     return updated_user.serialized


# @user_mcp.tool
# def delete_user(user_id):
#     """
#     Delete a user from the database.
#     Args:
#         user_id: The ID of the user to delete
#     """
#     user_service = UserService(session)
#     success = user_service.delete_user(user_id=user_id)
#     return "Success" if success else "Failure"
