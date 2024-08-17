#!/usr/bin/env python
from dotenv import load_dotenv
load_dotenv()
load_dotenv("secrets.env")


# pylint: disable=wrong-import-position,wrong-import-order
import contextlib
import logging

from argparse import ArgumentParser, RawTextHelpFormatter, ArgumentTypeError
from datetime import datetime as dt
from dateutil.tz.tz import tzlocal
from logging import basicConfig
from time import sleep

from models import User
from monitor.database import get_database_session


description = """
Adding new registration code to restore access for a given user.

Executing without a user id you will get a list of users.
"""

session = get_database_session()

basicConfig(level=logging.INFO, format="%(message)s")


def get_users():
    logging.info("Users:")
    for user in session.query(User).all():
        logging.info("ID: %s = %s (%s): ", user.id, user.name, user.role)


def wait(seconds=5):
    LINE_UP = '\033[1A'
    LINE_CLEAR = '\x1b[2K'

    with contextlib.suppress(KeyboardInterrupt):
        for s in range(seconds):
            print(f"Overwriting! Press CTRL+C if you want to stop in {seconds - s}s!")
            sleep(1)
            print(LINE_UP, end=LINE_CLEAR)

        print("Overwriting! Press CTRL+C if you want to stop!           ")


def new_registration_code(user_id, code, expiry):
    user = session.query(User).filter(User.id == user_id).one()

    if user.registration_code is not None:
        if user.registration_expiry and dt.now(tzlocal()) < user.registration_expiry:
            logging.info("User has active registration code (until %s)", user.registration_expiry.strftime("%Y-%m-%d %H:%M:%S"))
        elif user.registration_expiry is None:
            logging.info("User has active registration code (never expires)")
        else:
            logging.info("User has expired registration code")

        wait()
    else:
        logging.info("User doesn't have registration code")

    registration_code = user.add_registration_code(registration_code=code, expiry=expiry)

    logging.info("\n------------------------------")
    logging.info("Code generated for user (id: %s): %s", user.id, user.name)

    if code is None or code != registration_code:
        logging.info("New registration code: %s", registration_code)

    if expiry is None:
        logging.info("The code never expires")
    else:
        logging.info("The code expires in %s seconds", expiry)

    session.commit()


def main():
    def check_positive(value):
        ivalue = int(value)
        if ivalue <= 0:
            raise ArgumentTypeError(f"{value} is an invalid positive integer value")
        return ivalue

    parser = ArgumentParser(description=description, formatter_class=RawTextHelpFormatter)
    parser.add_argument("-c", "--code", required=False, help="New registration code")
    parser.add_argument("-u", "--user", required=False, help="The id of the user")
    parser.add_argument("-e", "--expiry", required=False, type=check_positive, help="The expiry of the code in seconds (or never expires)")

    args = parser.parse_args()

    if args.user:
        new_registration_code(user_id=args.user, code=args.code, expiry=args.expiry)
    else:
        get_users()


if __name__ == '__main__':
    main()
