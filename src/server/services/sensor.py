"""
Sensor service module to handle sensor-related operations.
"""

from sqlalchemy import select

from server.ipc import IPCClient
from server.services.base import (
    BaseService,
    ChannelConflictError,
    ConfigChangesNotAllowed,
    InvalidSensorSource,
    ObjectNotChanged,
    ObjectNotFound,
    ZigbeeBindingConflictError,
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
        statement = select(Sensor)

        if alerting:
            statement = statement.where(Sensor.alert == True)

        statement = statement.where(Sensor.deleted == False)

        return self._db_session.scalars(statement.order_by(Sensor.channel.asc())).all()

    def get_sensor(self, sensor_id) -> Sensor:
        """
        Get a sensor by ID.
        """
        statement = select(Sensor).where(Sensor.id == sensor_id, Sensor.deleted == False)
        sensor = self._db_session.scalar(statement)
        if not sensor:
            raise ObjectNotFound("Sensor not found")

        return sensor

    def create_sensor(
        self,
        sensor_type_id: int,
        area_id: int,
        name: str,
        zone_id: int,
        channel: int | None = None,
        description: str | None = None,
        enabled: bool = True,
        silent_alert: bool | None = None,
        monitor_period: int | None = None,
        monitor_threshold: int | None = None,
        channel_type: ChannelTypes = ChannelTypes.BASIC,
        sensor_contact_type: SensorContactTypes = SensorContactTypes.NO,
        sensor_eol_count: SensorEOLCount = SensorEOLCount.SINGLE,
        zigbee_device_id: int | None = None,
        zigbee_endpoint: str | None = None,
        zigbee_cluster_id: int | None = None,
        zigbee_attribute_id: int | None = None,
        zigbee_field: str | None = None,
    ) -> Sensor:
        """
        Create a new sensor in the database.
        """
        if not self.are_changes_allowed:
            raise ConfigChangesNotAllowed()

        area = self._db_session.get(Area, area_id)
        zone = self._db_session.get(Zone, zone_id)
        sensor_type = self._db_session.get(SensorType, sensor_type_id)

        try:
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
                zigbee_device_id=zigbee_device_id,
                zigbee_endpoint=zigbee_endpoint,
                zigbee_cluster_id=zigbee_cluster_id,
                zigbee_attribute_id=zigbee_attribute_id,
                zigbee_field=zigbee_field,
            )
        except AssertionError as error:
            raise InvalidSensorSource(str(error)) from error

        if not self.validate_binding(new_sensor):
            if new_sensor.channel is not None:
                raise ChannelConflictError("Channel conflict with existing sensors.")
            raise ZigbeeBindingConflictError("Zigbee signal already bound to another sensor.")

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

        sensor = self._db_session.scalar(select(Sensor).where(Sensor.id == sensor_id))
        if not sensor:
            raise ObjectNotFound("Sensor not found")

        try:
            changed = sensor.update(kwargs)
        except AssertionError as error:
            raise InvalidSensorSource(str(error)) from error

        if not changed:
            raise ObjectNotChanged("Sensor not changed")

        if not self.validate_binding(sensor):
            if sensor.channel is not None:
                raise ChannelConflictError("Channel conflict with existing sensors.")
            raise ZigbeeBindingConflictError("Zigbee signal already bound to another sensor.")

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

        sensor = self._db_session.scalar(select(Sensor).where(Sensor.id == sensor_id))
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
        return self._db_session.scalars(select(SensorType)).all()

    def validate_binding(self, sensor: Sensor) -> bool:
        """
        Validate the sensor's source (wired channel or Zigbee mapping) does not conflict.
        """
        if sensor.channel is None:
            return self.validate_zigbee_binding(sensor)
        return self.validate_channel(sensor)

    def validate_channel(self, sensor: Sensor = None) -> bool:
        """
        Validate that the sensor's channel does not conflict with existing sensors.
        """
        if sensor:
            statement = select(Sensor).where(
                Sensor.id != sensor.id,
                Sensor.channel == sensor.channel,
                Sensor.deleted == False,
            )
            same_channel_sensors = self._db_session.scalars(statement).all()
        else:
            same_channel_sensors = self._db_session.scalars(
                select(Sensor).where(Sensor.deleted == False)
            ).all()

        if (
            sensor.channel_type in [ChannelTypes.BASIC, ChannelTypes.NORMAL]
            and same_channel_sensors
        ):
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

    def validate_zigbee_binding(self, sensor: Sensor) -> bool:
        """
        Validate that the sensor's Zigbee endpoint/attribute/signal is not already bound elsewhere.
        """
        duplicate = self._db_session.scalar(
            select(Sensor).where(
                Sensor.id != sensor.id,
                Sensor.zigbee_device_id == sensor.zigbee_device_id,
                Sensor.zigbee_endpoint == sensor.zigbee_endpoint,
                Sensor.zigbee_cluster_id == sensor.zigbee_cluster_id,
                Sensor.zigbee_attribute_id == sensor.zigbee_attribute_id,
                Sensor.zigbee_field == sensor.zigbee_field,
                Sensor.deleted == False,
            )
        )
        return duplicate is None

    def reset_references(self, sensor_id: int | None = None) -> None:
        """
        Reset reference values for a specific sensor or all sensors.
        """
        if not self.are_changes_allowed:
            raise ConfigChangesNotAllowed()

        if sensor_id:
            sensor = self._db_session.get(Sensor, sensor_id)
            if not sensor:
                raise ObjectNotFound("Sensor not found")
            sensor.reference_value = None
        else:
            sensors = self._db_session.scalars(select(Sensor)).all()
            for sensor in sensors:
                sensor.reference_value = None

        self._db_session.commit()

        return IPCClient().update_configuration()

    def get_sensor_alert(self, sensor_id: int | None = None) -> bool:
        """
        Returns true when the specified sensor is in alert state,
        or if any sensor is in alert state.
        """
        statement = select(Sensor).where(
            Sensor.enabled == True,
            Sensor.alert == True,
            Sensor.deleted == False,
        )

        if sensor_id:
            statement = statement.where(Sensor.id == sensor_id)

        return self._db_session.scalar(statement) is not None

    def get_sensor_error(self, sensor_id: int | None = None) -> bool:
        """
        Returns true when the specified sensor is in error state,
        or if any sensor is in error state.
        """
        statement = select(Sensor).where(
            Sensor.enabled == True,
            Sensor.error == True,
            Sensor.deleted == False,
        )

        if sensor_id:
            statement = statement.where(Sensor.id == sensor_id)

        return self._db_session.scalar(statement) is not None

    def get_sensor_tamper(self, sensor_id: int | None = None) -> bool:
        """
        Returns true when the specified sensor is tampered,
        or if any sensor is tampered.
        """
        statement = select(Sensor).where(
            Sensor.enabled == True,
            Sensor.tamper == True,
            Sensor.deleted == False,
        )

        if sensor_id:
            statement = statement.where(Sensor.id == sensor_id)

        return self._db_session.scalar(statement) is not None
