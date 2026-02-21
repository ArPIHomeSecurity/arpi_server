"""
User service module to handle user-related operations.
"""

from server.services.base import BaseService
from utils.models import User


class UserService(BaseService):
    """
    Service for user management operations.
    """

    def get_users(self):
        """
        Get all users.

        Returns:
            List of User objects

        """
        return self._db_session.query(User).order_by(User.name).all()

    def get_user(self, user_id: int):
        """
        Get a specific user by ID.

        Args:
            user_id: The ID of the user to retrieve

        Returns:
            User object or None if not found

        """
        return self._db_session.query(User).get(user_id)
