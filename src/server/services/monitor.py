"""
Monitor service module to handle monitoring-related operations.
"""

from server.ipc import IPCClient
from server.services.base import BaseService
from utils.queries import get_arm_state


class MonitoringService(BaseService):
    """
    Service for monitoring system management operations.
    """

    def get_state(self):
        """
        Get the current monitoring state.

        Returns:
            str: The current monitoring state (e.g., "armed", "disarmed", etc.)
        """
        return IPCClient().get_state()
    
    def get_arm_state(self) -> str:
        """
        Get the current arm state.

        Returns:
            str: The current arm state (e.g., "away", "stay", "disarmed")
        """
        return get_arm_state(session=self._db_session)

    def arm(self, arm_type, user_id):
        """
        Arm the monitoring system.

        Args:
            arm_type: The type of arming (e.g., "away", "stay")
            user_id: The ID of the user performing the action

        Returns:
            str: The result of the arming action (e.g., success message or error)
        """
        return IPCClient().arm(arm_type, user_id)

    def disarm(self, user_id):
        """
        Disarm the monitoring system.

        Args:
            user_id: The ID of the user performing the action

        Returns:
            str: The result of the disarming action (e.g., success message or error)
        """
        return IPCClient().disarm(user_id)
