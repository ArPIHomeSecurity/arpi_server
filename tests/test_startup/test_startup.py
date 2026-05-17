import os

from sqlalchemy import select

import pytest
from data import create_test_no_delay_v2, create_test_no_delay_v2_armed
from helpers import (
    MonitorEvent,
    MonitorEventsClient,
    call_api,
    check_api_response,
    wait_for_monitoring_ready,
    wait_for_monitoring_state,
)

from monitor.adapters.mock.utils import set_input_state, set_input_states
from monitor.database import get_database_session
from monitor.sensor.detector import wiring_config
from utils.constants import MONITORING_ALERT, MONITORING_ARMED
from utils.models import Sensor, SensorContactTypes, ChannelTypes


@pytest.mark.parametrize("monitoring_state", [["monitoring_stopped", "network"]], indirect=True)
@pytest.mark.parametrize("database_data", [create_test_no_delay_v2], indirect=True)
def test_monitoring_stopped(device_token: str, user_token: str):
    """
    Test starting after normal shutdown.
    """
    # connect to monitor websocket first to catch events
    monitor_events = MonitorEventsClient(device_token)

    try:
        # wait for the monitor to emit the expected event
        wait_for_monitoring_ready(device_token)
    finally:
        monitor_events.disconnect()


@pytest.mark.parametrize("monitoring_state", [["monitoring_startup", "network"]], indirect=True)
@pytest.mark.parametrize("database_data", [create_test_no_delay_v2], indirect=True)
def test_monitoring_startup(device_token: str, user_token: str):
    """
    Test starting after crashed in startup phase.
    """
    # connect to monitor websocket first to catch events
    monitor_events = MonitorEventsClient(device_token)

    try:
        # wait for the monitor to emit the expected event
        wait_for_monitoring_ready(device_token)
    finally:
        monitor_events.disconnect()


@pytest.mark.parametrize(
    "monitoring_state", [["monitoring_invalid_config", "network"]], indirect=True
)
@pytest.mark.parametrize("database_data", [create_test_no_delay_v2], indirect=True)
def test_monitoring_invalid_config(device_token: str, user_token: str):
    """
    Test starting after crashed in invalid config phase.
    """
    # connect to monitor websocket first to catch events
    monitor_events = MonitorEventsClient(device_token)

    try:
        # wait for the monitor to emit the expected event
        wait_for_monitoring_ready(device_token)
    finally:
        monitor_events.disconnect()


@pytest.mark.parametrize(
    "monitoring_state", [["monitoring_updating_config", "network"]], indirect=True
)
@pytest.mark.parametrize("database_data", [create_test_no_delay_v2], indirect=True)
def test_monitoring_updating_config(device_token: str, user_token: str):
    """
    Test starting after crashed in updating config phase.
    """
    # connect to monitor websocket first to catch events
    monitor_events = MonitorEventsClient(device_token)

    try:
        # wait for the monitor to emit the expected event
        wait_for_monitoring_ready(device_token)
    finally:
        monitor_events.disconnect()


@pytest.mark.parametrize("monitoring_state", [["monitoring_armed", "network"]], indirect=True)
@pytest.mark.parametrize("database_data", [create_test_no_delay_v2_armed], indirect=True)
def test_monitoring_armed(device_token: str, user_token: str):
    """
    Test starting after crashed in armed phase.
    We need a state of database with armed area(s) for this test,
    otherwise the monitor will restore the ready state instead of armed.
    """
    # connect to monitor websocket first to catch events
    monitor_events = MonitorEventsClient(device_token)

    channel_values = [0.0] * int(os.environ["INPUT_NUMBER"])
    sensors = get_database_session().scalars(select(Sensor)).all()
    for sensor in sensors:
        channel_values[sensor.channel] = wiring_config.select_strategy(
            sensor.sensor_contact_type,
            sensor.channel_type in (ChannelTypes.CHANNEL_A, ChannelTypes.CHANNEL_B),
            sensor.sensor_eol_count,
        ).default
    set_input_states(channel_values)

    try:
        # wait for the monitor to emit the expected event
        wait_for_monitoring_state(MONITORING_ARMED, device_token)

        # activate sensor to check if the monitor is really armed
        set_input_state("CH01", wiring_config.select_strategy(SensorContactTypes.NC).active)

        # wait for the monitor to emit the expected event
        wait_for_monitoring_state(MONITORING_ALERT, device_token)

        # wait for alert event
        monitor_events.wait_for_events(
            [
                MonitorEvent(
                    name="alert_state_change",
                    payload={
                        "id": 1,
                        "alertType": "alert_away",
                        "startTime": "2026-05-02 19:09:40",
                        "endTime": None,
                        "silent": True,
                        "sensors": [
                            {
                                "sensorId": 1,
                                "channel": 0,
                                "typeId": 1,
                                "name": "Room 1",
                                "description": "Test room 1 movement sensor",
                                "startTime": "2026-05-02 21:09:30",
                                "endTime": None,
                                "delay": 0,
                                "silent": True,
                                "monitorPeriod": None,
                                "monitorThreshold": 100,
                            }
                        ],
                    },
                    diffOptions={
                        "ignore_order": True,
                        "exclude_paths": [
                            "root['id']",
                            "root['startTime']",
                            "root['sensors'][0]['sensorId']",
                            "root['sensors'][0]['startTime']",
                        ],
                    },
                ),
                MonitorEvent(
                    name="sensors_state_change",
                    payload=True,
                ),
                MonitorEvent(
                    name="syren_state_change",
                    payload=True,
                ),
            ],
            delay=0,
            timeout=1.0,
        )

        # disarm the system
        response = call_api("PUT", "/api/monitoring/disarm", {}, user_token)
        check_api_response(response)

        monitor_events.wait_for_events(
            [
                MonitorEvent(
                    name="area_state_change",
                    payload={"id": 1, "name": "House", "armState": "disarm", "uiOrder": None},
                    diffOptions={"exclude_paths": ["root['id']", "root['uiOrder']"]},
                ),
                MonitorEvent(
                    name="system_state_change",
                    payload="monitoring_ready",
                ),
                MonitorEvent(
                    name="arm_state_change",
                    payload="disarm",
                ),
            ],
            timeout=0.5,
        )

    finally:
        monitor_events.disconnect()
