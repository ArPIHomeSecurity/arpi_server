"""
Manage the communication between the simulator and the mock adapters.
"""

import contextlib
import json
import fcntl
from os import environ

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

def protected_update(filename, data, default_data, merge_function):
    """
    Update the data in a JSON file with file locking to avoid conflicts.
    """
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
    default_data = {f"CH{str(i).zfill(2)}": 0 for i in range(int(environ.get("INPUT_NUMBER", 0)))}
    default_data["POWER"] = 0
    return protected_read(INPUT_FILE, default_data).get(input_name)


def set_input_states(states):
    """
    Set the state of all input channels.
    """
    data = {f"CH{str(i).zfill(2)}": state for i, state in enumerate(states[:-1], start=1)}
    data["POWER"] = states[-1]
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
