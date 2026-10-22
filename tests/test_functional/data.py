import json
import logging
from dataclasses import asdict
from datetime import datetime

from psycopg2 import ProgrammingError
from sqlalchemy import Integer, text
from zigpy.zcl.clusters.security import IasZone

from monitor.config.models import (
    GSMConfig,
    MQTTConfigInternalPublish,
    SMSActionConfig,
    SMSCommandConfig,
)
from monitor.database import create_database_session
from utils.constants import ROLE_ADMIN, ROLE_USER
from utils.models import (
    Alert,
    AlertSensor,
    Area,
    Arm,
    ArmSensor,
    ArmStates,
    ChannelTypes,
    Disarm,
    Option,
    Output,
    OutputTriggerType,
    Sensor,
    SensorContactTypes,
    SensorEOLCount,
    SensorType,
    User,
    ZigbeeDevice,
    Zone,
    metadata,
)

logger = logging.getLogger(__name__)


def _reset_sequences(session):
    """Reset PostgreSQL serial sequences for deterministic test IDs."""
    logger.info("Resetting database sequences...")

    for table in metadata.sorted_tables:
        for column in table.columns:
            if not (column.primary_key and isinstance(column.type, Integer)):
                continue

            seq_name = session.execute(
                text("SELECT pg_get_serial_sequence(:table_name, :column_name)"),
                {"table_name": table.name, "column_name": column.name},
            ).scalar()

            if not seq_name:
                continue

            session.execute(
                text("SELECT setval(CAST(:seq_name AS regclass), 1, false)"),
                {"seq_name": seq_name},
            )
            logger.debug(" - Reset sequence %s", seq_name)

    session.commit()
    logger.info("Sequences reset")


def cleanup_database():
    with create_database_session() as session:
        logger.info("Clearing events...")
        session.execute(ArmSensor.__table__.delete())
        session.execute(AlertSensor.__table__.delete())
        session.execute(Disarm.__table__.delete())
        session.execute(Arm.__table__.delete())
        session.execute(Alert.__table__.delete())
        session.execute(Option.__table__.delete())
        session.commit()

        _reset_sequences(session)

        engine = session.get_bind()
        session.close()
        engine.dispose()
        logger.info("Events cleared")


def _create_sensor_types(session):
    # list existing sensor types and create them if they don't exist
    existing_sensor_types = {st.name for st in session.query(SensorType).all()}
    logger.info(" - Existing sensor types: %s", existing_sensor_types)

    sensor_types = {
        "Motion": SensorType(id=1, name="Motion", description="Detect motion"),
        "Tamper": SensorType(id=2, name="Tamper", description="Detect sabotage"),
        "Open": SensorType(id=3, name="Open", description="Detect opening"),
        "Break": SensorType(id=4, name="Break", description="Detect glass break"),
        "Contact": SensorType(id=5, name="Contact", description="IAS Zone contact switch"),
        "Fire": SensorType(id=6, name="Fire", description="IAS Zone fire sensor"),
        "Water": SensorType(id=7, name="Water", description="IAS Zone water sensor"),
        "CO": SensorType(id=8, name="CO", description="IAS Zone carbon monoxide sensor"),
        "Emergency": SensorType(id=9, name="Emergency", description="IAS Zone emergency device"),
        "Vibration": SensorType(id=10, name="Vibration", description="IAS Zone vibration sensor"),
        "Remote": SensorType(id=11, name="Remote", description="IAS Zone remote control"),
        "Key fob": SensorType(id=12, name="Key fob", description="IAS Zone key fob"),
        "Keypad": SensorType(id=13, name="Keypad", description="IAS Zone keypad"),
        "Warning": SensorType(id=14, name="Warning", description="IAS Zone warning device"),
        "Glass": SensorType(id=15, name="Glass", description="IAS Zone glass break sensor"),
        "Repeater": SensorType(id=16, name="Repeater", description="IAS Zone security repeater"),
        "Occupancy": SensorType(id=17, name="Occupancy", description="IAS Zone occupancy sensor"),
    }
    session.add_all(sensor_types.values())
    logger.info(" - Created sensor types")
    return sensor_types


