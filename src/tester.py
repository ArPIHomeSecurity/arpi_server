#!/usr/bin/env python

import argparse
import logging
import os
from time import sleep
from typing import List

try:
    import lgpio
except ImportError:
    lgpio = None

from dotenv import load_dotenv

from constants import LOG_ADSENSOR
from monitor.adapters.keypads import get_wiegand_keypad
from monitor.adapters.keypads.base import Action
from monitor.logger import ArgusLogger
from monitor.output import OUTPUT_NAMES

try:
    from monitor.adapters.output import get_output_adapter
    from monitor.adapters.power import get_power_adapter
    from monitor.adapters.sensor import get_sensor_adapter
except Exception as error:
    if isinstance(error, lgpio.error):
        logging.error(
            "Can't connect to GPIO. Please stop the argus_server and argus_monitor services!"
        )
    else:
        logging.exception("Error importing adapters: %s", error)

    exit(1)

def print_channels(correct_channels, values):
    for idx, value in enumerate(values):
        print(f"\033[2K", end="")  # Clear line
        print(f"CH{idx + 1:02d}: {value:.2f}", end="")
        if correct_channels[idx]:
            print(" ✅", end="")
        else:
            print(" ❓", end="")
        print()

def test_sensor_adapter(board_version):
    """
    Check the state of the sensor inputs and mark the ones that changed.
    """
    adapter = get_sensor_adapter(board_version)

    # mark channels as correct if they changed
    correct_channels = [False] * int(os.environ["INPUT_NUMBER"])
    previous = []
    values = []
    try:
        while True:
            values = adapter.get_values()
            values = [round(v, 2) for v in values]

            # Clear previous output and print current values
            if previous:
                print(f"\033[{len(values)}A", end="")  # Move cursor up

            sleep(1)

            if previous:
                for idx, value in enumerate(values):
                    if abs(value - previous[idx]) > 0.2:
                        correct_channels[idx] = True

            previous = values

            print_channels(correct_channels, values)

            # break if all correct
            if all(correct_channels):
                break
    except KeyboardInterrupt:
        print("\n")

    if not all(correct_channels):
        print_channels(correct_channels, values)

        

def test_power_adapter(board_version):
    """
    Check the power source type.
    """
    adapter = get_power_adapter(board_version)

    logging.info("Press Ctrl-C to exit")

    while True:
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
            {name: state for name, state in zip(OUTPUT_NAMES.values(), adapter.states)},
        )
        sleep(2)

    # turn off outputs
    for i in range(output_count):
        adapter.control_channel(i, False)
        logging.info(
            "Outputs: %s",
            {name: state for name, state in zip(OUTPUT_NAMES.values(), adapter.states)},
        )
        sleep(2)


def test_keypad_adapter(board_version):
    """
    Test the keypad adapter.
    """
    adapter = get_wiegand_keypad(board_version)

    logging.info("Press Ctrl-C to exit")

    while True:
        adapter.communicate()
        while True:
            last_action = adapter.last_action()
            if not last_action:
                break

            if last_action == Action.CARD:
                logging.info("Card presented: %s", adapter.get_card())
            elif last_action == Action.KEY:
                logging.info("Key pressed: %s", adapter.get_last_key())
            elif last_action == Action.FUNCTION:
                logging.info("Function activated: %s", adapter.get_function())
        sleep(1)


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
