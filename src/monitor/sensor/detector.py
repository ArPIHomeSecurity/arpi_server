"""
Utility functions to detect alerts and errors based on sensor readings.
"""

from os import environ

from models import ChannelTypes, Sensor, SensorEOLCount
from monitor.sensor.wirings import PullUpConfig

TOLERANCE_V2 = 0.01
TOLERANCE_V3 = 0.025

CHANNEL_CUT = 1.0
CHANNEL_SHORTAGE = 0.0

# pull-up resistor
R_PULL_UP = 2000

# EOL resistor for channel A
R_A = 5600
# EOL resistor for channel B
R_B = 3000

# Create a default configuration instance for calculating channel constants
wiring_config = PullUpConfig(R_PULL_UP, R_A, R_B)

BOARD_VERSION = int(environ.get("BOARD_VERSION", 1))


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
        # compare actual value to reference value
        return not is_close(current_value, sensor.reference_value, TOLERANCE_V3)

    if sensor.channel_type == ChannelTypes.NORMAL:
        return is_close(
            current_value,
            wiring_config.select_strategy(
                sensor.sensor_contact_type,
                dual=False,
                two_eol=sensor.sensor_eol_count == SensorEOLCount.DOUBLE,
            ).active,
            TOLERANCE_V3,
        )

    if sensor.channel_type == ChannelTypes.CHANNEL_A:
        # channel A: compare actual value to CHANNEL_A reference
        return is_close(
            current_value,
            wiring_config.select_strategy(sensor.sensor_contact_type, dual=True).channel_a_active,
            TOLERANCE_V3,
        ) or is_close(
            current_value,
            wiring_config.select_strategy(sensor.sensor_contact_type, dual=True).both_active,
            TOLERANCE_V3,
        )

    if sensor.channel_type == ChannelTypes.CHANNEL_B:
        # channel B: compare actual value to CHANNEL_B reference
        return is_close(
            current_value,
            wiring_config.select_strategy(sensor.sensor_contact_type, dual=True).channel_b_active,
            TOLERANCE_V3,
        ) or is_close(
            current_value,
            wiring_config.select_strategy(sensor.sensor_contact_type, dual=True).both_active,
            TOLERANCE_V3,
        )

    raise ValueError(f"Unsupported channel type: {sensor.channel_type}")


def detect_error_v3(sensor: Sensor, current_value: float) -> bool:
    return is_close(current_value, CHANNEL_CUT, TOLERANCE_V3) or is_close(
        current_value, CHANNEL_SHORTAGE, TOLERANCE_V3
    )
