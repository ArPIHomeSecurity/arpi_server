"""
Manage the communication between the simulator and the mock adapters.
"""

import contextlib
import fcntl
import json
import os
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from functools import cache
from random import randint

from sqlalchemy import select

from monitor.database import create_database_session
from monitor.output import OUTPUT_NAMES
from monitor.sensor.detector import wiring_config
from utils.models import ChannelTypes, Sensor, SensorContactTypes, SensorEOLCount

# buffer files between the simulator and the mock adapters
SIMULATOR_INPUT_FILE = os.environ.get("SIMULATOR_INPUT_FILE", "simulator_input.json")
SIMULATOR_OUTPUT_FILE = os.environ.get("SIMULATOR_OUTPUT_FILE", "simulator_output.json")
SIMULATOR_KEYPAD_FILE = os.environ.get("SIMULATOR_KEYPAD_FILE", "simulator_keypad.json")
SIMULATOR_GSM_FILE = os.environ.get("SIMULATOR_GSM_FILE", "simulator_gsm.json")
SIMULATOR_ZIGBEE_FILE = os.environ.get("SIMULATOR_ZIGBEE_FILE", "simulator_zigbee.json")

DEFAULT_KEYPAD = {"pending_bits": 0, "data": []}
DEFAULT_ZIGBEE_DATA = {"devices": {}}

