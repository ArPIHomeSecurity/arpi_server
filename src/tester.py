#!/usr/bin/env python

import logging
import os

from time import sleep

import argparse
from typing import List
from dotenv import load_dotenv

from monitor.adapters.power import PowerAdapter
from monitor.adapters.sensor import SensorAdapter
from monitor.adapters.output import OutputAdapter


def test_sensor_adapter():
    """
    Check the state of the sensor inputs and mark the ones that changed.
    """
    adapter = SensorAdapter()

    # mark channels as correct if they changed
    correct_channels = [False] * int(os.environ["INPUT_NUMBER"])
    previous = []
    for _ in range(99):
        values = adapter.get_values()
        logging.info("Values: %s", values)
        sleep(1)

        if previous:
            for idx, value in enumerate(values):
                if value != previous[idx]:
                    correct_channels[idx] = True

        previous = values

    for idx, correct in enumerate(correct_channels):
        logging.info("Channel CH%02d %s", idx+1, u"\u2705" if correct else u"\u274C")


def test_power_adapter():
    """
    Check the power source type.
    """
    adapter = PowerAdapter()

    for _ in range(9):
        logging.info("Source: %s", adapter.source_type)
        sleep(1)


def test_output_adapter():
    """
    Control the output channels.
    """
    adapter = OutputAdapter()

    OUTPUT_COUNT = 8
    outputs = [0] * OUTPUT_COUNT
    for i in range(OUTPUT_COUNT):
        adapter.control_channel(i, True)
        outputs[i] = 1
        logging.info("Outputs: %s", outputs)
        sleep(1)

    for i in range(OUTPUT_COUNT):
        adapter.control_channel(i, False)
        outputs[i] = 0
        logging.info("Outputs: %s", outputs)
        sleep(1)


def list_adapters() -> List[str]:
    adapters = []
    for g in globals():
        if g.startswith("test_") and g.endswith("_adapter"):
            adapters.append(g.replace("test_", "").replace("_adapter", ""))
    return adapters


def main():
    parser = argparse.ArgumentParser(
        description="Testing script for adapters which control the hardware components"
    )
    parser.add_argument("adapter", choices=list_adapters())
    parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()
    if args.verbose:
        logging.basicConfig(format="%(message)s", level=logging.DEBUG)
    else:
        logging.basicConfig(format="%(message)s", level=logging.INFO)

    test_function = f"test_{args.adapter}_adapter"
    globals()[test_function]()


if __name__ == "__main__":
    try:
        load_dotenv()
        main()
    except KeyboardInterrupt:
        print("\n")
