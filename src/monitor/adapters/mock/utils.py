"""
Manage the communication between the simulator and the mock adapters.
"""

import contextlib
import fcntl
import json
import os
from dataclasses import dataclass
from enum import Enum

from monitor.database import get_database_session
from monitor.output import OUTPUT_NAMES
from utils.models import ChannelTypes, Sensor, SensorContactTypes, SensorEOLCount

# buffer files between the simulator and the mock adapters
INPUT_FILE = os.environ.get("MOCK_INPUT_FILE", "simulator_input.json")
OUTPUT_FILE = os.environ.get("MOCK_OUTPUT_FILE", "simulator_output.json")
KEYPAD_FILE = os.environ.get("MOCK_KEYPAD_FILE", "simulator_keypad.json")

DEFAULT_KEYPAD = {"pending_bits": 0, "data": []}

DEFAULT_INPUT_DATA = {
    f"CH{str(i).zfill(2)}": 0 for i in range(1, int(os.environ.get("INPUT_NUMBER", 15)) + 1)
}
DEFAULT_INPUT_DATA["POWER"] = 0


class WiringStrategies(str, Enum):
    """
    Wiring strategies of the input channels
    """

    SINGLE_WITH_EOL = "single_with_eol"
    SINGLE_WITH_2EOL = "single_with_2eol"
    DUAL = "dual"
    CUT = "cut"
    SHORTAGE = "shortage"


@dataclass
class ChannelConfig:
    """Configuration for a single channel."""

    wiring_strategy: str
    contact_type: SensorContactTypes
    sensor_a_active: bool = False
    sensor_b_active: bool = False


def protected_read(filename, default_data):
    """
    Read data from a JSON file with file locking to avoid reading incomplete data
    or returning the default data.
    """
    with contextlib.suppress(FileNotFoundError, OSError):
        with open(filename, "r", encoding="utf-8") as file_handle:
            fcntl.flock(file_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                raw_data = json.load(file_handle)
            except json.JSONDecodeError:
                raw_data = default_data
            fcntl.flock(file_handle, fcntl.LOCK_UN)
            return raw_data
    return default_data


def protected_write(filename, data):
    """
    Write data to a JSON file with file locking to avoid conflicts.
    """
    with contextlib.suppress(FileNotFoundError, OSError):
        with open(filename, "w", encoding="utf-8") as file_handle:
            fcntl.flock(file_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            json.dump(data, file_handle)
            fcntl.flock(file_handle, fcntl.LOCK_UN)


def protected_transfer(filename, default_data):
    """
    Read the data from the input and clear it with default data.
    """
    with contextlib.suppress(FileNotFoundError, OSError):
        with open(filename, "r+", encoding="utf-8") as file_handle:
            fcntl.flock(file_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                raw_data = json.load(file_handle)
            except json.JSONDecodeError:
                raw_data = default_data

            # clear the file with default data
            file_handle.seek(0)
            file_handle.truncate()
            json.dump(default_data, file_handle)
            fcntl.flock(file_handle, fcntl.LOCK_UN)
            return raw_data

    return default_data


def protected_update(filename, data, default_data, merge_function):
    """
    Update the data in a JSON file with file locking to avoid conflicts.
    """
    # create the file if it does not exist
    if not os.path.exists(filename):
        protected_write(filename, default_data)

    with contextlib.suppress(FileNotFoundError, OSError):
        with open(filename, "r+", encoding="utf-8") as file_handle:
            fcntl.flock(file_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                raw_data = json.load(file_handle)
            except json.JSONDecodeError:
                raw_data = default_data

            # apply the merge function
            merged_data = merge_function(raw_data, data)

            # write the merged data back to the file
            file_handle.seek(0)
            file_handle.truncate()
            json.dump(merged_data, file_handle)
            fcntl.flock(file_handle, fcntl.LOCK_UN)


def get_input_state(input_name):
    """
    Get the numeric state of a specific input channel.
    """
    default_data = DEFAULT_INPUT_DATA.copy()
    data = protected_read(INPUT_FILE, default_data)
    return data.get(input_name, 0)


def set_input_state(input_name, state):
    """
    Set the numeric state of a specific input channel.
    """
    default_data = DEFAULT_INPUT_DATA.copy()
    data = protected_read(INPUT_FILE, default_data)
    data[input_name] = state
    protected_write(INPUT_FILE, data)


def set_input_states(channel_values):
    """
    Set the numeric state of all input channels.
    """
    data = {f"CH{str(i).zfill(2)}": value for i, value in enumerate(channel_values[:-1], start=1)}
    data["POWER"] = channel_values[-1]
    protected_write(INPUT_FILE, data)


def get_output_states() -> list[bool]:
    """
    Get the state of all output channels.
    """
    default_data = {name: 0 for name in OUTPUT_NAMES}
    return list(protected_read(OUTPUT_FILE, default_data).values())


def set_output_states(states):
    """
    Set the state of all output channels.
    """
    data = {name: state for name, state in zip(OUTPUT_NAMES.values(), states)}
    protected_write(OUTPUT_FILE, data)


def get_keypad_state():
    """
    Get the state of a specific keypad.
    """
    defaults = DEFAULT_KEYPAD.copy()
    return protected_transfer(KEYPAD_FILE, defaults)


def set_keypad_state(pending_bits, data):
    """
    Set the state of the keypad.
    """

    def merge_keypad_data(base, new):
        return {
            "pending_bits": base.get("pending_bits", 0) + new.get("pending_bits", 0),
            "data": base.get("data", []) + new.get("data", []),
        }

    new_data = {"pending_bits": pending_bits, "data": data}

    protected_update(KEYPAD_FILE, new_data, DEFAULT_KEYPAD, merge_keypad_data)


def load_channel_configs(input_number: int) -> dict:
    """
    Load channel configurations from the database.
    Returns a dict mapping channel names (CH01, CH02, ...) to ChannelConfig instances.
    """
    session = get_database_session()
    sensors = (
        session.query(Sensor)
        .filter(Sensor.channel.isnot(None), ~Sensor.deleted)
        .order_by(Sensor.channel)
        .all()
    )

    channel_configs = {
        f"CH{i:02d}": ChannelConfig(
            wiring_strategy=WiringStrategies.CUT.value,
            contact_type=SensorContactTypes.NC,
        )
        for i in range(1, input_number + 1)
    }

    # Update configs from DB
    for sensor in sensors:
        channel_name = f"CH{sensor.channel + 1:02d}"
        # Map DB fields to simulator config
        wiring_strategy = WiringStrategies.CUT.value
        if sensor.sensor_eol_count == SensorEOLCount.DOUBLE:
            wiring_strategy = WiringStrategies.SINGLE_WITH_2EOL.value
        elif (
            sensor.channel_type == ChannelTypes.BASIC or sensor.channel_type == ChannelTypes.NORMAL
        ):
            wiring_strategy = WiringStrategies.SINGLE_WITH_EOL.value
        elif (
            sensor.channel_type == ChannelTypes.CHANNEL_A
            or sensor.channel_type == ChannelTypes.CHANNEL_B
        ):
            wiring_strategy = WiringStrategies.DUAL.value

        channel_configs[channel_name] = ChannelConfig(
            wiring_strategy=wiring_strategy,
            contact_type=SensorContactTypes(sensor.sensor_contact_type),
        )

    return channel_configs
