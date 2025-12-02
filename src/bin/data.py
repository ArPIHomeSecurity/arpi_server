#!/usr/bin/env python3
import argparse
import json
import logging
import os

from sqlalchemy.exc import ProgrammingError

from utils.constants import ROLE_ADMIN, ROLE_USER
from utils.models import (
    Area,
    ChannelTypes,
    Keypad,
    KeypadType,
    Option,
    Sensor,
    SensorContactTypes,
    SensorEOLCount,
    SensorType,
    User,
    Zone,
)
from monitor.database import get_database_session
from utils.models import metadata


# Set up logging
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


SENSOR_TYPES = [
    SensorType(1, name="Motion", description="Detect motion"),
    SensorType(2, name="Tamper", description="Detect sabotage"),
    SensorType(3, name="Open", description="Detect opening"),
    SensorType(4, name="Break", description="Detect glass break"),
]


def cleanup():
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


def env_prod():
    """
    This configuration is used for the released production version.
    """
    session = get_database_session()
    admin_user = User(name="Administrator", role=ROLE_ADMIN, access_code="1234")
    admin_user.add_registration_code("ABCD1234")
    session.add(admin_user)
    logger.info(" - Created admin user")

    session.add_all(SENSOR_TYPES)
    logger.info(" - Created sensor types")

    kt1 = KeypadType(1, "DSC", "DSC keybus (DSC PC-1555RKZ)")
    kt2 = KeypadType(2, "WIEGAND", "Wiegand keypad")
    session.add_all([kt1, kt2])
    logger.info(" - Created keypad types")

    k1 = Keypad(keypad_type=kt2)
    session.add_all([k1])
    logger.info(" - Created keypads")

    a1 = Area(name="House")
    session.add(a1)
    logger.info(" - Created area")

    mqtt_config = {
        "hostname": "localhost",
        "port": 8883,
        "username": "argus",
        "password": os.environ["ARGUS_MQTT_PASSWORD"],
        "tls_enabled": True,
        "tls_insecure": False,
    }
    mqtt_option = Option(name="mqtt", section="internal_publish", value=json.dumps(mqtt_config))
    session.add(mqtt_option)

    mqtt_config = {
        "hostname": "localhost",
        "port": 8883,
        "username": "argus_reader",
        "password": os.environ["ARGUS_READER_MQTT_PASSWORD"],
        "tls_enabled": True,
        "tls_insecure": False,
    }
    mqtt_option = Option(name="mqtt", section="internal_read", value=json.dumps(mqtt_config))
    session.add(mqtt_option)

    mqtt_connection = {
        "enabled": True,
        "external": False,
    }
    mqtt_option = Option(name="mqtt", section="connection", value=json.dumps(mqtt_connection))
    session.add(mqtt_option)
    logger.info(" - Created MQTT options")

    access_config = {
        "service_enabled": True,
        "restrict_local_network": False,
        "password_authentication_enabled": True,
    }
    ssh_access = Option(name="network", section="access", value=json.dumps(access_config))
    session.add(ssh_access)
    logger.info(" - Created access options")

    session.commit()


