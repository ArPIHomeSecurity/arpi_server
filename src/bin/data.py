#!/usr/bin/env python3
import argparse
import json
import logging
import os
import sys
from dataclasses import asdict

from sqlalchemy.exc import ProgrammingError

from monitor.config.models import SSHConfig
from monitor.database import create_database_session
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
    metadata,
)


class InvalidBoardVersion(Exception):
    def __init__(self, board_version: str):
        super().__init__(f"Invalid board version: {board_version}")


# Set up logging
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


SENSOR_TYPE_DATA = (
    (1, "Motion", "Detect motion"),
    (2, "Tamper", "Detect sabotage"),
    (3, "Open", "Detect opening"),
    (4, "Break", "Detect glass break"),
    (5, "Contact", "IAS Zone contact switch"),
    (6, "Fire", "IAS Zone fire sensor"),
    (7, "Water", "IAS Zone water sensor"),
    (8, "CO", "IAS Zone carbon monoxide sensor"),
    (9, "Emergency", "IAS Zone emergency device"),
    (10, "Vibration", "IAS Zone vibration sensor"),
    (11, "Remote", "IAS Zone remote control"),
    (12, "Key fob", "IAS Zone key fob"),
    (13, "Keypad", "IAS Zone keypad"),
    (14, "Warning", "IAS Zone warning device"),
    (15, "Glass", "IAS Zone glass break sensor"),
    (16, "Repeater", "IAS Zone security repeater"),
    (17, "Occupancy", "Occupancy sensor"),
)


def _create_sensor_types(session) -> dict[str, SensorType]:
    # cleanup existing sensor types
    session.execute(SensorType.__table__.delete())
    session.commit()
    logger.info(" - Cleaned up existing sensor types")

    # create sensor types from data
    sensor_types = {
        name: SensorType(id=sensor_type_id, name=name, description=description)
        for sensor_type_id, name, description in SENSOR_TYPE_DATA
    }
    session.add_all(sensor_types.values())
    logger.info(" - Created sensor types")
    return sensor_types


def _create_admin_user(
    session, user_id: int | None = None, registration_code: str | None = None
) -> User:
    admin_user = User(id=user_id, name="Administrator", role=ROLE_ADMIN, access_code="1234")
    if registration_code:
        admin_user.add_registration_code(registration_code)
    session.add(admin_user)
    return admin_user


def _create_test_zones(session, delay: int) -> dict[str, Zone]:
    zones = {
        "no_delay": Zone(name="No delay", description="Alert with no delay"),
        "tamper": Zone(
            name="Tamper",
            disarmed_delay=0,
            away_alert_delay=0,
            stay_alert_delay=0,
            description="Sabotage alert",
        ),
        "away_stay_delayed": Zone(
            name="Away/stay delayed",
            away_alert_delay=delay,
            stay_alert_delay=delay,
            description="Alert delayed when armed AWAY or STAY",
        ),
        "stay_delayed": Zone(
            name="Stay delayed",
            stay_alert_delay=delay,
            description="Alert delayed when armed STAY",
        ),
        "stay": Zone(
            name="Stay",
            stay_alert_delay=None,
            description="No alert when armed STAY",
        ),
    }
    session.add_all(zones.values())
    logger.info(" - Created zones")
    return zones


def _create_keypad(
    session, keypad_type_name: str, *, include_wiegand: bool = False, enabled: bool | None = None
) -> Keypad:
    keypad_types = {"DSC": KeypadType(1, "DSC", "DSC keybus (DSC PC-1555RKZ)")}
    if include_wiegand:
        keypad_types["WIEGAND"] = KeypadType(2, "WIEGAND", "Wiegand keypad")

    session.add_all(keypad_types.values())
    logger.info(" - Created keypad types")

    if enabled is None:
        keypad = Keypad(keypad_type=keypad_types[keypad_type_name])
    else:
        keypad = Keypad(keypad_type=keypad_types[keypad_type_name], enabled=enabled)
    session.add(keypad)
    logger.info(" - Created keypads")
    return keypad


def cleanup():
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
        logger.info("Database is empty")


