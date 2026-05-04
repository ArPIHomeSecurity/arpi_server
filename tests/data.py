from dataclasses import asdict
import json
import logging

from psycopg2 import ProgrammingError

from monitor.config.models import MQTTConfigInternalPublish
from monitor.database import get_database_session
from utils.constants import ROLE_ADMIN, ROLE_USER
from utils.models import (
    Area,
    ChannelTypes,
    Option,
    Sensor,
    SensorContactTypes,
    SensorEOLCount,
    SensorType,
    User,
    Zone,
    metadata,
)

logger = logging.getLogger(__name__)


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
                        port=1883,
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


def _create_users(session):
    admin_user = User(id=1, name="Administrator", role=ROLE_ADMIN, access_code="1234")
    admin_user.add_registration_code("ABCD1234")
    session.add_all(
        [admin_user, User(id=2, name="Chuck Norris", role=ROLE_USER, access_code="1111")]
    )
    logger.info(" - Created users")


def clear_database():
    session = get_database_session()
    logger.info("Clean up database...")
    for table in reversed(metadata.sorted_tables):
        logger.info(" - Clear table %s", table)
        try:
            session.execute(table.delete())
            session.commit()
        except ProgrammingError:
            logger.warning("   Table %s does not exist, skipping", table)
            session.rollback()
    logger.info("Database is empty")


def create_test_no_delay_v2():
    """
    This configuration is for basic testing with board v2 without any delays.
    """
    session = get_database_session()

    _create_users(session)
    _create_options(session)
    sensor_types = _create_sensor_types(session)

    z1 = Zone(name="No delay", description="Alert with no delay")
    z2 = Zone(
        name="Tamper",
        disarmed_delay=0,
        away_alert_delay=0,
        stay_alert_delay=0,
        description="Sabotage alert",
    )
    session.add_all([z1, z2])
    logger.info(" - Created zones")

    area = Area(name="House")
    session.add(area)
    logger.info(" - Created area")

    s1 = Sensor(
        channel=0,
        channel_type=ChannelTypes.NORMAL,
        sensor_contact_type=SensorContactTypes.NC,
        sensor_eol_count=SensorEOLCount.SINGLE,
        sensor_type=sensor_types["Motion"],
        area=area,
        zone=z1,
        name="Test room",
        description="Test room movement sensor",
        silent_alert=True,
    )
    s2 = Sensor(
        channel=1,
        channel_type=ChannelTypes.NORMAL,
        sensor_contact_type=SensorContactTypes.NC,
        sensor_eol_count=SensorEOLCount.SINGLE,
        sensor_type=sensor_types["Open"],
        area=area,
        zone=z1,
        name="Test room 0",
        description="Test room 0 door sensor",
    )
    s3 = Sensor(
        channel=2,
        channel_type=ChannelTypes.NORMAL,
        sensor_type=sensor_types["Tamper"],
        sensor_contact_type=SensorContactTypes.NC,
        sensor_eol_count=SensorEOLCount.SINGLE,
        area=area,
        zone=z2,
        name="Tamper",
        description="Sabotage wire",
    )
    session.add_all([s1, s2, s3])
    logger.info(" - Created sensors")

    session.commit()
    logger.info("Database setup is complete")


def create_test_with_delay_v2():
    """
    This configuration is for basic testing with board v2.
    """
    session = get_database_session()

    _create_users(session)
    _create_options(session)
    sensor_types = _create_sensor_types(session)

    z1 = Zone(name="No delay", description="Alert with no delay")
    z2 = Zone(
        name="Tamper",
        disarmed_delay=0,
        away_alert_delay=0,
        stay_alert_delay=0,
        description="Sabotage alert",
    )
    z3 = Zone(
        name="Away/stay delayed",
        away_arm_delay=3,
        stay_arm_delay=3,
        away_alert_delay=3,
        stay_alert_delay=3,
        description="Alert delayed when armed AWAY or STAY",
    )
    z4 = Zone(
        name="Stay delayed",
        stay_arm_delay=3,
        stay_alert_delay=3,
        description="Alert delayed when armed STAY",
    )
    z5 = Zone(
        name="Stay",
        stay_arm_delay=None,
        stay_alert_delay=None,
        description="No alert when armed STAY",
    )
    session.add_all([z1, z2, z3, z4, z5])
    logger.info(" - Created zones")

    area = Area(name="House")
    session.add(area)
    logger.info(" - Created area")

    s1 = Sensor(
        channel=0,
        channel_type=ChannelTypes.NORMAL,
        sensor_contact_type=SensorContactTypes.NC,
        sensor_eol_count=SensorEOLCount.SINGLE,
        sensor_type=sensor_types["Motion"],
        area=area,
        zone=z3,
        name="Room 0",
        description="Test room 0 delayed movement sensor",
        silent_alert=True,
    )
    s2 = Sensor(
        channel=1,
        channel_type=ChannelTypes.NORMAL,
        sensor_contact_type=SensorContactTypes.NC,
        sensor_eol_count=SensorEOLCount.SINGLE,
        sensor_type=sensor_types["Open"],
        area=area,
        zone=z4,
        name="Room 1",
        description="Test room 1 stay delayed door sensor",
    )
    s3 = Sensor(
        channel=2,
        channel_type=ChannelTypes.NORMAL,
        sensor_type=sensor_types["Motion"],
        sensor_contact_type=SensorContactTypes.NC,
        sensor_eol_count=SensorEOLCount.SINGLE,
        area=area,
        zone=z5,
        name="Room 2",
        description="Test room 2 stay delayed movement sensor",
    )
    s4 = Sensor(
        channel=3,
        channel_type=ChannelTypes.NORMAL,
        sensor_type=sensor_types["Tamper"],
        sensor_contact_type=SensorContactTypes.NC,
        sensor_eol_count=SensorEOLCount.SINGLE,
        area=area,
        zone=z2,
        name="Tamper",
        description="Sabotage wire",
    )
    session.add_all([s1, s2, s3, s4])
    logger.info(" - Created sensors")

    session.commit()
    logger.info("Database setup is complete")
