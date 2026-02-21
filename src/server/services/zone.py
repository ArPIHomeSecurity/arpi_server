"""
Zone service module to handle zone-related operations.
"""

from server.ipc import IPCClient
from server.services.base import BaseService, ConfigChangesNotAllowed, ObjectNotChanged, ObjectNotFound
from utils.models import Zone


class ZoneService(BaseService):
    """
    Service for Zone management operations.
    """

    def get_zones(self) -> list[Zone]:
        """
        Get all zones.

        Returns:
            List of Zone objects
        """
        query = self._db_session.query(Zone)

        return query.order_by(Zone.name.asc()).all()

    def get_zone(self, zone_id: int) -> Zone:
        """
        Get a zone by its ID.

        Args:
            zone_id: ID of the zone to retrieve

        Returns:
            Zone object or None if not found
        """
        zone = self._db_session.query(Zone).get(zone_id)
        if not zone:
            raise ObjectNotFound("Zone not found")
        
        return zone

    def create_zone(
        self,
        name: str,
        description: str = "",
        disarmed_delay: int = None,
        away_alert_delay: int = 0,
        stay_alert_delay: int = 0,
        away_arm_delay: int = 0,
        stay_arm_delay: int = 0,
    ) -> Zone:
        """
        Create a new zone in the database.

        Args:
            name: The name of the new zone
            description: Optional description of the zone

        Returns:
            The newly created Zone object
        """
        if not self.are_changes_allowed:
            raise ConfigChangesNotAllowed()

        new_zone = Zone(
            name=name,
            description=description,
            disarmed_delay=disarmed_delay,
            away_alert_delay=away_alert_delay,
            stay_alert_delay=stay_alert_delay,
            away_arm_delay=away_arm_delay,
            stay_arm_delay=stay_arm_delay,
        )
        self._db_session.add(new_zone)
        self._db_session.commit()
        IPCClient().update_configuration()
        return new_zone

    def update_zone(self, zone_id: int, **kwargs) -> Zone:
        """
        Update an existing zone in the database.

        Args:
            zone_id: ID of the zone to update
            zone_data: Fields to update with their new values

        Returns:
            The updated Zone object
        """
        if not self.are_changes_allowed:
            raise ConfigChangesNotAllowed()

        zone = self.get_zone(zone_id)
        if not zone:
            raise ObjectNotFound("Zone not found")

        if not zone.update(kwargs):
            raise ObjectNotChanged("Zone not changed")

        self._db_session.commit()
        self._db_session.refresh(zone)
        IPCClient().update_configuration()
        return zone

    def delete_zone(self, zone_id: int) -> None:
        """
        Delete a zone from the database.

        Args:
            zone_id: ID of the zone to delete
        Returns:
            
        """
        if not self.are_changes_allowed:
            raise ConfigChangesNotAllowed()

        zone = self.get_zone(zone_id)
        if not zone:
            raise ObjectNotFound("Zone not found")

        if not zone.can_be_deleted():
            raise ObjectNotChanged("Zone cannot be deleted because it has associated sensors")

        self._db_session.delete(zone)
        self._db_session.commit()
        IPCClient().update_configuration()
