"""
Sensor service module to handle sensor-related operations.
"""

from server.ipc import IPCClient
from server.services.base import (
    BaseService,
    ChannelConflictError,
    ConfigChangesNotAllowed,
    ObjectNotChanged,
    ObjectNotFound,
)
from utils.models import (
    Area,
    ChannelTypes,
    Sensor,
    SensorContactTypes,
    SensorEOLCount,
    SensorType,
    Zone,
)


class SensorService(BaseService):
    """
    Service for sensor management operations.
    """

    def get_sensors(self, alerting: bool = False) -> list[Sensor]:
        """
        Get all existing sensors or alerting sensors.
        """
        query = self._db_session.query(Sensor)

        if alerting:
            query = query.filter(Sensor.alert == True)

        query = query.filter(Sensor.deleted == False)

        return query.order_by(Sensor.channel.asc()).all()

    def get_sensor(self, sensor_id) -> Sensor:
        """
        Get a sensor by ID.
        """
        sensor = (
            self._db_session.query(Sensor)
            .filter(Sensor.id == sensor_id, Sensor.deleted == False)
            .first()
        )
        if not sensor:
            raise ObjectNotFound("Sensor not found")

        return sensor

    def create_sensor(
        self,
        channel: int,
        sensor_type_id: int,
        area_id: int,
        name: str,
        zone_id: int,
        description: str = None,
        enabled: bool = True,
        silent_alert: bool = False,
        monitor_period: int = None,
        monitor_threshold: int = None,
        channel_type: ChannelTypes = ChannelTypes.BASIC,
        sensor_contact_type: SensorContactTypes = SensorContactTypes.NO,
        sensor_eol_count: SensorEOLCount = SensorEOLCount.SINGLE,
    ) -> Sensor:
        """
        Create a new sensor in the database.
        """
        if not self.are_changes_allowed:
            raise ConfigChangesNotAllowed()

        area = self._db_session.query(Area).get(area_id)
        zone = self._db_session.query(Zone).get(zone_id)
        sensor_type = self._db_session.query(SensorType).get(sensor_type_id)

        new_sensor = Sensor(
            channel=channel,
            sensor_type=sensor_type,
            area=area,
            name=name,
            zone=zone,
            description=description,
            enabled=enabled,
            silent_alert=silent_alert,
            monitor_period=monitor_period,
            monitor_threshold=monitor_threshold,
            channel_type=channel_type,
            sensor_contact_type=sensor_contact_type,
            sensor_eol_count=sensor_eol_count,
        )

        if not self.validate_channel(new_sensor):
            raise ChannelConflictError("Channel conflict with existing sensors.")

        self._db_session.add(new_sensor)
        self._db_session.commit()
        self._db_session.refresh(new_sensor)

        IPCClient().update_configuration()

        return new_sensor

    def update_sensor(self, sensor_id: int, **kwargs) -> Sensor:
        """
        Update an existing sensor in the database.
        """
        if not self.are_changes_allowed:
            raise ConfigChangesNotAllowed()

        sensor = self._db_session.query(Sensor).filter(Sensor.id == sensor_id).first()
        if not sensor:
            raise ObjectNotFound("Sensor not found")

        if not sensor.update(kwargs):
            raise ObjectNotChanged("Sensor not changed")

        if not self.validate_channel(sensor):
            raise ChannelConflictError("Channel conflict with existing sensors.")

        self._db_session.commit()
        self._db_session.refresh(sensor)
        IPCClient().update_configuration()
        return sensor

    def delete_sensor(self, sensor_id) -> None:
        """
        Delete a sensor from the database.

        Args:
            sensor_id: ID of the sensor to delete
        """
        if not self.are_changes_allowed:
            raise ConfigChangesNotAllowed()

        sensor = self._db_session.query(Sensor).filter(Sensor.id == sensor_id).first()
        if not sensor:
            raise ObjectNotFound("Sensor not found")

        if sensor.deleted:
            raise ObjectNotChanged("Sensor already deleted")

        sensor.deleted = True
        self._db_session.commit()
        IPCClient().update_configuration()

    def get_sensor_types(self):
        """
        Get all sensor types.
        """
        return self._db_session.query(SensorType).all()

    def validate_channel(self, sensor: Sensor = None) -> bool:
        """
        Validate that the sensor's channel does not conflict with existing sensors.
        """
        same_channel_sensors = (
            self._db_session.query(Sensor)
            .filter(
                Sensor.id != sensor.id,
                Sensor.channel == sensor.channel,
                Sensor.deleted == False,
            )
            .all()
            if sensor
            else (self._db_session.query(Sensor).filter(Sensor.deleted == False).all())
        )

        if sensor.channel_type in [ChannelTypes.BASIC, ChannelTypes.NORMAL]:
            if same_channel_sensors:
                return False

        if sensor.channel_type in [ChannelTypes.CHANNEL_A, ChannelTypes.CHANNEL_B]:
            for existing_sensor in same_channel_sensors:
                if (
                    existing_sensor.channel_type == ChannelTypes.BASIC
                    or existing_sensor.channel_type == ChannelTypes.NORMAL
                ):
                    return False

                if sensor.channel_type == existing_sensor.channel_type:
                    return False

        return True

    def reset_references(self, sensor_id: int = None) -> None:
        """
        Reset reference values for a specific sensor or all sensors.
        """
        if not self.are_changes_allowed:
            raise ConfigChangesNotAllowed()

        if sensor_id:
            sensor = self._db_session.query(Sensor).get(sensor_id)
            if not sensor:
                raise ObjectNotFound("Sensor not found")
            sensor.reference_value = None
        else:
            sensors = self._db_session.query(Sensor).all()
            for sensor in sensors:
                sensor.reference_value = None

        self._db_session.commit()

        return IPCClient().update_configuration()

    def get_sensor_alert(self, sensor_id: int) -> bool:
        """
        Returns true when the specified sensor is in alert state,
        or if any sensor is in alert state.
        """
        query = self._db_session.query(Sensor).filter(
            Sensor.enabled == True, Sensor.alert == True, Sensor.deleted == False
        )

        if sensor_id:
            query = query.filter(Sensor.id == sensor_id)

        return query.first() is not None

    def get_sensor_error(self, sensor_id: int) -> bool:
        """
        Returns true when the specified sensor is in error state,
        or if any sensor is in error state.
        """
        query = self._db_session.query(Sensor).filter(
            Sensor.enabled == True, Sensor.error == True, Sensor.deleted == False
        )

        if sensor_id:
            query = query.filter(Sensor.id == sensor_id)

        return query.first() is not None