def _create_options(session):
    session.add(
        Option(
            name=MQTTConfigInternalPublish.OPTION_NAME,
            section=MQTTConfigInternalPublish.SECTION_NAME,
            value=json.dumps(
                asdict(
                    MQTTConfigInternalPublish(
                        hostname="localhost",
                        port=2883,
                        username="argus_reader",
                        password="",
                        tls_enabled=False,
                        tls_insecure=True,
                    )
                )
            ),
        )
    )
    logger.info(" - Created MQTT config option")

    session.add(
        Option(
            name=GSMConfig.OPTION_NAME,
            section=GSMConfig.SECTION_NAME,
            value=json.dumps(
                asdict(GSMConfig(enabled=True, pin_code="1234", phone_number_1="+1234567890"))
            ),
        )
    )
    logger.info(" - Created GSM config option")

    session.add(
        Option(
            name=SMSActionConfig.OPTION_NAME,
            section=SMSActionConfig.SECTION_NAME,
            value=json.dumps(
                asdict(
                    SMSActionConfig(
                        enabled=True,
                        check_phone_number=True,
                        access_code_required=True,
                    )
                )
            ),
        )
    )
    logger.info(" - Created SMS action config option")

    session.add(
        Option(
            name=SMSCommandConfig.OPTION_NAME,
            section=SMSCommandConfig.SECTION_NAME,
            value=json.dumps(
                asdict(
                    SMSCommandConfig(
                        case_sensitive=False,
                        arm_away_command="away",
                        arm_stay_command="stay",
                        disarm_command="disarm",
                    )
                )
            ),
        )
    )
    logger.info(" - Created SMS command config option")


def _create_users(session) -> dict:
    admin_user = User(id=1, name="Administrator", role=ROLE_ADMIN, access_code="1234")
    admin_user.add_registration_code("ABCD1234")

    user = User(id=2, name="Chuck Norris", role=ROLE_USER, access_code="1111")
    session.add_all([admin_user, user])
    logger.info(" - Created users")
    return {"admin": admin_user, "user": user}


def _create_zones(session, delay: int = 3) -> dict[str, Zone]:
    zones = {
        "tamper": Zone(
            name="Tamper",
            disarmed_delay=0,
            away_alert_delay=0,
            stay_alert_delay=0,
            description="Sabotage alert",
        ),
        "no_delay": Zone(
            name="Away/stay",
            away_arm_delay=0,
            stay_arm_delay=0,
            away_alert_delay=0,
            stay_alert_delay=0,
            description="Alert when armed AWAY or STAY",
        ),
        "delayed": Zone(
            name="Away/stay delayed",
            away_arm_delay=delay,
            stay_arm_delay=delay,
            away_alert_delay=delay,
            stay_alert_delay=delay,
            description="Alert delayed when armed AWAY or STAY",
        ),
        "away_delayed": Zone(
            name="Away delayed",
            away_arm_delay=delay,
            away_alert_delay=delay,
            description="Alert delayed when armed AWAY",
        ),
        "stay_delayed": Zone(
            name="Stay delayed",
            stay_arm_delay=delay,
            stay_alert_delay=delay,
            description="Alert delayed when armed STAY",
        ),
        "stay": Zone(
            name="Stay",
            stay_arm_delay=None,
            stay_alert_delay=None,
            description="No alert when armed STAY",
        ),
    }
    session.add_all(zones.values())
    logger.info(" - Created zones")
    return zones


