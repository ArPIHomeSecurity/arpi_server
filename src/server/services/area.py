"""
Area service module to handle area-related operations.
"""

from server.ipc import IPCClient
from server.services.base import (
    BaseService,
    ConfigChangesNotAllowed,
    ObjectNotChanged,
    ObjectNotFound,
)
from utils.models import Area


class AreaService(BaseService):
    """
    Service for Area management operations.
    """

    def get_areas(self) -> list[Area]:
        """
        Get all areas.

        Returns:
            List of Area objects
        """
        query = self._db_session.query(Area)

        return query.order_by(Area.name.asc()).filter(Area.deleted == False).all()  # noqa: E712

    def get_area(self, area_id: int) -> Area:
        """
        Get an area by its ID.

        Args:
            area_id: ID of the area to retrieve

        Returns:
            Area object or None if not found
        """
        area = (
            self._db_session.query(Area).filter(Area.id == area_id, Area.deleted == False).first()  # noqa: E712
        )
        if not area:
            raise ObjectNotFound("Area not found")

        return area

    def create_area(
        self,
        name: str,
    ) -> Area:
        """
        Create a new area in the database.

        Args:
            name: The name of the new area
            description: Optional description of the area

        Returns:
            The newly created Area object
        """
        if not self.are_changes_allowed:
            raise ConfigChangesNotAllowed()

        new_area = Area(name=name)
        self._db_session.add(new_area)
        self._db_session.commit()
        return new_area

    def update_area(self, area_id: int, area_name: str) -> Area:
        """
        Update an existing area in the database.

        Args:
            area_id: ID of the area to update
            area_name: New name for the area

        Returns:
            The updated Area object or None if not found
        """
        if not self.are_changes_allowed:
            raise ConfigChangesNotAllowed()

        area = self.get_area(area_id)
        if not area:
            raise ObjectNotFound("Area not found")

        area.name = area_name
        self._db_session.commit()
        return area

    def delete_area(self, area_id: int) -> None:
        """
        Delete an area by its ID if it has no associated sensors.

        Args:
            area_id: ID of the area to delete
        Returns:
            True if deletion was successful, False otherwise
        """
        if not self.are_changes_allowed:
            raise ConfigChangesNotAllowed()

        area = self.get_area(area_id)
        if not area:
            raise ObjectNotFound("Area not found")

        if not area.can_be_deleted():
            raise ObjectNotChanged("Area cannot be deleted because it has associated sensors")

        if area.deleted:
            raise ObjectNotChanged("Area already deleted")

        area.deleted = True
        self._db_session.commit()

    def arm(self, area_id: int, arm_type: str, user_id: int) -> Area:
        """
        Arm an area by its ID.

        Args:
            area_id: ID of the area to arm
            arm_type: Type of arming
            user_id: ID of the user performing the arming

        Returns:
            The armed Area object or None if not found
        """
        area = self.get_area(area_id)
        if not area:
            raise ObjectNotFound("Area not found")

        return IPCClient().arm(
            arm_type=arm_type,
            user_id=user_id,
            area_id=area_id,
        )

    def disarm(self, area_id: int, user_id: int) -> Area:
        """
        Disarm an area by its ID.

        Args:
            area_id: ID of the area to disarm
            user_id: ID of the user performing the arming

        Returns:
            The armed Area object or None if not found
        """
        area = self.get_area(area_id)
        if not area:
            raise ObjectNotFound("Area not found")

        return IPCClient().disarm(
            user_id=user_id,
            area_id=area_id,
        )
