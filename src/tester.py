#!/usr/bin/env python

from logging import basicConfig, INFO, DEBUG
from time import sleep

import argparse

from monitor.adapters.sensor import SensorAdapter
from monitor.adapters.syren import SyrenAdapter

basicConfig(format="%(message)s", level=DEBUG)


def test_sensor_adapter():
    sa = SensorAdapter()
    sa.get_values()

    # avoid exception when gpiozero cleanup
    del sa


def test_syren_adapter():
    sa = SyrenAdapter()
    sa.alert(start=True)
    sleep(3)
    sa.alert(start=False)
    sleep(3)

    # avoid exception when gpiozero cleanup
    del sa


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("adapter", choices=["sensor", "syren"])

    args = parser.parse_args()
    test_function = f"test_{args.adapter}_adapter"
    globals()[test_function]()


if __name__ == "__main__":
    main()
