#!/usr/bin/env python

import argparse
import logging
import os

from time import sleep
from typing import List

import lgpio

from constants import LOG_ADSENSOR
from dotenv import load_dotenv

from monitor.logger import ArgusLogger
from monitor.output import OUTPUT_NAMES


try:
    from monitor.adapters.power import get_power_adapter
    from monitor.adapters.sensor import get_sensor_adapter
    from monitor.adapters.output import get_output_adapter
except lgpio.error:
    logging.error("Can't connect to GPIO. Please stop the argus_server and argus_monitor services!")
    exit(1)


def test_sensor_adapter(board_version):
    """
    Check the state of the sensor inputs and mark the ones that changed.
    """
    adapter = get_sensor_adapter(board_version)
    try:
        # mark channels as correct if they changed
        correct_channels = [False] * int(os.environ["INPUT_NUMBER"])
        previous = []
        for _ in range(99):
            values = adapter.get_values()
            values = [round(v, 2) for v in values]
            logging.info("Values: %s", values)
            sleep(1)

            if previous:
                for idx, value in enumerate(values):
                    if value != previous[idx]:
                        correct_channels[idx] = True

            previous = values

            # break if all correct
            if all(correct_channels):
                break

        for idx, correct in enumerate(correct_channels):
            logging.info("Channel CH%02d %s", idx + 1, "\u2705" if correct else "\u274c")
    finally:
        # Ensure GPIO/SPI resources released promptly
        try:
            adapter.close()
        except (OSError, RuntimeError, ValueError):
            pass


def test_power_adapter(board_version):
    """
    Check the power source type.
    """
    adapter = get_power_adapter(board_version)

    for _ in range(9):
        logging.info("Source: %s", adapter.source_type)
        sleep(1)


def test_output_adapter(board_version):
    """
    Control the output channels.
    """
    adapter = get_output_adapter(board_version)
    output_count = int(os.environ.get("OUTPUT_NUMBER", 8))

    # turn on outputs
    for i in range(output_count):
        adapter.control_channel(i, True)
        logging.info(
            "Output: %s",
            [
                (name, "ON" if state else "OFF")
                for name, state in zip(OUTPUT_NAMES.values(), adapter.states)
            ],
        )
        sleep(2)

    # turn off outputs
    for i in range(output_count):
        adapter.control_channel(i, False)
        logging.info(
            "Outputs: %s",
            [
                (name, "ON" if state else "OFF")
                for name, state in zip(OUTPUT_NAMES.values(), adapter.states)
            ],
        )
        sleep(2)


def list_adapters() -> List[str]:
    """
    List all available adapter test functions.
    """
    adapters = []
    for g in globals():
        if g.startswith("test_") and g.endswith("_adapter"):
            adapters.append(g.replace("test_", "").replace("_adapter", ""))
    return adapters


def main():
    """
    Main function to run the adapter tests.
    """
    parser = argparse.ArgumentParser(
        description="Testing script for adapters which control the hardware components"
    )
    parser.add_argument("adapter", choices=list_adapters())
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument(
        "-b", "--board-version", type=int, choices=[2, 3], help="Board version (2=GPIO, 3=SPI/AD)"
    )

    # add the ArgusLogger as handler
    logger = logging.getLogger(LOG_ADSENSOR)
    logger.__class__ = ArgusLogger

    args = parser.parse_args()
    if args.verbose:
        logging.basicConfig(format="%(message)s", level=logging.DEBUG)
    else:
        logging.basicConfig(format="%(message)s", level=logging.INFO)

    test_function = f"test_{args.adapter}_adapter"
    globals()[test_function](args.board_version)


if __name__ == "__main__":
    try:
        load_dotenv()
        main()
    except KeyboardInterrupt:
        print("\n")
