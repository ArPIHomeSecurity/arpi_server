import json
import logging
from dataclasses import asdict
from datetime import datetime

from psycopg2 import ProgrammingError
from sqlalchemy import Integer, text

from monitor.config.models import MQTTConfigInternalPublish
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
        session.commit()

        _reset_sequences(session)

        engine = session.get_bind()
        session.close()
        engine.dispose()
        logger.info("Events cleared")


def _create_sensor_types(session):
    sensor_types = {
        "Motion": SensorType(1, name="Motion", description="Detect motion"),
        "Tamper": SensorType(2, name="Tamper", description="Detect sabotage"),
        "Open": SensorType(3, name="Open", description="Detect opening"),
        "Break": SensorType(4, name="Break", description="Detect glass break"),
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


def _create_users(session) -> dict:
    admin_user = User(id=1, name="Administrator", role=ROLE_ADMIN, access_code="1234")
    admin_user.add_registration_code("ABCD1234")

    user = User(id=2, name="Chuck Norris", role=ROLE_USER, access_code="1111")
    session.add_all([admin_user, user])
    logger.info(" - Created users")
    return {"admin": admin_user, "user": user}


def create_zones(session, delay: int = 3) -> dict:
    tamper = Zone(
        name="Tamper",
        disarmed_delay=0,
        away_alert_delay=0,
        stay_alert_delay=0,
        description="Sabotage alert",
    )
    no_delay = Zone(
        name="Away/stay",
        away_arm_delay=0,
        stay_arm_delay=0,
        away_alert_delay=0,
        stay_alert_delay=0,
        description="Alert when armed AWAY or STAY",
    )
    delayed = Zone(
        name="Away/stay delayed",
        away_arm_delay=delay,
        stay_arm_delay=delay,
        away_alert_delay=delay,
        stay_alert_delay=delay,
        description="Alert delayed when armed AWAY or STAY",
    )
    away_delayed = Zone(
        name="Away delayed",
        away_arm_delay=delay,
        away_alert_delay=delay,
        description="Alert delayed when armed AWAY",
    )
    stay_delayed = Zone(
        name="Stay delayed",
        stay_arm_delay=delay,
        stay_alert_delay=delay,
        description="Alert delayed when armed STAY",
    )
    stay = Zone(
        name="Stay",
        stay_arm_delay=None,
        stay_alert_delay=None,
        description="No alert when armed STAY",
    )
    session.add_all([tamper, no_delay, no_delay, delayed, away_delayed, stay_delayed, stay])
    logger.info(" - Created zones")
    return {
        "tamper": tamper,
        "no_delay": no_delay,
        "delayed": delayed,
        "away_delayed": away_delayed,
        "stay_delayed": stay_delayed,
        "stay": stay,
    }


def create_sensors(session, sensor_types, area, zones):
    s1 = Sensor(
        channel=0,
        channel_type=ChannelTypes.NORMAL,
        sensor_contact_type=SensorContactTypes.NC,
        sensor_eol_count=SensorEOLCount.SINGLE,
        sensor_type=sensor_types["Motion"],
        area=area,
        zone=zones[0],
        name="Room 1",
        description="Test room 1 movement sensor",
        silent_alert=True,
    )
    s2 = Sensor(
        channel=1,
        channel_type=ChannelTypes.NORMAL,
        sensor_contact_type=SensorContactTypes.NC,
        sensor_eol_count=SensorEOLCount.SINGLE,
        sensor_type=sensor_types["Open"],
        area=area,
        zone=zones[1],
        name="Room 2",
        description="Test room 2 door sensor",
    )
    s3 = Sensor(
        channel=2,
        channel_type=ChannelTypes.NORMAL,
        sensor_type=sensor_types["Tamper"],
        sensor_contact_type=SensorContactTypes.NC,
        sensor_eol_count=SensorEOLCount.SINGLE,
        area=area,
        zone=zones[2],
        name="Tamper",
        description="Sabotage wire",
    )
    session.add_all([s1, s2, s3])
    logger.info(" - Created sensors")


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

        zones = create_zones(session)
        create_sensors(
            session, sensor_types, area, [zones["no_delay"], zones["no_delay"], zones["tamper"]]
        )

        session.commit()
        engine = session.get_bind()
        session.close()
        engine.dispose()
        logger.info("Database setup is complete")


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

        zones = create_zones(session)
        create_sensors(
            session, sensor_types, area, [zones["no_delay"], zones["no_delay"], zones["tamper"]]
        )
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

        zones = create_zones(session)
        create_sensors(
            session, sensor_types, house, [zones["no_delay"], zones["no_delay"], zones["tamper"]]
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

        zones = create_zones(session)
        create_sensors(
            session, sensor_types, house, [zones["delayed"], zones["delayed"], zones["tamper"]]
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

        zones = create_zones(session)
        create_sensors(
            session, sensor_types, backyard, [zones["no_delay"], zones["no_delay"], zones["tamper"]]
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

        zones = create_zones(session)
        create_sensors(
            session, sensor_types, area, [zones["no_delay"], zones["no_delay"], zones["tamper"]]
        )

        arm = Arm(arm_type=ArmStates.AWAY, time=datetime.now(), user=users["admin"])
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

        zones = create_zones(session)
        create_sensors(
            session, sensor_types, area, [zones["delayed"], zones["delayed"], zones["tamper"]]
        )

        session.commit()
        engine = session.get_bind()
        session.close()
        engine.dispose()
        logger.info("Database setup is complete")
