#!/usr/bin/env python3

import argparse
import logging
import sys
from logging import basicConfig

from sqlalchemy import select

from monitor.database import get_database_session
from utils.models import Card, User, hash_code, hash_code_2

logger = logging.getLogger(__name__)


def check_hashes():
    """
    Check if the database is using bcrypt hashes

    Returns:
        int: 0 if all hashes are bcrypt, 1 if any hash is not bcrypt
    """
    db_session = get_database_session()

    # Check if the database is using bcrypt hashes
    users = db_session.scalars(select(User)).all()
    for tmp_user in users:
        if (
            (tmp_user.access_code and not tmp_user.access_code.startswith("$2b$"))
            or (tmp_user.fourkey_code and not tmp_user.fourkey_code.startswith("$2b$"))
            or (tmp_user.registration_code and not tmp_user.registration_code.startswith("$2b$"))
        ):
            logger.info("User %s(%d) is not using bcrypt hashes.", tmp_user.name, tmp_user.id)
            return 1

    cards = db_session.scalars(select(Card)).all()
    for tmp_card in cards:
        if not tmp_card.code.startswith("$2b$"):
            logger.info(
                "Card %s(%d) is not using bcrypt hashes.", tmp_card.card_number, tmp_card.id
            )
            return 1

    logger.info("All hashes are using bcrypt.")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Hash text to database format")
    parser.add_argument(
        "-c", "--check", action="store_true", help="Check if database uses bcrypt hashes"
    )
    parser.add_argument("input", nargs="?", default=None, help="Input string to hash")

    args = parser.parse_args()

    if args.check:
        sys.exit(check_hashes())
    elif args.input:
        logger.info("SHA256 hash: %s", hash_code(args.input))
        logger.info("BCrypt hash: %s", hash_code_2(args.input))


def cli_main():
    try:
        basicConfig(level=logging.INFO, format="%(message)s")
        main()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    cli_main()
