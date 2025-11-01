"""
Manage the communication between the simulator and the mock adapters.
"""

import contextlib
import fcntl
import json
import os

from monitor.output import OUTPUT_NAMES

# buffer files between the simulator and the mock adapters
INPUT_FILE = "simulator_input.json"
OUTPUT_FILE = "simulator_output.json"
KEYPAD_FILE = "simulator_keypad.json"

DEFAULT_KEYPAD = {"pending_bits": 0, "data": []}


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
    Get the state of a specific input channel.
    """
    default_data = {f"CH{str(i).zfill(2)}": {"value": 0, "type": "cut"} for i in range(int(os.environ.get("INPUT_NUMBER", 0)))}
    default_data["POWER"] = 0
    data = protected_read(INPUT_FILE, default_data)
    if input_name == "POWER":
        return data.get(input_name)
    else:
        channel_data = data.get(input_name, {"value": 0, "type": "cut"})
        return channel_data.get("value", 0) if isinstance(channel_data, dict) else channel_data


def set_input_states(channel_values, channel_configs):
    """
    Set the state of all input channels with their complete configurations.
    """
    data = {}
    for i, (value, config) in enumerate(zip(channel_values[:-1], channel_configs), start=1):
        ch_key = f"CH{str(i).zfill(2)}"
        if isinstance(config, dict):
            data[ch_key] = {
                "value": value,
                "wiring_strategy": config.get("wiring_strategy", "cut"),
                "contact_type": config.get("contact_type", "nc"),
                "sensor_a_active": config.get("sensor_a_active", False),
                "sensor_b_active": config.get("sensor_b_active", False)
            }
        else:
            # Handle legacy format where config is just a string type
            data[ch_key] = {
                "value": value,
                "wiring_strategy": "cut" if config in ["cut", "shortage"] else "single_with_eol",
                "contact_type": "nc",
                "sensor_a_active": False,
                "sensor_b_active": False
            }
    data["POWER"] = channel_values[-1]
    protected_write(INPUT_FILE, data)


def get_channel_configs():
    """
    Get the complete configuration of all channels.
    """
    default_data = {f"CH{str(i).zfill(2)}": {"value": 0, "wiring_strategy": "cut", "contact_type": "nc", "sensor_a_active": False, "sensor_b_active": False} for i in range(1, int(os.environ.get("INPUT_NUMBER", 15)) + 1)}
    default_data["POWER"] = 0
    data = protected_read(INPUT_FILE, default_data)
    configs = {}
    for ch_key in [f"CH{str(i).zfill(2)}" for i in range(1, int(os.environ.get("INPUT_NUMBER", 15)) + 1)]:
        channel_data = data.get(ch_key, {"value": 0, "wiring_strategy": "cut", "contact_type": "nc", "sensor_a_active": False, "sensor_b_active": False})
        if isinstance(channel_data, dict):
            configs[ch_key] = {
                "wiring_strategy": channel_data.get("wiring_strategy", "cut"),
                "contact_type": channel_data.get("contact_type", "nc"),
                "sensor_a_active": channel_data.get("sensor_a_active", False),
                "sensor_b_active": channel_data.get("sensor_b_active", False)
            }
        else:
            # Handle old format - default to "cut"
            configs[ch_key] = {
                "wiring_strategy": "cut",
                "contact_type": "nc",
                "sensor_a_active": False,
                "sensor_b_active": False
            }
    return configs


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
    data = {
        name: state for name, state in zip(OUTPUT_NAMES.values(), states)
    }
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
            "data": base.get("data", []) + new.get("data", [])
        }

    new_data = {
        "pending_bits": pending_bits,
        "data": data
    }

    protected_update(KEYPAD_FILE, new_data, DEFAULT_KEYPAD, merge_keypad_data)