def env_prod():
    """
    This configuration is used for the released production version.
    """
    with create_database_session() as session:
        _create_admin_user(session, registration_code="ABCD1234")
        logger.info(" - Created admin user")
        _create_sensor_types(session)

        # add default zones: tamper, instant alert, delayed alert
        z1 = Zone(
            name="Tamper",
            disarmed_delay=0,
            away_alert_delay=0,
            stay_alert_delay=0,
            description="Sabotage alert",
        )
        z2 = Zone(
            name="Instant alert",
            disarmed_delay=None,
            away_arm_delay=0,
            away_alert_delay=0,
            stay_arm_delay=0,
            stay_alert_delay=0,
            description="Arm and alert with no delay",
        )
        z3 = Zone(
            name="Delayed",
            disarmed_delay=None,
            away_arm_delay=30,
            away_alert_delay=30,
            stay_arm_delay=30,
            stay_alert_delay=30,
            description="Arm and alert with delay",
        )
        session.add_all([z1, z2, z3])
        logger.info(" - Created default zones")

        _create_keypad(session, "WIEGAND", include_wiegand=True)

        a1 = Area(name="House")
        session.add(a1)
        logger.info(" - Created area")

        ssh_access = SSHConfig()
        ssh_option = Option(name="network", section="access", value=json.dumps(asdict(ssh_access)))
        session.add(ssh_option)
        logger.info(" - Created access options")

        session.commit()


def env_live_01():
    """
    This configuration is used for live testing with real hardware.
    """
    with create_database_session() as session:
        _create_admin_user(session)
        session.add(User(name="Chuck.Norris", role=ROLE_USER, access_code="1111"))
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

        sensor_types = _create_sensor_types(session)

        area = Area(name="House")
        session.add(area)
        logger.info(" - Created area")

        s1 = Sensor(
            channel=0,
            channel_type=ChannelTypes.NORMAL,
            sensor_type=sensor_types["Motion"],
            sensor_contact_type=SensorContactTypes.NC,
            sensor_eol_count=SensorEOLCount.SINGLE,
            zone=z5,
            name="Garage",
            area=area,
        )
        s2 = Sensor(
            channel=1,
            channel_type=ChannelTypes.NORMAL,
            sensor_type=sensor_types["Motion"],
            sensor_contact_type=SensorContactTypes.NC,
            sensor_eol_count=SensorEOLCount.SINGLE,
            zone=z5,
            name="Hall",
            area=area,
        )
        s3 = Sensor(
            channel=2,
            channel_type=ChannelTypes.NORMAL,
            sensor_type=sensor_types["Open"],
            sensor_contact_type=SensorContactTypes.NC,
            sensor_eol_count=SensorEOLCount.SINGLE,
            zone=z5,
            name="Front door",
            area=area,
        )
        s4 = Sensor(
            channel=3,
            channel_type=ChannelTypes.NORMAL,
            sensor_type=sensor_types["Motion"],
            sensor_contact_type=SensorContactTypes.NC,
            sensor_eol_count=SensorEOLCount.SINGLE,
            zone=z3,
            name="Kitchen",
            area=area,
        )
        s5 = Sensor(
            channel=4,
            channel_type=ChannelTypes.NORMAL,
            sensor_type=sensor_types["Motion"],
            sensor_contact_type=SensorContactTypes.NC,
            sensor_eol_count=SensorEOLCount.SINGLE,
            zone=z1,
            name="Living room",
            area=area,
        )
        s6 = Sensor(
            channel=5,
            channel_type=ChannelTypes.NORMAL,
            sensor_type=sensor_types["Motion"],
            sensor_contact_type=SensorContactTypes.NC,
            sensor_eol_count=SensorEOLCount.SINGLE,
            zone=z4,
            name="Children's room",
            area=area,
        )
        s7 = Sensor(
            channel=6,
            channel_type=ChannelTypes.NORMAL,
            sensor_type=sensor_types["Motion"],
            sensor_contact_type=SensorContactTypes.NC,
            sensor_eol_count=SensorEOLCount.SINGLE,
            zone=z4,
            name="Bedroom",
            area=area,
        )
        s8 = Sensor(
            channel=7,
            channel_type=ChannelTypes.NORMAL,
            sensor_type=sensor_types["Tamper"],
            sensor_contact_type=SensorContactTypes.NC,
            sensor_eol_count=SensorEOLCount.SINGLE,
            zone=z6,
            name="Tamper",
            area=area,
        )
        session.add_all([s1, s2, s3, s4, s5, s6, s7, s8])
        logger.info(" - Created sensors")

        _create_keypad(session, "DSC")

        session.commit()


def env_dev_with_v3():
    with create_database_session() as session:
        _env_with_v3(session)
        session.commit()


def env_test_with_v3():
    with create_database_session() as session:
        _env_with_v3(session)
        session.commit()


