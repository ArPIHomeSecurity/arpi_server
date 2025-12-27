#!/usr/bin/env python3
"""
ArPI Clock Management Tool
"""

import argparse
import logging

from utils.constants import LOG_CLOCK
from tools.clock import Clock


logger = logging.getLogger(LOG_CLOCK)


def main():
    parser = argparse.ArgumentParser(
        description="List or synchronize system clock with HW clock or NTP server"
    )
    parser.add_argument(
        "-s",
        "--sync",
        action="store_true",
        help="synchronize system clock with HW clock or NTP server",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="increase output verbosity")

    args = parser.parse_args()

    logging.basicConfig(
        format="%(asctime)-15s %(message)s",
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    clock = Clock()
    if args.sync:
        clock.sync_clock()
        return

    logger.info("Timezone: %s", clock.get_timezone())
    logger.info("HW Clock: %s", clock.get_time_hw())
    logger.info("NTP Clock: %s", clock.get_time_ntp())
    logger.info("Uptime: %s", clock.get_uptime())


def cli_main():
    try:
        main()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    cli_main()