def env_live_01():
    """
    This configuration is used for live testing with real hardware.
    """
    session = get_database_session()
    session.add_all(
        [
            User(name="Administrator", role=ROLE_ADMIN, access_code="1234"),
            User(name="Chuck.Norris", role=ROLE_USER, access_code="1111"),
        ]
    )
    logger.info(" - Created users")

    z1 = Zone(name="No delay", description="Alert with no delay")
    z2 = Zone(
        name="Away delayed",
        away_alert_delay=20,
        description="Alert delayed when armed AWAY",
    )
    z3 = Zone(
        name="Stay delayed",
        stay_alert_delay=20,
        description="Alert delayed when armed STAY",
    )
    z4 = Zone(name="Stay", stay_alert_delay=None, description="No alert when armed STAY")
    z5 = Zone(
        name="Away/Stay delayed",
        away_alert_delay=40,
        stay_alert_delay=20,
        description="Alert delayed when armed AWAY/STAY",
    )
    z6 = Zone(
        name="Tamper",
        disarmed_delay=0,
        away_alert_delay=0,
        stay_alert_delay=0,
        description="Sabotage alert",
    )
    session.add_all([z1, z2, z3, z4, z5, z6])
    logger.info(" - Created zones")

    session.add_all(SENSOR_TYPES)
    logger.info(" - Created sensor types")

    area = Area(name="House")
    session.add(area)
    logger.info(" - Created area")

    s1 = Sensor(
        channel=0,
        channel_type=ChannelTypes.NORMAL,
        sensor_type=SENSOR_TYPES[0],
        sensor_contact_type=SensorContactTypes.NC,
        sensor_eol_count=SensorEOLCount.SINGLE,
        zone=z5,
        name="Garage",
        area=area,
    )
    s2 = Sensor(
        channel=1,
        channel_type=ChannelTypes.NORMAL,
        sensor_type=SENSOR_TYPES[0],
        sensor_contact_type=SensorContactTypes.NC,
        sensor_eol_count=SensorEOLCount.SINGLE,
        zone=z5,
        name="Hall",
        area=area,
    )
    s3 = Sensor(
        channel=2,
        channel_type=ChannelTypes.NORMAL,
        sensor_type=SENSOR_TYPES[2],
        sensor_contact_type=SensorContactTypes.NC,
        sensor_eol_count=SensorEOLCount.SINGLE,
        zone=z5,
        name="Front door",
        area=area,
    )
    s4 = Sensor(
        channel=3,
        channel_type=ChannelTypes.NORMAL,
        sensor_type=SENSOR_TYPES[0],
        sensor_contact_type=SensorContactTypes.NC,
        sensor_eol_count=SensorEOLCount.SINGLE,
        zone=z3,
        name="Kitchen",
        area=area,
    )
    s5 = Sensor(
        channel=4,
        channel_type=ChannelTypes.NORMAL,
        sensor_type=SENSOR_TYPES[0],
        sensor_contact_type=SensorContactTypes.NC,
        sensor_eol_count=SensorEOLCount.SINGLE,
        zone=z1,
        name="Living room",
        area=area,
    )
    s6 = Sensor(
        channel=5,
        channel_type=ChannelTypes.NORMAL,
        sensor_type=SENSOR_TYPES[0],
        sensor_contact_type=SensorContactTypes.NC,
        sensor_eol_count=SensorEOLCount.SINGLE,
        zone=z4,
        name="Children's room",
        area=area,
    )
    s7 = Sensor(
        channel=6,
        channel_type=ChannelTypes.NORMAL,
        sensor_type=SENSOR_TYPES[0],
        sensor_contact_type=SensorContactTypes.NC,
        sensor_eol_count=SensorEOLCount.SINGLE,
        zone=z4,
        name="Bedroom",
        area=area,
    )
    s8 = Sensor(
        channel=7,
        channel_type=ChannelTypes.NORMAL,
        sensor_type=SENSOR_TYPES[1],
        sensor_contact_type=SensorContactTypes.NC,
        sensor_eol_count=SensorEOLCount.SINGLE,
        zone=z6,
        name="Tamper",
        area=area,
    )
    session.add_all([s1, s2, s3, s4, s5, s6, s7, s8])
    logger.info(" - Created sensors")

    kt1 = KeypadType(1, "DSC", "DSC keybus (DSC PC-1555RKZ)")
    session.add_all([kt1])
    logger.info(" - Created keypad types")

    k1 = Keypad(keypad_type=kt1)
    session.add_all([k1])
    logger.info(" - Created keypads")

    mqtt_config = {
        "hostname": "localhost",
        "port": 8883,
        "username": "argus",
        "password": os.environ["ARGUS_MQTT_PASSWORD"],
        "tls_enabled": True,
        "tls_insecure": True,
    }
    mqtt_option = Option(name="network", section="mqtt", value=json.dumps(mqtt_config))
    session.add(mqtt_option)

    mqtt_config = {
        "hostname": "localhost",
        "port": 8883,
        "username": "argus_reader",
        "password": os.environ["ARGUS_READER_MQTT_PASSWORD"],
        "tls_enabled": True,
        "tls_insecure": True,
    }
    mqtt_option = Option(name="mqtt", section="internal_read", value=json.dumps(mqtt_config))
    session.add(mqtt_option)

    mqtt_connection = {
        "enabled": True,
        "external": False,
    }
    mqtt_option = Option(name="mqtt", section="connection", value=json.dumps(mqtt_connection))
    session.add(mqtt_option)
    logger.info(" - Created MQTT options")

    session.commit()