def _env_with_v3(session):
    """
    This configuration is used for testing with V3 board.
    """
    board_version = os.environ["BOARD_VERSION"]
    if board_version != "3":
        raise InvalidBoardVersion(board_version)

    _create_admin_user(session, user_id=1, registration_code="ABCD1234")
    session.add(User(id=2, name="Chuck Norris", role=ROLE_USER, access_code="1111"))
    logger.info(" - Created users")

    zones = _create_test_zones(session, delay=5)

    sensor_types = _create_sensor_types(session)

    area = Area(name="House")
    session.add(area)
    logger.info(" - Created area")

    s1 = Sensor(
        channel=0,
        channel_type=ChannelTypes.CHANNEL_A,
        sensor_contact_type=SensorContactTypes.NC,
        sensor_eol_count=SensorEOLCount.SINGLE,
        sensor_type=sensor_types["Motion"],
        area=area,
        zone=zones["away_stay_delayed"],
        name="Test room",
        description="Test room movement sensor",
        silent_alert=True,
    )
    s2 = Sensor(
        channel=0,
        channel_type=ChannelTypes.CHANNEL_B,
        sensor_contact_type=SensorContactTypes.NC,
        sensor_eol_count=SensorEOLCount.SINGLE,
        sensor_type=sensor_types["Open"],
        area=area,
        zone=zones["stay"],
        name="Test room 0",
        description="Test room 0 door sensor",
    )
    s3 = Sensor(
        channel=1,
        channel_type=ChannelTypes.BASIC,
        sensor_type=sensor_types["Motion"],
        sensor_contact_type=SensorContactTypes.NC,
        sensor_eol_count=SensorEOLCount.SINGLE,
        area=area,
        zone=zones["no_delay"],
        name="Test room 1",
        description="Test room 1 movement sensor",
    )
    s4 = Sensor(
        channel=2,
        channel_type=ChannelTypes.NORMAL,
        sensor_type=sensor_types["Motion"],
        sensor_contact_type=SensorContactTypes.NC,
        sensor_eol_count=SensorEOLCount.SINGLE,
        area=area,
        zone=zones["no_delay"],
        name="Test room 2",
        description="Test room 2 movement sensor",
    )
    s5 = Sensor(
        channel=3,
        channel_type=ChannelTypes.NORMAL,
        sensor_type=sensor_types["Motion"],
        sensor_contact_type=SensorContactTypes.NO,
        sensor_eol_count=SensorEOLCount.SINGLE,
        area=area,
        zone=zones["no_delay"],
        name="Test room 3",
        description="Test room 3 movement sensor",
    )
    s6 = Sensor(
        channel=4,
        channel_type=ChannelTypes.NORMAL,
        sensor_type=sensor_types["Motion"],
        sensor_contact_type=SensorContactTypes.NC,
        sensor_eol_count=SensorEOLCount.DOUBLE,
        area=area,
        zone=zones["no_delay"],
        name="Test room 4",
        description="Test room 4 movement sensor",
    )
    s7 = Sensor(
        channel=5,
        channel_type=ChannelTypes.NORMAL,
        sensor_type=sensor_types["Tamper"],
        sensor_contact_type=SensorContactTypes.NC,
        sensor_eol_count=SensorEOLCount.SINGLE,
        area=area,
        zone=zones["tamper"],
        name="Tamper",
        description="Sabotage wire",
    )
    session.add_all([s1, s2, s3, s4, s5, s6, s7])
    logger.info(" - Created sensors")

    _create_keypad(session, "WIEGAND", include_wiegand=True, enabled=True)


def env_test_with_v2():
    with create_database_session() as session:
        _env_with_v2(session)
        session.commit()


def env_dev_with_v2():
    with create_database_session() as session:
        _env_with_v2(session)
        session.commit()


def _env_with_v2(session):
    """
    This configuration is used for testing with V2 board.
    """

    board_Version = os.getenv("BOARD_VERSION")
    if board_Version != "2":
        raise InvalidBoardVersion(board_Version)

    _create_admin_user(session, user_id=1, registration_code="ABCD1234")
    session.add(User(id=2, name="Chuck Norris", role=ROLE_USER, access_code="1111"))
    logger.info(" - Created users")

    zones = _create_test_zones(session, delay=10)

    sensor_types = _create_sensor_types(session)

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
        zone=zones["away_stay_delayed"],
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
        zone=zones["away_stay_delayed"],
        name="Test room 0",
        description="Test room 0 door sensor",
    )
    s3 = Sensor(
        channel=2,
        channel_type=ChannelTypes.BASIC,
        sensor_type=sensor_types["Tamper"],
        sensor_contact_type=SensorContactTypes.NC,
        sensor_eol_count=SensorEOLCount.SINGLE,
        area=area,
        zone=zones["tamper"],
        name="Tamper",
        description="Sabotage wire",
    )
    session.add_all([s1, s2, s3])
    logger.info(" - Created sensors")

    _create_keypad(session, "WIEGAND", include_wiegand=True, enabled=True)


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


def cli_main() -> int:
    try:
        return main()
    except InvalidBoardVersion as e:
        logger.error("ERROR: %s", e)
        return 1
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(cli_main())
