#!/usr/bin/env python3
from dotenv import load_dotenv

load_dotenv()
load_dotenv("secrets.env")

import argparse

from sqlalchemy.exc import ProgrammingError

from constants import ROLE_ADMIN, ROLE_USER
from models import Area, Keypad, KeypadType, Sensor, SensorType, User, Zone
from monitor.database import Session
from models import metadata


SENSOR_TYPES = [
    SensorType(1, name="Motion", description="Detect motion"),
    SensorType(2, name="Tamper", description="Detect sabotage"),
    SensorType(3, name="Open", description="Detect opening"),
    SensorType(4, name="Break", description="Detect glass break"),
]

session = Session()


def cleanup():
    print("Clean up database...")
    for table in reversed(metadata.sorted_tables):
        print(f" - Clear table {table}")
        try:
            session.execute(table.delete())
            session.commit()
        except ProgrammingError:
            session.rollback()
    print("Database is empty")


def env_prod():
    admin_user = User(name="Administrator", role=ROLE_ADMIN, access_code="1234")
    admin_user.add_registration_code("ABCD1234")
    session.add(admin_user)
    print(" - Created admin user")

    session.add_all(SENSOR_TYPES)
    print(" - Created sensor types")

    kt1 = KeypadType(1, "DSC", "DSC keybus (DSC PC-1555RKZ)")
    kt2 = KeypadType(2, "WIEGAND", "Wiegand keypad")
    session.add_all([kt1, kt2])
    print(" - Created keypad types")

    k1 = Keypad(keypad_type=kt1)
    session.add_all([k1])
    print(" - Created keypads")

    a1 = Area(name="House")
    session.add(a1)
    print(" - Created area")

    session.commit()


def env_live_01():
    session.add_all(
        [
            User(name="Administrator", role=ROLE_ADMIN, access_code="1234"),
            User(name="Chuck.Norris", role=ROLE_USER, access_code="1111"),
        ]
    )
    print(" - Created users")

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
    z4 = Zone(
        name="Stay", stay_alert_delay=None, description="No alert when armed STAY"
    )
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
    print(" - Created zones")

    session.add_all(SENSOR_TYPES)
    print(" - Created sensor types")

    area = Area(name="House")
    session.add(area)
    print(" - Created area")

    s1 = Sensor(
        channel=0, sensor_type=SENSOR_TYPES[0], zone=z5, name="Garage", area=area
    )
    s2 = Sensor(
        channel=1, sensor_type=SENSOR_TYPES[0], zone=z5, name="Hall", area=area
    )
    s3 = Sensor(
        channel=2,
        sensor_type=SENSOR_TYPES[2],
        zone=z5,
        name="Front door",
        area=area,
    )
    s4 = Sensor(
        channel=3,
        sensor_type=SENSOR_TYPES[0],
        zone=z3,
        name="Kitchen",
        area=area,
    )
    s5 = Sensor(
        channel=4,
        sensor_type=SENSOR_TYPES[0],
        zone=z1,
        name="Living room",
        area=area,
    )
    s6 = Sensor(
        channel=5,
        sensor_type=SENSOR_TYPES[0],
        zone=z4,
        name="Children's room",
        area=area,
    )
    s7 = Sensor(
        channel=6,
        sensor_type=SENSOR_TYPES[0],
        zone=z4,
        name="Bedroom",
        area=area,
    )
    s8 = Sensor(
        channel=7, sensor_type=SENSOR_TYPES[1], zone=z6, name="Tamper", area=area
    )
    session.add_all([s1, s2, s3, s4, s5, s6, s7, s8])
    print(" - Created sensors")

    kt1 = KeypadType(1, "DSC", "DSC keybus (DSC PC-1555RKZ)")
    session.add_all([kt1])
    print(" - Created keypad types")

    k1 = Keypad(keypad_type=kt1)
    session.add_all([k1])
    print(" - Created keypads")

    session.commit()


def env_test_01():
    admin_user = User(name="Administrator", role=ROLE_ADMIN, access_code="1234")
    admin_user.add_registration_code("ABCD1234")
    session.add_all(
        [admin_user, User(name="Chuck Norris", role=ROLE_USER, access_code="1111")]
    )
    print(" - Created users")

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
        name="Stay", stay_alert_delay=None, description="No alert when armed STAY"
    )
    session.add_all([z1, z2, z3, z4, z5])
    print(" - Created zones")

    session.add_all(SENSOR_TYPES)
    print(" - Created sensor types")

    area = Area(name="House")
    session.add(area)
    print(" - Created area")

    s1 = Sensor(
        channel=0,
        sensor_type=SENSOR_TYPES[0],
        area=area,
        zone=z3,
        name="Garage",
        description="Garage movement sensor",
        silent_alert=True,
    )
    s2 = Sensor(
        channel=1,
        sensor_type=SENSOR_TYPES[2],
        area=area,
        zone=z5,
        name="Test room",
        description="Test room door sensor",
    )
    s3 = Sensor(
        channel=2,
        sensor_type=SENSOR_TYPES[1],
        area=area,
        zone=z2,
        name="Tamper",
        description="Sabotage wire",
    )
    session.add_all([s1, s2, s3])
    print(" - Created sensors")

    kt1 = KeypadType(1, "DSC", "DSC keybus (DSC PC-1555RKZ)")
    kt2 = KeypadType(2, "WIEGAND", "Wiegand keypad")
    kt3 = KeypadType(3, "MOCK", "MOCK keypad")
    session.add_all([kt1, kt2, kt3])
    print(" - Created keypad types")

    k1 = Keypad(keypad_type=kt1)
    session.add_all([k1])
    print(" - Created keypads")

    session.commit()


def env_admin_registration():
    admin_user = session.query(User).filter(User.role == ROLE_ADMIN).first()
    code = admin_user.add_registration_code("ABCD")
    print("Code: ", code)
    admin_user.update({"access_code": "1234"})
    print("Password: ", "1234")
    session.commit()
    print("Admin registration added and password changed")


def main():
    environments = [
        attribute.replace("env_", "")
        for attribute in globals()
        if attribute.startswith("env_")
    ]

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-d", "--delete", action="store_true", help="Delete database content"
    )
    parser.add_argument(
        "-c",
        "--create",
        metavar="environment",
        help=f'Create database content (environments: {", ".join(environments)})',
    )

    args = parser.parse_args()

    if args.delete:
        cleanup()

    if args.create:
        create_method = globals()[f"env_{args.create}"]
        print(f"Creating '{args.create}' environment...")
        create_method()
        print("Environment created")


if __name__ == "__main__":
    main()