def env_test_with_v3():
    """
    This configuration is used for testing with V3 board.
    """
    session = get_database_session()
    admin_user = User(id=1, name="Administrator", role=ROLE_ADMIN, access_code="1234")
    admin_user.add_registration_code("ABCD1234")
    session.add_all(
        [admin_user, User(id=2, name="Chuck Norris", role=ROLE_USER, access_code="1111")]
    )
    logger.info(" - Created users")

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
        away_alert_delay=5,
        stay_alert_delay=5,
        description="Alert delayed when armed AWAY or STAY",
    )
    z4 = Zone(
        name="Stay delayed",
        stay_alert_delay=5,
        description="Alert delayed when armed STAY",
    )
    z5 = Zone(
        name="Stay",
        stay_alert_delay=None,
        description="No alert when armed STAY",
    )
    session.add_all([z1, z2, z3, z4, z5])
    logger.info(" - Created zones")

    session.add_all(SENSOR_TYPES)
    logger.info(" - Created sensor types")

    area = Area(name="House")
    session.add(area)
    logger.info(" - Created area")

    s1 = Sensor(
        channel=0,
        channel_type=ChannelTypes.CHANNEL_A,
        sensor_contact_type=SensorContactTypes.NC,
        sensor_eol_count=SensorEOLCount.SINGLE,
        sensor_type=SENSOR_TYPES[0],
        area=area,
        zone=z3,
        name="Test room",
        description="Test room movement sensor",
        silent_alert=True,
    )
    s2 = Sensor(
        channel=0,
        channel_type=ChannelTypes.CHANNEL_B,
        sensor_contact_type=SensorContactTypes.NC,
        sensor_eol_count=SensorEOLCount.SINGLE,
        sensor_type=SENSOR_TYPES[2],
        area=area,
        zone=z5,
        name="Test room 0",
        description="Test room 0 door sensor",
    )
    s3 = Sensor(
        channel=1,
        channel_type=ChannelTypes.BASIC,
        sensor_type=SENSOR_TYPES[0],
        sensor_contact_type=SensorContactTypes.NC,
        sensor_eol_count=SensorEOLCount.SINGLE,
        area=area,
        zone=z1,
        name="Test room 1",
        description="Test room 1 movement sensor",
    )
    s4 = Sensor(
        channel=2,
        channel_type=ChannelTypes.NORMAL,
        sensor_type=SENSOR_TYPES[0],
        sensor_contact_type=SensorContactTypes.NC,
        sensor_eol_count=SensorEOLCount.SINGLE,
        area=area,
        zone=z1,
        name="Test room 2",
        description="Test room 2 movement sensor",
    )
    s5 = Sensor(
        channel=3,
        channel_type=ChannelTypes.NORMAL,
        sensor_type=SENSOR_TYPES[0],
        sensor_contact_type=SensorContactTypes.NO,
        sensor_eol_count=SensorEOLCount.SINGLE,
        area=area,
        zone=z1,
        name="Test room 3",
        description="Test room 3 movement sensor",
    )
    s6 = Sensor(
        channel=4,
        channel_type=ChannelTypes.NORMAL,
        sensor_type=SENSOR_TYPES[0],
        sensor_contact_type=SensorContactTypes.NC,
        sensor_eol_count=SensorEOLCount.DOUBLE,
        area=area,
        zone=z1,
        name="Test room 4",
        description="Test room 4 movement sensor",
    )
    s7 = Sensor(
        channel=5,
        channel_type=ChannelTypes.NORMAL,
        sensor_type=SENSOR_TYPES[1],
        sensor_contact_type=SensorContactTypes.NC,
        sensor_eol_count=SensorEOLCount.SINGLE,
        area=area,
        zone=z2,
        name="Tamper",
        description="Sabotage wire",
    )
    session.add_all([s1, s2, s3, s4, s5, s6, s7])
    logger.info(" - Created sensors")

    kt1 = KeypadType(1, "DSC", "DSC keybus (DSC PC-1555RKZ)")
    kt2 = KeypadType(2, "WIEGAND", "Wiegand keypad")
    session.add_all([kt1, kt2])
    logger.info(" - Created keypad types")

    k1 = Keypad(keypad_type=kt2, enabled=True)
    session.add_all([k1])
    logger.info(" - Created keypads")

    mqtt_config = {
        "hostname": "localhost",
        "port": 8883,
        "username": "argus",
        "password": os.environ["ARGUS_MQTT_PASSWORD"],
        "tls_enabled": False,
        "tls_insecure": True,
    }
    mqtt_option = Option(name="mqtt", section="internal_publish", value=json.dumps(mqtt_config))
    session.add(mqtt_option)
    mqtt_config = {
        "hostname": "localhost",
        "port": 8883,
        "username": "argus_reader",
        "password": os.environ["ARGUS_READER_MQTT_PASSWORD"],
        "tls_enabled": False,
        "tls_insecure": True,
    }
    mqtt_option = Option(name="mqtt", section="internal_read", value=json.dumps(mqtt_config))
    session.add(mqtt_option)

    mqtt_connection = {
        "enabled": True,
        "external": False,
    }
    mqtt_option = Option(name="mqtt", section="connection", value=json.dumps(mqtt_connection))
    session.add(mqtt_option)
    logger.info(" - Created MQTT options")

    session.commit()


