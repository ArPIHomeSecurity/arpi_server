#!/usr/bin/env python

from logging import basicConfig, INFO, DEBUG
from time import sleep

import argparse

from monitor.adapters.sensor import SensorAdapter
from monitor.adapters.relay import RelayAdapter

basicConfig(format="%(message)s", level=DEBUG)


def test_sensor_adapter():
    sa = SensorAdapter()

    for i in range(0, 9):
        sa.get_values()
        sleep(1)


def test_relay_adapter():
    ra = RelayAdapter()

    for i in range(0, 8):
        ra.control_relay(i, 1)
        sleep(1)
    for i in range(0, 8):
        ra.control_relay(i, 0)
        sleep(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("adapter", choices=["sensor", "relay"])

    args = parser.parse_args()
    test_function = f"test_{args.adapter}_adapter"
    globals()[test_function]()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        exit(0)