DEFAULT_INPUT_DATA = {
    f"CH{str(i).zfill(2)}": 0 for i in range(1, int(os.environ.get("INPUT_NUMBER", "15")) + 1)
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


def calculate_channel_value(config: ChannelConfig) -> float:
    """Calculate a mock channel reading from its wiring and contact state."""
    if config.wiring_strategy == WiringStrategies.CUT.value:
        return wiring_config.open_circuit
    if config.wiring_strategy == WiringStrategies.SHORTAGE.value:
        return wiring_config.shortcut

    dual = config.wiring_strategy == WiringStrategies.DUAL.value
    two_eol = config.wiring_strategy == WiringStrategies.SINGLE_WITH_2EOL.value
    if not dual and not two_eol and config.wiring_strategy != WiringStrategies.SINGLE_WITH_EOL.value:
        raise ValueError(f"Unknown wiring strategy: {config.wiring_strategy}")

    strategy = wiring_config.select_strategy(config.contact_type, dual=dual, two_eol=two_eol)
    if dual:
        if config.sensor_a_active and config.sensor_b_active:
            return strategy.both_active
        if config.sensor_a_active:
            return strategy.channel_a_active
        if config.sensor_b_active:
            return strategy.channel_b_active
        return strategy.default

    return strategy.active if config.sensor_a_active else strategy.default


def protected_read(filename, default_data):
    """
    Read data from a JSON file with file locking to avoid reading incomplete data
    or returning the default data.
    """
    with (
        contextlib.suppress(FileNotFoundError, OSError),
        open(filename, "r", encoding="utf-8") as file_handle,
    ):
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
    with (
        contextlib.suppress(FileNotFoundError, OSError),
        open(filename, "w", encoding="utf-8") as file_handle,
    ):
        fcntl.flock(file_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        json.dump(data, file_handle)
        fcntl.flock(file_handle, fcntl.LOCK_UN)


def protected_transfer(filename, default_data):
    """
    Read the data from the input and clear it with default data.
    """
    with (
        contextlib.suppress(FileNotFoundError, OSError),
        open(filename, "r+", encoding="utf-8") as file_handle,
    ):
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

    with (
        contextlib.suppress(FileNotFoundError, OSError),
        open(filename, "r+", encoding="utf-8") as file_handle,
    ):
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
    data = protected_read(SIMULATOR_INPUT_FILE, default_data)
    return data.get(input_name, 0)


def set_input_state(input_name, state):
    """
    Set the numeric state of a specific input channel.
    """
    default_data = DEFAULT_INPUT_DATA.copy()
    data = protected_read(SIMULATOR_INPUT_FILE, default_data)
    data[input_name] = state
    protected_write(SIMULATOR_INPUT_FILE, data)


def set_input_states(channel_values):
    """
    Set the numeric state of all input channels.
    """
    data = {f"CH{str(i).zfill(2)}": value for i, value in enumerate(channel_values[:-1], start=1)}
    data["POWER"] = channel_values[-1]
    protected_write(SIMULATOR_INPUT_FILE, data)


def get_output_states() -> list[bool]:
    """
    Get the state of all output channels.
    """
    default_data = {name: 0 for name in OUTPUT_NAMES}
    return list(protected_read(SIMULATOR_OUTPUT_FILE, default_data).values())


def set_output_states(states):
    """
    Set the state of all output channels.
    """
    data = {name: state for name, state in zip(OUTPUT_NAMES.values(), states)}
    protected_write(SIMULATOR_OUTPUT_FILE, data)


def get_keypad_state():
    """
    Get the state of a specific keypad.
    """
    defaults = DEFAULT_KEYPAD.copy()
    return protected_transfer(SIMULATOR_KEYPAD_FILE, defaults)


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

    protected_update(SIMULATOR_KEYPAD_FILE, new_data, DEFAULT_KEYPAD, merge_keypad_data)


@cache
def load_zigbee_device_states() -> dict:
    """Build inactive Zigbee simulator states from database sensor mappings."""
    data = deepcopy(DEFAULT_ZIGBEE_DATA)
    with create_database_session() as session:
        sensors = session.scalars(select(Sensor).where(Sensor.zigbee_device_id.isnot(None))).all()
        for sensor in sensors:
            device = sensor.zigbee_device
            simulated_device = data["devices"].setdefault(
                device.ieee_address,
                {
                    "name": device.name,
                    "entities": deepcopy((device.device_metadata or {}).get("entities", [])),
                },
            )
            for entity in simulated_device["entities"]:
                if entity.get("platform") == "binary_sensor":
                    entity.setdefault("value", False)
                    entity.setdefault("attributes", {})
    return data


def get_zigbee_devices():
    """Get structured simulator state."""
    return protected_read(SIMULATOR_ZIGBEE_FILE, deepcopy(load_zigbee_device_states()))


def set_zigbee_devices(data):
    """Replace the entire Zigbee simulator state payload."""
    protected_write(SIMULATOR_ZIGBEE_FILE, data)


def reset_zigbee_devices():
    """Discard simulator state and reload database defaults on the next read."""
    load_zigbee_device_states.cache_clear()
    with contextlib.suppress(FileNotFoundError):
        os.unlink(SIMULATOR_ZIGBEE_FILE)


def set_zigbee_entity_value(ieee_address: str, entity_id: str, value: bool):
    """Set a simulated Zigbee entity value."""
    default_data = get_zigbee_devices()

    def merge_entity(base, new):
        if not isinstance(base, dict):
            base = deepcopy(default_data)

        devices = base.setdefault("devices", {})
        device = devices.setdefault(new["ieee_address"], {})
        entity = next(
            (
                entity
                for entity in device.get("entities", [])
                if entity.get("entityId") == new["entity_id"]
            ),
            None,
        )
        if entity is None:
            raise ValueError(
                f"Unknown Zigbee entity {new['entity_id']} on device {new['ieee_address']}"
            )
        entity["value"] = bool(new["value"])
        device["last_seen"] = datetime.now().astimezone().isoformat()
        return base

    protected_update(
        SIMULATOR_ZIGBEE_FILE,
        {"ieee_address": str(ieee_address), "entity_id": str(entity_id), "value": bool(value)},
        default_data,
        merge_entity,
    )


def set_zigbee_entity_attribute(
    ieee_address: str, entity_id: str, attribute: str, value: bool
):
    """Set an extra state attribute for a simulated entity."""
    default_data = get_zigbee_devices()

    def merge_attribute(base, new):
        if not isinstance(base, dict):
            base = deepcopy(default_data)

        device = base.setdefault("devices", {}).setdefault(new["ieee_address"], {})
        entity = next(
            (
                entity
                for entity in device.get("entities", [])
                if entity.get("entityId") == new["entity_id"]
            ),
            None,
        )
        if entity is None:
            raise ValueError(
                f"Unknown Zigbee entity {new['entity_id']} on device {new['ieee_address']}"
            )
        entity.setdefault("attributes", {})[new["attribute"]] = bool(new["value"])
        device["last_seen"] = datetime.now().astimezone().isoformat()
        return base

    protected_update(
        SIMULATOR_ZIGBEE_FILE,
        {
            "ieee_address": str(ieee_address),
            "entity_id": str(entity_id),
            "attribute": str(attribute),
            "value": bool(value),
        },
        default_data,
        merge_attribute,
    )


def get_sms_messages():
    """
    Get the list of SMS messages from the mock GSM adapter.
    """
    default_data = []
    return protected_transfer(SIMULATOR_GSM_FILE, default_data)


def append_sms_message(number, text, time):
    """
    Append a new SMS message to the mock GSM adapter's message list.
    """
    default_data = []

    def merge_sms_data(base, new):
        return base + [{"index": randint(1_000_000, 10_000_000), **new}]

    new_message = {"number": number, "text": text, "time": time.isoformat()}
    protected_update(
        SIMULATOR_GSM_FILE,
        new_message,
        default_data,
        merge_sms_data,
    )


def load_channel_configs(input_number: int) -> dict:
    """
    Load channel configurations from the database.
    Returns a dict mapping channel names (CH01, CH02, ...) to ChannelConfig instances.
    """
    with create_database_session() as session:
        sensors = session.scalars(
            select(Sensor)
            .where(Sensor.channel.isnot(None), ~Sensor.deleted)
            .order_by(Sensor.channel)
        ).all()

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
                sensor.channel_type == ChannelTypes.BASIC
                or sensor.channel_type == ChannelTypes.NORMAL
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


def initialize_input_states(input_number: int, power_state: int = 1) -> None:
    """Initialize mock channels from database wiring with inactive contacts."""
    channel_configs = load_channel_configs(input_number)
    channel_values = [
        calculate_channel_value(channel_configs[f"CH{i:02d}"])
        for i in range(1, input_number + 1)
    ]
    set_input_states([*channel_values, power_state])