def env_test_with_v2():
    """
    This configuration is used for testing with V2 board.
    """
    session = get_database_session()
    admin_user = User(id=1, name="Administrator", role=ROLE_ADMIN, access_code="1234")
    admin_user.add_registration_code("ABCD1234")
    session.add_all(
        [admin_user, User(id=2, name="Chuck Norris", role=ROLE_USER, access_code="1111")]
    )
    logger.info(" - Created users")

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
        away_alert_delay=10,
        stay_alert_delay=10,
        description="Alert delayed when armed AWAY or STAY",
    )
    z4 = Zone(
        name="Stay delayed",
        stay_alert_delay=10,
        description="Alert delayed when armed STAY",
    )
    z5 = Zone(
        name="Stay",
        stay_alert_delay=None,
        description="No alert when armed STAY",
    )
    session.add_all([z1, z2, z3, z4, z5])
    logger.info(" - Created zones")

    session.add_all(SENSOR_TYPES)
    logger.info(" - Created sensor types")

    area = Area(name="House")
    session.add(area)
    logger.info(" - Created area")

    s1 = Sensor(
        channel=0,
        channel_type=ChannelTypes.CHANNEL_A,
        sensor_contact_type=SensorContactTypes.NC,
        sensor_eol_count=SensorEOLCount.SINGLE,
        sensor_type=SENSOR_TYPES[0],
        area=area,
        zone=z3,
        name="Test room",
        description="Test room movement sensor",
        silent_alert=True,
    )
    s2 = Sensor(
        channel=1,
        channel_type=ChannelTypes.CHANNEL_B,
        sensor_contact_type=SensorContactTypes.NC,
        sensor_eol_count=SensorEOLCount.SINGLE,
        sensor_type=SENSOR_TYPES[2],
        area=area,
        zone=z3,
        name="Test room 0",
        description="Test room 0 door sensor",
    )
    s3 = Sensor(
        channel=2,
        channel_type=ChannelTypes.BASIC,
        sensor_type=SENSOR_TYPES[1],
        sensor_contact_type=SensorContactTypes.NC,
        sensor_eol_count=SensorEOLCount.SINGLE,
        area=area,
        zone=z2,
        name="Tamper",
        description="Sabotage wire",
    )
    session.add_all([s1, s2, s3])
    logger.info(" - Created sensors")

    kt1 = KeypadType(1, "DSC", "DSC keybus (DSC PC-1555RKZ)")
    kt2 = KeypadType(2, "WIEGAND", "Wiegand keypad")
    session.add_all([kt1, kt2])
    logger.info(" - Created keypad types")

    k1 = Keypad(keypad_type=kt2, enabled=True)
    session.add_all([k1])
    logger.info(" - Created keypads")

    mqtt_config = {
        "hostname": "localhost",
        "port": 8883,
        "username": "argus",
        "password": os.environ["ARGUS_MQTT_PASSWORD"],
        "tls_enabled": False,
        "tls_insecure": True,
    }
    mqtt_option = Option(name="mqtt", section="internal_publish", value=json.dumps(mqtt_config))
    session.add(mqtt_option)
    mqtt_config = {
        "hostname": "localhost",
        "port": 8883,
        "username": "argus_reader",
        "password": os.environ["ARGUS_READER_MQTT_PASSWORD"],
        "tls_enabled": False,
        "tls_insecure": True,
    }
    mqtt_option = Option(name="mqtt", section="internal_read", value=json.dumps(mqtt_config))
    session.add(mqtt_option)

    mqtt_connection = {
        "enabled": True,
        "external": False,
    }
    mqtt_option = Option(name="mqtt", section="connection", value=json.dumps(mqtt_connection))
    session.add(mqtt_option)
    logger.info(" - Created MQTT options")

    session.commit()


def env_admin_registration():
    session = get_database_session()
    admin_user = session.query(User).filter(User.role == ROLE_ADMIN).first()
    code = admin_user.add_registration_code("ABCD")
    logger.info("Code: %s", code)
    admin_user.update({"access_code": "1234"})
    logger.info("Password: %s", "1234")
    session.commit()
    logger.info("Admin registration added and password changed")


def main():
    environments = [
        attribute.replace("env_", "") for attribute in globals() if attribute.startswith("env_")
    ]

    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--delete", action="store_true", help="Delete database content")
    parser.add_argument(
        "-c",
        "--create",
        metavar="environment",
        help=f"Create database content (environments: {', '.join(environments)})",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    if not args.delete and not args.create:
        parser.print_help()
        return 0

    # Configure logging based on verbose flag
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    if args.delete:
        cleanup()

    if args.create:
        try:
            create_method = globals()[f"env_{args.create}"]
        except KeyError:
            logger.error("Unknown environment: %s", args.create)
            return 1

        logger.info("Creating '%s' environment...", args.create)
        create_method()
        logger.info("Environment created")
        return 0


if __name__ == "__main__":
    exit(main())
