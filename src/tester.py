#!/usr/bin/env python

import logging
from logging import basicConfig, INFO, DEBUG
from time import sleep

import argparse

from monitor.adapters.power import PowerAdapter
from monitor.adapters.sensor import SensorAdapter
from monitor.adapters.relay import RelayAdapter


def test_sensor_adapter():
    adapter = SensorAdapter()

    for i in range(0, 9):
        values = adapter.get_values()
        logging.info("Values: %s", values)
        sleep(1)


def test_power_adapter():
    adapter = PowerAdapter()

    for i in range(0, 9):
        logging.info("Source: %s", adapter.source_type)
        sleep(1)


def test_relay_adapter():
    adapter = RelayAdapter()

    faults = adapter._read_faults()
    logging.info("Faults: %s", faults)

    OUTPUT_COUNT = 8
    # create array with size OUTPUT_COUNT and fill it with zeros
    outputs = [0] * OUTPUT_COUNT
    for i in range(0, OUTPUT_COUNT):
        adapter.control_relay(i, 1)
        outputs[i] = 1
        logging.info("Outputs: %s", outputs)
        sleep(1)
    for i in range(0, OUTPUT_COUNT):
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
        main()
    except KeyboardInterrupt:
        print("\n")
