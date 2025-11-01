#!/usr/bin/env python3

import argparse
import logging
import os
import subprocess
from time import sleep
from typing import List

try:
    import lgpio
except ImportError:
    lgpio = None


from constants import LOG_ADSENSOR
from monitor.adapters.keypads import get_wiegand_keypad
from monitor.adapters.keypads.base import Action
from monitor.adapters.output import get_output_adapter
from monitor.adapters.power import get_power_adapter
from monitor.adapters.sensor import get_sensor_adapter
from monitor.logger import ArgusLogger
from monitor.output import OUTPUT_NAMES


def print_channels(correct_channels, values):
    for idx, value in enumerate(values):
        print(f"\033[2K", end="")  # Clear line
        print(f"CH{idx + 1:02d}: {value:.2f}", end="")
        if correct_channels[idx]:
            print(" ✅", end="")
        else:
            print(" ❓", end="")
        print()


def test_sensor_adapter(board_version) -> bool:
    """
    Check the state of the sensor inputs and mark the ones that changed.
    """
    adapter = get_sensor_adapter(board_version)
    if not adapter.is_initialized():
        logging.error("Sensor adapter not initialized properly. Exiting test.")
        logging.info("Check if argus_monitor service is running and using the GPIO.")
        return False

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
                logging.info("All channels verified successfully.")
                return True
    except KeyboardInterrupt:
        print("\n")

    if not all(correct_channels):
        print_channels(correct_channels, values)
        logging.warning("Some channels were not verified.")
        return False


def test_power_adapter(board_version) -> bool:
    """
    Check the power source type.
    """
    adapter = get_power_adapter(board_version)
    if not adapter.is_initialized():
        logging.error("Power adapter not initialized properly. Exiting test.")
        logging.info("Check if argus_monitor service is running and using the GPIO.")
        return False

    logging.info("Press Ctrl-C to exit")

    while True:
        logging.info("Source: %s", adapter.source_type)
        sleep(1)


def test_output_adapter(board_version) -> bool:
    """
    Control the output channels.
    """
    adapter = get_output_adapter(board_version)
    if not adapter.is_initialized():
        logging.error("Output adapter not initialized properly. Exiting test.")
        logging.info("Check if argus_monitor service is running and using the GPIO.")
        return False

    output_count = int(os.environ.get("OUTPUT_NUMBER", 8))

    # turn on outputs
    for i in range(output_count):
        adapter.control_channel(i, True)
        logging.info(
            "Outputs: %s",
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

    return True


def test_keypad_adapter(board_version) -> bool:
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

def check_service_running() -> bool:
    """
    Check if argus_monitor service is running.
    """
    try:
        output = subprocess.check_output(["systemctl", "is-active", "argus_monitor"], stderr=subprocess.STDOUT)
        return output.strip() == b"active"
    except subprocess.CalledProcessError:
        return False

def main() -> int:
    """
    Main function to run the adapter tests.
    """
    parser = argparse.ArgumentParser(
        description="Testing script for adapters which control the hardware components"
    )
    parser.add_argument("adapter", choices=list_adapters())
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument(
        "-b",
        "--board-version",
        default=os.getenv("BOARD_VERSION"),
        type=int,
        choices=[2, 3],
        help="Board version (2=GPIO/OPTO, 3=SPI/AD)",
    )

    # add the ArgusLogger as handler
    logger = logging.getLogger(LOG_ADSENSOR)
    logger.__class__ = ArgusLogger

    args = parser.parse_args()
    if args.verbose:
        logging.basicConfig(format="%(message)s", level=logging.DEBUG)
    else:
        logging.basicConfig(format="%(message)s", level=logging.INFO)

    if check_service_running():
        logging.error("argus_monitor service is running. Please stop it before running the tests.")
        return 1

    test_function = f"test_{args.adapter}_adapter"
    result = globals()[test_function](args.board_version)
    if not result:
        return 1

    return 0


if __name__ == "__main__":
    try:
        exit(main())
    except KeyboardInterrupt:
        print("\n")
