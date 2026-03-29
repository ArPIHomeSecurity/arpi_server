"""
User service module to handle user-related operations.
"""

from server.services.base import BaseService, ConfigChangesNotAllowed, ObjectNotFound
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
        user = self._db_session.query(User).get(user_id)
        if not user:
            raise ObjectNotFound("User not found")
        return user

    def create_user(self, name: str, role: str, access_code: str, comment: str = None) -> User:
        """
        Create a new user in the database.

        Args:
            name: The name of the new user
            role: The role of the new user
            access_code: The access code for the new user
            comment: Optional comment for the user

        Returns:
            The newly created User object
        """
        if not self.are_changes_allowed:
            raise ConfigChangesNotAllowed()

        new_user = User(name=name, role=role, access_code=access_code, comment=comment)
        self._db_session.add(new_user)
        self._db_session.commit()
        return new_user

    def update_user(
        self,
        user_id: int,
        name: str = None,
        email: str = None,
        role: str = None,
        comment: str = None,
    ) -> User:
        """
        Update an existing user in the database.

        Args:
            user_id: The ID of the user to update
            name: The new name for the user (optional)
            email: The new email for the user (optional)
            role: The new role for the user (optional)
            comment: The new comment for the user (optional)

        Returns:
            The updated User object
        """
        if not self.are_changes_allowed:
            raise ConfigChangesNotAllowed()

        user = self.get_user(user_id)

        if name is not None:
            user.name = name
        if email is not None:
            user.email = email
        if role is not None:
            user.role = role
        if comment is not None:
            user.comment = comment

        self._db_session.commit()
        return user

    def delete_user(self, user_id: int) -> None:
        """
        Delete a user from the database.

        Args:
            user_id: The ID of the user to delete
        """
        if not self.are_changes_allowed:
            raise ConfigChangesNotAllowed()

        user = self.get_user(user_id)
        self._db_session.delete(user)
        self._db_session.commit()
