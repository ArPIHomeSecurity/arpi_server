#!/usr/bin/env python

from dotenv import load_dotenv

load_dotenv()
load_dotenv("secrets.env")

import argparse
import logging
from logging import basicConfig

from models import hash_code, hash_code_2, User, Card
from monitor.database import get_database_session


basicConfig(level=logging.INFO, format="%(message)s")


def check_hashes():
    db_session = get_database_session()

    # Check if the database is using bcrypt hashes
    users = db_session.query(User).all()
    for tmp_user in users:
        if (
            (tmp_user.access_code and not tmp_user.access_code.startswith("$2b$"))
            or (tmp_user.fourkey_code and not tmp_user.fourkey_code.startswith("$2b$"))
            or (tmp_user.registration_code and not tmp_user.registration_code.startswith("$2b$"))
        ):
            logging.info("User %s(%d) is not using bcrypt hashes.", tmp_user.name, tmp_user.id)
            return 1

    cards = db_session.query(Card).all()
    for tmp_card in cards:
        if not tmp_card.code.startswith("$2b$"):
            logging.info(
                "Card %s(%d) is not using bcrypt hashes.", tmp_card.card_number, tmp_card.id
            )
            return 1

    logging.info("All hashes are using bcrypt.")
    return 0


parser = argparse.ArgumentParser(description="Hash text to database format")
parser.add_argument(
    "-c", "--check", action="store_true", help="Check if database uses bcrypt hashes"
)
parser.add_argument(
    "input", nargs="?", default=None, help="Input string to hash"
)

args = parser.parse_args()

if args.check:
    exit(check_hashes())
elif args.input:
    logging.info("SHA256 hash: %s", hash_code(args.input))
    logging.info("BCrypt hash: %s", hash_code_2(args.input))