def _create_sensors(session, sensor_types, area, zone_1, zone_2, zone_tamper) -> dict[str, Sensor]:
    sensors = {
        "Room 1": Sensor(
            channel=0,  # CH01
            channel_type=ChannelTypes.NORMAL,
            sensor_contact_type=SensorContactTypes.NC,
            sensor_eol_count=SensorEOLCount.SINGLE,
            sensor_type=sensor_types["Motion"],
            area=area,
            zone=zone_1,
            name="Room 1",
            description="Test room 1 movement sensor",
            silent_alert=True,
        ),
        "Room 2": Sensor(
            channel=1,  # CH02
            channel_type=ChannelTypes.NORMAL,
            sensor_contact_type=SensorContactTypes.NC,
            sensor_eol_count=SensorEOLCount.SINGLE,
            sensor_type=sensor_types["Open"],
            area=area,
            zone=zone_2,
            name="Room 2",
            description="Test room 2 door sensor",
        ),
        "Tamper": Sensor(
            channel=2,  # CH03
            channel_type=ChannelTypes.NORMAL,
            sensor_type=sensor_types["Tamper"],
            sensor_contact_type=SensorContactTypes.NC,
            sensor_eol_count=SensorEOLCount.SINGLE,
            area=area,
            zone=zone_tamper,
            name="Tamper",
            description="Sabotage wire",
        ),
    }
    session.add_all(sensors.values())
    logger.info(" - Created sensors")
    return sensors


def _create_zigbee_devices(session) -> dict[str, ZigbeeDevice]:
    endpoint = "1"
    zone_status = IasZone.AttributeDefs.zone_status
    devices = {
        "X001": ZigbeeDevice(
            ieee_address="11:22:33:44:55:66:77:88",
            name="Zigbee Contact Sensor",
            metadata={
                "signals": [
                    {
                        "endpoint": endpoint,
                        "cluster": IasZone.ep_attribute,
                        "clusterId": int(IasZone.cluster_id),
                        "attribute": zone_status.name,
                        "attributeId": int(zone_status.id),
                        "valueType": zone_status.type.__name__,
                        "field": "alarm",
                        "sources": ["command:status_change_notification"],
                    },
                    {
                        "endpoint": endpoint,
                        "cluster": IasZone.ep_attribute,
                        "clusterId": int(IasZone.cluster_id),
                        "attribute": zone_status.name,
                        "attributeId": int(zone_status.id),
                        "valueType": zone_status.type.__name__,
                        "field": "tamper",
                        "sources": ["command:status_change_notification"],
                    },
                ]
            },
        )
    }
    session.add_all(devices.values())
    session.flush()
    logger.info(" - Created Zigbee devices")
    return devices


def _create_zigbee_sensor(session, sensor_types, zigbee_devices, area, zones) -> Sensor:
    zigbee_sensor = Sensor(
        channel=None,
        zigbee_device_id=zigbee_devices["X001"].id,
        zigbee_endpoint="1",
        zigbee_cluster_id=int(IasZone.cluster_id),
        zigbee_attribute_id=int(IasZone.AttributeDefs.zone_status.id),
        zigbee_field="alarm",
        sensor_type=sensor_types["Open"],
        area=area,
        zone=zones["no_delay"],
        name="Zigbee Door",
        description="Test Zigbee contact sensor",
    )
    session.add(zigbee_sensor)
    logger.info(" - Created Zigbee device and contact sensor")
    return zigbee_sensor


def clear_database():
    with create_database_session() as session:
        logger.info("Clean up database...")
        for table in reversed(metadata.sorted_tables):
            logger.info(" - Clear table %s", table)
            try:
                session.execute(table.delete())
                session.commit()
            except ProgrammingError:
                logger.warning("   Table %s does not exist, skipping", table)
                session.rollback()

        _reset_sequences(session)

        engine = session.get_bind()
        session.close()
        engine.dispose()
        logger.info("Database is empty")


def create_test_no_delay_v2():
    """
    This configuration is for basic testing with board v2 without any delays.
    """
    with create_database_session() as session:
        _create_users(session)
        _create_options(session)
        sensor_types = _create_sensor_types(session)

        area = Area(name="House")
        session.add(area)
        logger.info(" - Created area")

        zones = _create_zones(session)
        _create_sensors(
            session, sensor_types, area, zones["no_delay"], zones["no_delay"], zones["tamper"]
        )

        zigbee_devices = _create_zigbee_devices(session)
        _create_zigbee_sensor(session, sensor_types, zigbee_devices, area, zones)

        session.commit()
        logger.info("Database setup is complete")


