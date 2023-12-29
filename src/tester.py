#!/usr/bin/env python

import logging
import os

from logging import basicConfig, INFO, DEBUG
from time import sleep

import argparse
from dotenv import load_dotenv

from monitor.adapters.power import PowerAdapter
from monitor.adapters.sensor import SensorAdapter
from monitor.adapters.relay import RelayAdapter


def test_sensor_adapter():
    adapter = SensorAdapter()

    correct_channel = [False] * os.environ["INPUT_NUMBER"]
    previous = []
    for _ in range(99):
        values = adapter.get_values()
        logging.info("Values: %s", values)
        sleep(1)

        if previous:
            for idx, value in enumerate(values):
                if value != previous[idx]:
                    correct_channel[idx] = True

        previous = values

    for idx, correct in enumerate(correct_channel):
        logging.info("Channel CH%02d %s", idx+1, u"\u2705" if correct else u"\u274C")


def test_power_adapter():
    adapter = PowerAdapter()

    for _ in range(9):
        logging.info("Source: %s", adapter.source_type)
        sleep(1)


def test_relay_adapter():
    adapter = RelayAdapter()

    faults = adapter._read_faults()
    logging.info("Faults: %s", faults)

    OUTPUT_COUNT = 8
    # create array with size OUTPUT_COUNT and fill it with zeros
    outputs = [0] * OUTPUT_COUNT
    for i in range(OUTPUT_COUNT):
        adapter.control_relay(i, 1)
        outputs[i] = 1
        logging.info("Outputs: %s", outputs)
        sleep(1)

    for i in range(OUTPUT_COUNT):
        adapter.control_relay(i, 0)
        outputs[i] = 0
        logging.info("Outputs: %s", outputs)
        sleep(1)


def main():
    parser = argparse.ArgumentParser(
        description="Testing script for adapters which control the hardware components"
    )
    parser.add_argument("adapter", choices=["power", "sensor", "relay"])
    parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()
    if args.verbose:
        basicConfig(format="%(message)s", level=DEBUG)
    else:
        basicConfig(format="%(message)s", level=INFO)

    test_function = f"test_{args.adapter}_adapter"
    globals()[test_function]()


if __name__ == "__main__":
    try:
        load_dotenv()
        main()
    except KeyboardInterrupt:
        print("\n")
