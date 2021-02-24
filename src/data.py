#!/usr/bin/env python
# -*- coding: utf-8 -*-

import argparse

from sqlalchemy.exc import ProgrammingError

from monitoring.constants import ROLE_ADMIN, ROLE_USER

from models import Keypad, KeypadType, Sensor, SensorType, User, Zone
from monitoring.database import Session
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
        print(" - Clear table %s" % table)
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
    session.add_all([kt1])
    print(" - Created keypad types")

    k1 = Keypad(keypad_type=kt1)
    session.add_all([k1])
    print(" - Created keypads")

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
    z2 = Zone(name="Away delayed", away_delay=20, description="Alert delayed when armed AWAY")
    z3 = Zone(name="Stay delayed", stay_delay=20, description="Alert delayed when armed STAY")
    z4 = Zone(name="Stay", stay_delay=None, description="No alert when armed STAY")
    z5 = Zone(name="Away/Stay delayed", away_delay=40, stay_delay=20, description="Alert delayed when armed AWAY/STAY")
    z6 = Zone(name="Tamper", disarmed_delay=0, away_delay=None, stay_delay=None, description="Sabotage alert")
    session.add_all([z1, z2, z3, z4, z5, z6])
    print(" - Created zones")

    session.add_all(SENSOR_TYPES)
    print(" - Created sensor types")

    s1 = Sensor(channel=0, sensor_type=SENSOR_TYPES[0], zone=z5, description="Garage")
    s2 = Sensor(channel=1, sensor_type=SENSOR_TYPES[0], zone=z5, description="Hall")
    s3 = Sensor(channel=2, sensor_type=SENSOR_TYPES[2], zone=z5, description="Front door")
    s4 = Sensor(channel=3, sensor_type=SENSOR_TYPES[0], zone=z3, description="Kitchen")
    s5 = Sensor(channel=4, sensor_type=SENSOR_TYPES[0], zone=z1, description="Living room")
    s6 = Sensor(channel=5, sensor_type=SENSOR_TYPES[0], zone=z4, description="Children's room")
    s7 = Sensor(channel=6, sensor_type=SENSOR_TYPES[0], zone=z4, description="Bedroom")
    s8 = Sensor(channel=7, sensor_type=SENSOR_TYPES[1], zone=z6, description="Tamper")
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
    admin_user.add_registration_code("123")
    session.add_all([admin_user, User(name="Chuck Norris", role=ROLE_USER, access_code="1111")])
    print(" - Created users")

    z1 = Zone(name="No delay", description="Alert with no delay")
    z2 = Zone(name="Tamper", disarmed_delay=0, away_delay=None, stay_delay=None, description="Sabotage alert")
    z3 = Zone(name="Away/stay delayed", away_delay=5, stay_delay=5, description="Alert delayed when armed AWAY or STAY")
    z4 = Zone(name="Stay delayed", stay_delay=5, description="Alert delayed when armed STAY")
    z5 = Zone(name="Stay", stay_delay=None, description="No alert when armed STAY")
    session.add_all([z1, z2, z3, z4, z5])
    print(" - Created zones")

    session.add_all(SENSOR_TYPES)
    print(" - Created sensor types")

    s1 = Sensor(channel=0, sensor_type=SENSOR_TYPES[0], zone=z3, description="Garage")
    s2 = Sensor(channel=1, sensor_type=SENSOR_TYPES[2], zone=z5, description="Test room")
    s3 = Sensor(channel=2, sensor_type=SENSOR_TYPES[1], zone=z2, description="Tamper")
    session.add_all([s1, s2, s3])
    print(" - Created sensors")

    kt1 = KeypadType(1, "DSC", "DSC keybus (DSC PC-1555RKZ)")
    session.add_all([kt1])
    print(" - Created keypad types")

    k1 = Keypad(keypad_type=kt1)
    session.add_all([k1])
    print(" - Created keypads")

    session.commit()


def main():
    environments = []
    for attribute, value in globals().items():
        if attribute.startswith("env_"):
            environments.append(attribute.replace("env_", ""))

    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--create", action="store_true", help="Create database content")
    parser.add_argument("-d", "--delete", action="store_true", help="Delete database content")
    parser.add_argument("-e", "--environment", required=True, help="/".join(environments), metavar="environment")
    args = parser.parse_args()

    if args.delete:
        cleanup()

    if args.create:
        create_method = globals()["env_" + args.environment]
        print("Creating '%s' environment..." % args.environment)
        create_method()
        print("Environment create")


if __name__ == "__main__":
    main()
