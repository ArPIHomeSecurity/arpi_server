"""
Utility functions to detect alerts and errors based on sensor readings.
"""

import logging
from os import environ

from models import ChannelTypes, Sensor, SensorEOLCount
from monitor.sensor.wirings import PullUpConfig, PullUpDownConfig
from constants import LOG_SENSORS

TOLERANCE_V2 = 0.01
TOLERANCE_V3 = 0.05

CHANNEL_CUT = 1.0
CHANNEL_SHORTAGE = 0.0

# pull-up resistor
R_PULL_UP = 2000
# pull-down resistor
R_PULL_DOWN = 20000

# EOL resistor for channel A
R_A = 5600
# EOL resistor for channel B
R_B = 3000

# Create a default configuration instance for calculating channel constants
# wiring_config = PullUpConfig(R_PULL_UP, R_A, R_B)
wiring_config = PullUpDownConfig(R_PULL_UP, R_PULL_DOWN, R_A, R_B)

BOARD_VERSION = int(environ.get("BOARD_VERSION", 1))

logger = logging.getLogger(LOG_SENSORS)


def is_close(a, b, tolerance=0.0):
    """
    Check if two values are close enough.
    """
    return abs(a - b) < tolerance


def detect_alert(sensor: Sensor, current_value: float):
    if BOARD_VERSION == 2:
        return detect_alert_v2(sensor, current_value)
    elif BOARD_VERSION == 3:
        return detect_alert_v3(sensor, current_value)
    else:
        raise ValueError(f"Unsupported BOARD_VERSION: {BOARD_VERSION}")


def detect_error(sensor: Sensor, current_value: float) -> bool:
    if BOARD_VERSION == 2:
        return False
    elif BOARD_VERSION == 3:
        return detect_error_v3(sensor, current_value)
    else:
        raise ValueError(f"Unsupported BOARD_VERSION: {BOARD_VERSION}")


def detect_alert_v2(sensor: Sensor, current_value: float) -> bool:
    return not is_close(current_value, sensor.reference_value, TOLERANCE_V2)


def detect_alert_v3(sensor: Sensor, current_value: float) -> bool:
    """
    Detect alert condition based on sensor configuration and current value.
    """
    if sensor.channel_type == ChannelTypes.BASIC:
        logger.trace(
            "Detecting BASIC alert for sensor %s: %.3f-%.3f<%.3f",
            sensor.name,
            sensor.reference_value,
            current_value,
            TOLERANCE_V2
        )
        # compare actual value to reference value
        return not is_close(current_value, sensor.reference_value, TOLERANCE_V2)

    if sensor.channel_type == ChannelTypes.NORMAL:
        reference_value_a = wiring_config.select_strategy(
            sensor.sensor_contact_type,
            dual=False,
            two_eol=sensor.sensor_eol_count == SensorEOLCount.DOUBLE,
        ).active
        logger.trace(
            "Detecting NORMAL alert for sensor %s: %.3f-%.3f<%.3f",
            sensor.name,
            current_value,
            reference_value_a,
            TOLERANCE_V3,
        )
        return is_close(current_value, reference_value_a, TOLERANCE_V3)

    if sensor.channel_type == ChannelTypes.CHANNEL_A:
        # channel A: compare actual value to CHANNEL_A reference
        reference_value_a = wiring_config.select_strategy(
            sensor.sensor_contact_type,
            dual=True,
            two_eol=False,
        ).channel_a_active
        logger.trace(
            "Detecting CHANNEL_A alert for sensor %s: %.3f-%.3f<%.3f",
            sensor.name,
            current_value,
            reference_value_a,
            TOLERANCE_V3,
        )
        reference_value_ab = wiring_config.select_strategy(
            sensor.sensor_contact_type,
            dual=True,
            two_eol=False,
        ).both_active
        logger.trace(
            "Detecting CHANNEL_A alert for sensor %s: %.3f-%.3f<%.3f",
            sensor.name,
            current_value,
            reference_value_ab,
            TOLERANCE_V3,
        )
        return is_close(current_value, reference_value_a, TOLERANCE_V3) or is_close(
            current_value, reference_value_ab, TOLERANCE_V3
        )

    if sensor.channel_type == ChannelTypes.CHANNEL_B:
        # channel B: compare actual value to CHANNEL_B reference
        reference_value_b = wiring_config.select_strategy(
            sensor.sensor_contact_type,
            dual=True,
            two_eol=False,
        ).channel_b_active
        logger.trace(
            "Detecting CHANNEL_B alert for sensor %s: %.3f-%.3f<%.3f",
            sensor.name,
            current_value,
            reference_value_b,
            TOLERANCE_V3,
        )
        reference_value_ab = wiring_config.select_strategy(
            sensor.sensor_contact_type,
            dual=True,
            two_eol=False,
        ).both_active
        logger.trace(
            "Detecting CHANNEL_B alert for sensor %s: %.3f-%.3f<%.3f",
            sensor.name,
            current_value,
            reference_value_ab,
            TOLERANCE_V3,
        )
        return is_close(current_value, reference_value_b, TOLERANCE_V3) or is_close(
            current_value, reference_value_ab, TOLERANCE_V3
        )

    raise ValueError(f"Unsupported channel type: {sensor.channel_type}")


def detect_error_v3(sensor: Sensor, current_value: float) -> bool:
    return is_close(current_value, CHANNEL_CUT, TOLERANCE_V3) or is_close(
        current_value, CHANNEL_SHORTAGE, TOLERANCE_V3
    )