def create_test_v3_zigbee():
    """Create a v3 test setup with one double-EOL wired sensor."""
    with create_database_session() as session:
        _create_users(session)
        _create_options(session)
        sensor_types = _create_sensor_types(session)

        area = Area(name="House")
        session.add(area)
        zones = _create_zones(session)
        sensors = _create_sensors(
            session, sensor_types, area, zones["no_delay"], zones["no_delay"], zones["tamper"]
        )
        sensors["Room 1"].sensor_eol_count = SensorEOLCount.DOUBLE

        zigbee_devices = _create_zigbee_devices(session)
        _create_zigbee_sensor(session, sensor_types, zigbee_devices, area, zones)

        session.commit()
        logger.info("Error-state test database setup is complete")


def create_test_outputs_v2():
    """
    This configuration has one output of every trigger type.
    """
    with create_database_session() as session:
        _create_users(session)
        _create_options(session)
        sensor_types = _create_sensor_types(session)

        area = Area(name="House")
        session.add(area)

        zones = _create_zones(session)
        _create_sensors(
            session, sensor_types, area, zones["no_delay"], zones["no_delay"], zones["tamper"]
        )
        zigbee_devices = _create_zigbee_devices(session)
        _create_zigbee_sensor(session, sensor_types, zigbee_devices, area, zones)
        session.commit()

        session.add_all(
            [
                Output(
                    name="Button",
                    description="Button output",
                    channel=0,
                    trigger_type=OutputTriggerType.BUTTON.value,
                    area_id=None,
                    delay=0,
                    duration=1,
                    default_state=False,
                    enabled=True,
                ),
                Output(
                    name="Area",
                    description="Area output",
                    channel=1,
                    trigger_type=OutputTriggerType.AREA.value,
                    area_id=area.id,
                    delay=0,
                    duration=1,
                    default_state=False,
                    enabled=True,
                ),
                Output(
                    name="System",
                    description="System output",
                    channel=2,
                    trigger_type=OutputTriggerType.SYSTEM.value,
                    area_id=None,
                    delay=0,
                    duration=1,
                    default_state=False,
                    enabled=True,
                ),
            ]
        )
        logger.info(" - Created outputs")

        session.commit()
        engine = session.get_bind()
        session.close()
        engine.dispose()
        logger.info("Database setup is complete")


def create_test_two_areas_v2():
    """
    Two areas with their own sensors, without any delays.

    The area created first stays disarmed in the tests and only the second one is
    armed, so a non deterministic arm state calculation is detected.
    """
    with create_database_session() as session:
        _create_users(session)
        _create_options(session)
        sensor_types = _create_sensor_types(session)

        house = Area(name="House")
        garage = Area(name="Garage")
        session.add_all([house, garage])
        logger.info(" - Created areas")

        zones = _create_zones(session)
        _create_sensors(
            session, sensor_types, house, zones["no_delay"], zones["no_delay"], zones["tamper"]
        )

        session.add(
            Sensor(
                channel=3,
                channel_type=ChannelTypes.NORMAL,
                sensor_contact_type=SensorContactTypes.NC,
                sensor_eol_count=SensorEOLCount.SINGLE,
                sensor_type=sensor_types["Motion"],
                area=garage,
                zone=zones["no_delay"],
                name="Garage",
                description="Test garage movement sensor",
            )
        )
        logger.info(" - Created garage sensor")
        zigbee_devices = _create_zigbee_devices(session)
        _create_zigbee_sensor(session, sensor_types, zigbee_devices, house, zones)

        session.commit()
        engine = session.get_bind()
        session.close()
        engine.dispose()
        logger.info("Database setup is complete")


