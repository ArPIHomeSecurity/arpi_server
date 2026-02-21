"""
Base service module providing common functionality for all services.
"""

from utils.constants import ARM_DISARM
from utils.queries import get_arm_state


class ObjectNotFound(Exception):
    """Thrown when object not found in the database."""


class ObjectNotChanged(Exception):
    """Raised when an object is not changed."""


class TestingNotAllowed(Exception):
    """Raised when testing is not allowed."""

    def __init__(self):
        super().__init__("Testing is not allowed currently.")

class ConfigChangesNotAllowed(Exception):
    """Exception raised when configuration changes are not allowed."""

    def __init__(self):
        super().__init__("Changes are not allowed currently.")


class BaseService:
    """
    Base service class providing common functionality for all services.
    """

    def __init__(self, db_session):
        self._db_session = db_session

    @property
    def are_changes_allowed(self):
        """
        Check if changes are allowed in the current context.

        Returns:
            bool: True if changes are allowed, False otherwise.
        """
        arm_state = get_arm_state(session=self._db_session)
        return arm_state == ARM_DISARM

    @property
    def is_testing_allowed(self):
        """
        Check if testing is allowed in the current context.

        Returns:
            bool: True if testing is allowed, False otherwise.
        """
        arm_state = get_arm_state(session=self._db_session)
        return arm_state == ARM_DISARM
