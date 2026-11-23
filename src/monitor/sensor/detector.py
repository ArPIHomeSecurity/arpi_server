"""
Utility functions to detect alerts and errors based on sensor readings.

V3 sensor NORMAL detection:

| EOL count | Contact type | Contact state       | Detection |
|-----------|--------------|---------------------|-----------|
| Single    | NC           | Closed              | Normal    |
| Single    | NC           | Open                | Alert     |
| Single    | NC           | Wire cut            | Alert     |
| Single    | NC           | Shortcut            | Error     |
| Single    | NO           | Open                | Normal    |
| Single    | NO           | Closed              | Alert     |
| Single    | NO           | Shortcut            | Alert     |
| Single    | NO           | Wire cut            | Error     |
|-----------|--------------|---------------------|-----------|
| Double    | NC           | Closed              | Normal    |
| Double    | NC           | Open                | Alert     |
| Double    | NC           | Wire cut            | Tamper    |
| Double    | NC           | Shortcut            | Tamper    |
| Double    | NO           | Open                | Normal    |
| Double    | NO           | Closed              | Alert     |
| Double    | NO           | Wire cut            | Tamper    |
| Double    | NO           | Shortcut            | Tamper    |
|-----------|--------------|---------------------|-----------|


"""

import logging
from os import environ

from monitor.sensor.wirings import PullUpDownConfig
from utils.constants import LOG_SENSORS
from utils.models import ChannelTypes, Sensor, SensorEOLCount

TOLERANCE_V2 = 0.01
TOLERANCE_V3 = 0.05

CHANNEL_CUT = 1.0
CHANNEL_SHORTAGE = 0.0

# pull-up resistor
R_PULL_UP = 2200
# pull-down resistor
R_PULL_DOWN = 22000

# EOL resistor for channel A
R_A = 5600
# EOL resistor for channel B
R_B = 3600

# Create a default configuration instance for calculating channel constants
# wiring_config = PullUpConfig(R_PULL_UP, R_A, R_B)
wiring_config = PullUpDownConfig(R_PULL_UP, R_PULL_DOWN, R_A, R_B)

BOARD_VERSION = int(environ.get("BOARD_VERSION", "1"))

logger = logging.getLogger(LOG_SENSORS)


class ChannelError:
    SHORTCUT = "shortcut"
    OPEN_CIRCUIT = "open_circuit"


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
    """
    Detect error condition based on sensor configuration and current value.
    Only BOARD_VERSION 3 supports error detection.
    """
    if BOARD_VERSION == 2:
        # BOARD_VERSION 2 does not support error detection
        return False
    elif BOARD_VERSION == 3:
        return detect_error_v3(sensor, current_value)
    else:
        raise ValueError(f"Unsupported BOARD_VERSION: {BOARD_VERSION}")


def detect_tamper(sensor: Sensor, current_value: float) -> bool:
    """Detect cut or shortcut tampering on double-EOL wired sensors."""
    if BOARD_VERSION != 3:
        return False

    if (
        sensor.channel_type == ChannelTypes.NORMAL
        and sensor.sensor_eol_count == SensorEOLCount.DOUBLE
    ):
        return is_close(current_value, wiring_config.shortcut, TOLERANCE_V3) or is_close(
            current_value, wiring_config.open_circuit, TOLERANCE_V3
        )

    return False


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
            TOLERANCE_V2,
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
    """
    Detect error condition for the sensor based on its channel type
    and EOL configuration for BOARD_VERSION 3.

    An error means that the sensor's current value is not close to any expected
    reference value (normal, alert, tamper).
    """
    # Basic channels are never considered in error state
    if sensor.channel_type == ChannelTypes.BASIC:
        return False

    acceptable_values = []
    shortcut = wiring_config.shortcut
    open_circuit = wiring_config.open_circuit

    # suppress error if the value is close to normal active value
    if sensor.channel_type == ChannelTypes.NORMAL:
        references = wiring_config.select_strategy(
            sensor.sensor_contact_type,
            dual=False,
            two_eol=sensor.sensor_eol_count == SensorEOLCount.DOUBLE,
        )

        acceptable_values = [references.active, references.default]

        if sensor.sensor_eol_count == SensorEOLCount.DOUBLE:
            acceptable_values.extend([wiring_config.shortcut, wiring_config.open_circuit])

        logger.trace(
            "Detecting error for sensor %s(%s): default=%.3f active=%.3f shortcut=%.3f open=%.3f",
            sensor.name,
            sensor.id,
            references.default,
            references.active,
            shortcut,
            open_circuit,
        )
    # suppress error if the value is close to any of the dual channel active values
    elif sensor.channel_type in (ChannelTypes.CHANNEL_A, ChannelTypes.CHANNEL_B):
        references = wiring_config.select_strategy(
            sensor.sensor_contact_type,
            dual=True,
            two_eol=False,
        )

        acceptable_values = [
            references.default,
            references.channel_a_active,
            references.channel_b_active,
            references.both_active,
        ]

        logger.trace(
            "Detecting error for sensor %s(%s): default=%.3f active A=%.3f active B=%.3f both active=%.3f shortcut=%.3f open=%.3f",
            sensor.name,
            sensor.id,
            references.default,
            references.channel_a_active,
            references.channel_b_active,
            references.both_active,
            shortcut,
            open_circuit,
        )
    else:
        raise ValueError(f"Unsupported channel type: {sensor.channel_type}")

    return not any(is_close(current_value, value, TOLERANCE_V3) for value in acceptable_values)