def create_test_two_areas_with_delay_v2():
    """
    Two areas with their own delayed sensors, for testing the exit delay when only a
    part of the areas is armed or disarmed.
    """
    with create_database_session() as session:
        _create_users(session)
        _create_options(session)
        sensor_types = _create_sensor_types(session)

        house = Area(name="House")
        garage = Area(name="Garage")
        session.add_all([house, garage])
        logger.info(" - Created areas")

        zones = _create_zones(session)
        _create_sensors(
            session, sensor_types, house, zones["delayed"], zones["delayed"], zones["tamper"]
        )

        session.add(
            Sensor(
                channel=3,
                channel_type=ChannelTypes.NORMAL,
                sensor_contact_type=SensorContactTypes.NC,
                sensor_eol_count=SensorEOLCount.SINGLE,
                sensor_type=sensor_types["Motion"],
                area=garage,
                zone=zones["delayed"],
                name="Garage",
                description="Test garage movement sensor",
            )
        )
        logger.info(" - Created garage sensor")
        zigbee_devices = _create_zigbee_devices(session)
        _create_zigbee_sensor(session, sensor_types, zigbee_devices, house, zones)

        session.commit()
        engine = session.get_bind()
        session.close()
        engine.dispose()
        logger.info("Database setup is complete")


def create_test_colliding_areas_v2():
    """
    Areas whose names collide on the MQTT topics.

    "A B" and "A.B" both sanitize to "a_b" and "System" collides with the panel
    controlling the whole system. Only "Backyard" has its own topic.
    """
    with create_database_session() as session:
        _create_users(session)
        _create_options(session)
        sensor_types = _create_sensor_types(session)

        backyard = Area(name="Backyard")
        system = Area(name="System")
        session.add_all([backyard, Area(name="A B"), Area(name="A.B"), system])
        logger.info(" - Created areas")

        zones = _create_zones(session)
        _create_sensors(
            session, sensor_types, backyard, zones["no_delay"], zones["no_delay"], zones["tamper"]
        )

        # the colliding area needs a sensor as well, an area without sensors cannot be armed
        session.add(
            Sensor(
                channel=3,
                channel_type=ChannelTypes.NORMAL,
                sensor_contact_type=SensorContactTypes.NC,
                sensor_eol_count=SensorEOLCount.SINGLE,
                sensor_type=sensor_types["Motion"],
                area=system,
                zone=zones["no_delay"],
                name="System room",
                description="Test movement sensor in the colliding area",
            )
        )

        zigbee_devices = _create_zigbee_devices(session)
        _create_zigbee_sensor(session, sensor_types, zigbee_devices, backyard, zones)

        session.commit()
        engine = session.get_bind()
        session.close()
        engine.dispose()
        logger.info("Database setup is complete")


def create_test_no_delay_v2_armed():
    """
    This configuration is for basic testing with board v2 without any delays.
    But the area is armed, so we can test starting in armed state.
    """
    with create_database_session() as session:
        users = _create_users(session)
        _create_options(session)
        sensor_types = _create_sensor_types(session)

        area = Area(name="House", arm_state=ArmStates.AWAY)
        session.add(area)
        logger.info(" - Created area")

        zones = _create_zones(session)
        _create_sensors(
            session, sensor_types, area, zones["no_delay"], zones["no_delay"], zones["tamper"]
        )
        zigbee_devices = _create_zigbee_devices(session)
        _create_zigbee_sensor(session, sensor_types, zigbee_devices, area, zones)

        arm = Arm(arm_type=ArmStates.AWAY, time=datetime.now().astimezone(), user=users["admin"])
        session.add(arm)

        session.commit()
        engine = session.get_bind()
        session.close()
        engine.dispose()
        logger.info("Database setup is complete")


def create_test_with_delay_v2():
    """
    This configuration is for basic testing with board v2.
    """
    with create_database_session() as session:
        _create_users(session)
        _create_options(session)
        sensor_types = _create_sensor_types(session)

        area = Area(name="House")
        session.add(area)
        logger.info(" - Created area")

        zones = _create_zones(session)
        _create_sensors(
            session, sensor_types, area, zones["delayed"], zones["delayed"], zones["tamper"]
        )

        zigbee_devices = _create_zigbee_devices(session)
        _create_zigbee_sensor(session, sensor_types, zigbee_devices, area, zones)

        session.commit()
        engine = session.get_bind()
        session.close()
        engine.dispose()
        logger.info("Database setup is complete")
