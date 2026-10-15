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
from zigpy.zcl.clusters.security import ZoneStatus

from monitor.database import create_database_session
from monitor.output import OUTPUT_NAMES
from utils.models import ChannelTypes, Sensor, SensorContactTypes, SensorEOLCount
from utils.zigbee import (
    IAS_ZONE_STATUS_ATTRIBUTE,
    decode_zigbee_attribute,
)

# buffer files between the simulator and the mock adapters
INPUT_FILE = os.environ.get("MOCK_INPUT_FILE", "simulator_input.json")
OUTPUT_FILE = os.environ.get("MOCK_OUTPUT_FILE", "simulator_output.json")
KEYPAD_FILE = os.environ.get("MOCK_KEYPAD_FILE", "simulator_keypad.json")
GSM_FILE = os.environ.get("MOCK_GSM_FILE", "simulator_gsm.json")
ZIGBEE_FILE = os.environ.get("MOCK_ZIGBEE_FILE", "simulator_zigbee.json")

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
                    "available": True,
                    "signal_values": [],
                    "signal_metadata": (device.device_metadata or {}).get("signals", []),
                },
            )
            _set_signal_value(
                simulated_device,
                sensor.zigbee_endpoint,
                sensor.zigbee_cluster_id,
                sensor.zigbee_attribute_id,
                sensor.zigbee_field,
                False,
            )
    return data


def get_zigbee_devices():
    """Get structured simulator state."""
    return protected_read(ZIGBEE_FILE, deepcopy(load_zigbee_device_states()))


def set_zigbee_devices(data):
    """Replace the entire Zigbee simulator state payload."""
    protected_write(ZIGBEE_FILE, data)


def reset_zigbee_devices():
    """Discard simulator state and reload database defaults on the next read."""
    load_zigbee_device_states.cache_clear()
    with contextlib.suppress(FileNotFoundError):
        os.unlink(ZIGBEE_FILE)


def _signal_matches(signal, endpoint, cluster_id, attribute_id, field):
    return (
        str(signal.get("endpoint")) == str(endpoint)
        and int(signal.get("clusterId", -1)) == int(cluster_id)
        and int(signal.get("attributeId", -1)) == int(attribute_id)
        and signal.get("field") == field
    )


def _set_signal_value(device, endpoint, cluster_id, attribute_id, field, value):
    signal_values = device.setdefault("signal_values", [])
    for signal in signal_values:
        if _signal_matches(signal, endpoint, cluster_id, attribute_id, field):
            signal["value"] = value
            return
    signal_values.append(
        {
            "endpoint": str(endpoint),
            "clusterId": int(cluster_id),
            "attributeId": int(attribute_id),
            "field": field,
            "value": value,
        }
    )


def _get_signal_value(device, endpoint, cluster_id, attribute_id, field):
    for signal in device.get("signal_values", []):
        if _signal_matches(signal, endpoint, cluster_id, attribute_id, field):
            return signal.get("value")
    return None


def set_zigbee_signal(ieee_address, endpoint, cluster_id, attribute_id, field, value):
    """
    Update a normalized signal value for a simulated device.
    """
    default_data = get_zigbee_devices()

    def merge_signal(base, new):
        if not isinstance(base, dict):
            base = deepcopy(default_data)

        devices = base.setdefault("devices", {})
        device = devices.setdefault(new["ieee_address"], {})
        endpoint = new["endpoint"]
        statuses = device.get("ias_zone_status", {})
        is_ias_signal = (
            int(new["cluster_id"]) == int(IAS_ZONE_STATUS_ATTRIBUTE.cluster.cluster_id)
            and int(new["attribute_id"]) == IAS_ZONE_STATUS_ATTRIBUTE.attribute_id
            and new["field"] in ("alarm", "tamper")
        )
        if is_ias_signal and endpoint in statuses:
            flag = (
                ZoneStatus.Alarm_1 | ZoneStatus.Alarm_2
                if new["field"] == "alarm"
                else ZoneStatus.Tamper
            )
            status = int(statuses[endpoint]) & ~int(flag)
            if new["value"]:
                status |= int(ZoneStatus.Alarm_1 if new["field"] == "alarm" else flag)
            _update_ias_status(device, endpoint, status)
        else:
            _set_signal_value(
                device,
                endpoint,
                new["cluster_id"],
                new["attribute_id"],
                new["field"],
                new["value"],
            )
        device["last_seen"] = datetime.now().astimezone().isoformat()
        return base

    protected_update(
        ZIGBEE_FILE,
        {
            "ieee_address": str(ieee_address),
            "endpoint": str(endpoint),
            "cluster_id": int(cluster_id),
            "attribute_id": int(attribute_id),
            "field": field,
            "value": value,
        },
        default_data,
        merge_signal,
    )


def _update_ias_status(device, endpoint, status):
    device.setdefault("ias_zone_status", {})[endpoint] = int(status)
    decoded = decode_zigbee_attribute(IAS_ZONE_STATUS_ATTRIBUTE, status)
    for signal, value in decoded.signals:
        _set_signal_value(
            device,
            endpoint,
            IAS_ZONE_STATUS_ATTRIBUTE.cluster.cluster_id,
            IAS_ZONE_STATUS_ATTRIBUTE.attribute_id,
            signal.field,
            value,
        )
    device["last_seen"] = datetime.now().astimezone().isoformat()


def set_zigbee_zone_status(ieee_address, endpoint, status):
    default_data = get_zigbee_devices()

    def merge_status(base, new):
        device = base.setdefault("devices", {}).setdefault(new["ieee_address"], {})
        _update_ias_status(device, new["endpoint"], new["status"])
        return base

    protected_update(
        ZIGBEE_FILE,
        {"ieee_address": str(ieee_address), "endpoint": str(endpoint), "status": int(status)},
        default_data,
        merge_status,
    )


def set_zigbee_trouble(ieee_address, endpoint, enabled):
    default_data = get_zigbee_devices()

    def merge_trouble(base, new):
        device = base.setdefault("devices", {}).setdefault(new["ieee_address"], {})
        endpoint = new["endpoint"]
        alarm_cluster = IAS_ZONE_STATUS_ATTRIBUTE.cluster.cluster_id
        alarm_attribute = IAS_ZONE_STATUS_ATTRIBUTE.attribute_id
        status = device.get("ias_zone_status", {}).get(endpoint)
        if status is None:
            status = 0
            if _get_signal_value(device, endpoint, alarm_cluster, alarm_attribute, "alarm") is True:
                status |= int(ZoneStatus.Alarm_1)
            if (
                _get_signal_value(device, endpoint, alarm_cluster, alarm_attribute, "tamper")
                is True
            ):
                status |= int(ZoneStatus.Tamper)
        status = int(status) & ~int(ZoneStatus.Trouble)
        if new["enabled"]:
            status |= int(ZoneStatus.Trouble)
        _update_ias_status(device, endpoint, status)
        return base

    protected_update(
        ZIGBEE_FILE,
        {"ieee_address": str(ieee_address), "endpoint": str(endpoint), "enabled": bool(enabled)},
        default_data,
        merge_trouble,
    )


def get_sms_messages():
    """
    Get the list of SMS messages from the mock GSM adapter.
    """
    default_data = []
    return protected_transfer(GSM_FILE, default_data)


def append_sms_message(number, text, time):
    """
    Append a new SMS message to the mock GSM adapter's message list.
    """
    default_data = []

    def merge_sms_data(base, new):
        return base + [{"index": randint(1_000_000, 10_000_000), **new}]

    new_message = {"number": number, "text": text, "time": time.isoformat()}
    protected_update(
        GSM_FILE,
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
