"""
Sensor service module to handle sensor-related operations.
"""

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
from utils.zigbee import IAS_ZONE_STATUS_ATTRIBUTE


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
        self._ensure_zigbee_tamper_sensor(new_sensor)
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

        self._ensure_zigbee_tamper_sensor(sensor)
        self._db_session.commit()
        self._db_session.refresh(sensor)
        IPCClient().update_configuration()
        return sensor

    def _ensure_zigbee_tamper_sensor(self, sensor: Sensor) -> None:
        """Create the IAS Zone tamper companion for an alarm sensor if needed."""
        if (
            sensor.channel is not None
            or sensor.zigbee_field != "alarm"
            or sensor.zigbee_cluster_id != int(IAS_ZONE_STATUS_ATTRIBUTE.cluster.cluster_id)
            or sensor.zigbee_attribute_id != IAS_ZONE_STATUS_ATTRIBUTE.attribute_id
            or not any(signal.field == "tamper" for signal in IAS_ZONE_STATUS_ATTRIBUTE.signals)
        ):
            return

        tamper_type = self._db_session.query(SensorType).filter(SensorType.name == "Tamper").first()
        if not tamper_type:
            return

        existing_tamper = (
            self._db_session.query(Sensor)
            .filter(
                Sensor.zigbee_device_id == sensor.zigbee_device_id,
                Sensor.type_id == tamper_type.id,
                Sensor.deleted == False,
            )
            .first()
        )
        if existing_tamper:
            return

        # ensure there is a zone for the tamper sensor
        tamper_zone = (
            self._db_session.query(Zone)
            .filter(Zone.disarmed_delay.isnot(None), Zone.deleted == False)
            .first()
        )
        if not tamper_zone:
            tamper_zone = Zone(
                name="Tamper",
                description="Sabotage alert",
                disarmed_delay=0,
                away_alert_delay=0,
                stay_alert_delay=0,
                away_arm_delay=0,
                stay_arm_delay=0,
            )
            self._db_session.add(tamper_zone)
            self._db_session.commit()

        tamper_sensor = Sensor(
            channel=None,
            sensor_type=tamper_type,
            area=sensor.area,
            zone=tamper_zone,
            name=f"{sensor.name[: Sensor.NAME_LENGTH - 4]} (T)",
            description=f"Tamper signal for {sensor.name}",
            enabled=sensor.enabled,
            zigbee_device_id=sensor.zigbee_device_id,
            zigbee_endpoint=sensor.zigbee_endpoint,
            zigbee_cluster_id=sensor.zigbee_cluster_id,
            zigbee_attribute_id=sensor.zigbee_attribute_id,
            zigbee_field="tamper",
            ui_hidden=True,
        )
        self._db_session.add(tamper_sensor)

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

    def validate_zigbee_binding(self, sensor: Sensor) -> bool:
        """
        Validate that the sensor's Zigbee endpoint/attribute/signal is not already bound elsewhere.
        """
        duplicate = (
            self._db_session.query(Sensor)
            .filter(
                Sensor.id != sensor.id,
                Sensor.zigbee_device_id == sensor.zigbee_device_id,
                Sensor.zigbee_endpoint == sensor.zigbee_endpoint,
                Sensor.zigbee_cluster_id == sensor.zigbee_cluster_id,
                Sensor.zigbee_attribute_id == sensor.zigbee_attribute_id,
                Sensor.zigbee_field == sensor.zigbee_field,
                Sensor.deleted == False,
            )
            .first()
        )
        return duplicate is None

    def reset_references(self, sensor_id: int = None) -> None:
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
            Sensor.enabled == True,
            Sensor.alert == True,
            Sensor.deleted == False,
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
            Sensor.enabled == True,
            Sensor.error == True,
            Sensor.deleted == False,
        )

        if sensor_id:
            query = query.filter(Sensor.id == sensor_id)

        return query.first() is not None
