#!/usr/bin/env python3
"""
ArPI Dynamic DNS Update Tool
"""

import argparse
import logging

from psycopg2 import OperationalError

from tools.dyndns import DynDns


def main():
    parser = argparse.ArgumentParser(description="Update IP address at DNS provider")
    parser.add_argument("-v", "--verbose", action="store_true", help="increase output verbosity")
    parser.add_argument("-f", "--force", action="store_true", help="force update")

    args = parser.parse_args()

    logging.basicConfig(
        format="%(asctime)-15s: %(message)s",
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    dyndns = DynDns()
    dyndns.update_ip(force=args.force)


def cli_main():
    try:
        main()
    except KeyboardInterrupt:
        pass
    except OperationalError as database_error:
        logging.warning("Database error: %s", database_error)


if __name__ == "__main__":
    cli_main()
