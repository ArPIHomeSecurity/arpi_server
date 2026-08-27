"""
Arm/disarm the system over MQTT, as Home Assistant does it.
"""

import json
import logging
from time import sleep

import paho.mqtt.client as mqtt
import pytest
from dotenv import load_dotenv

from tests.test_functional.data import create_test_no_delay_v2
from tests.test_functional.helpers import (
    MonitorEvent,
    MonitorEventsClient,
    call_api,
    check_api_response,
    wait_for_monitoring_ready,
)

load_dotenv(".env.pytest")

logger = logging.getLogger(__name__)

BROKER_HOST = "localhost"
BROKER_PORT = 2883

SYSTEM_COMMAND_TOPIC = "arpi/alarm_control_panel/system/state/set"
AREA_COMMAND_TOPIC = "arpi/alarm_control_panel/house_1/state/set"

# see tests/data.py: admin id=1 / user id=2
ADMIN_CODE = "1234"
USER_CODE = "1111"


def send_command(topic: str, action: str, code: str):
    """
    Publish an arm/disarm command like the Home Assistant MQTT alarm control panel does.
    """
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="test_home_assistant")
    client.connect(BROKER_HOST, BROKER_PORT, keepalive=10)
    client.loop_start()
    try:
        message = client.publish(topic, json.dumps({"action": action, "code": code}), qos=1)
        message.wait_for_publish(timeout=5)
        logger.debug("Published MQTT command %s to %s", action, topic)
    finally:
        client.loop_stop()
        client.disconnect()


def armed_events(arm_state: str):
    return [
        MonitorEvent(
            name="area_state_change",
            payload={"id": 1, "name": "House", "armState": arm_state, "uiOrder": None},
            diffOptions={"exclude_paths": ["root['id']", "root['uiOrder']"]},
        ),
        MonitorEvent(
            name="system_state_change",
            payload="monitoring_armed",
        ),
        MonitorEvent(
            name="arm_state_change",
            payload=arm_state,
        ),
    ]


def disarmed_events():
    return [
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
    ]


@pytest.mark.parametrize("database_data", [create_test_no_delay_v2], indirect=True)
def test_01_arm_away_and_disarm_the_system(device_token, user_token):
    """
    Arm and disarm the whole system over the system alarm control panel.
    The access codes of two different users are used to verify that the arm log
    records who armed and who disarmed the system.
    """
    monitor_events = MonitorEventsClient(device_token)

    try:
        wait_for_monitoring_ready(device_token)
        monitor_events.clear_events()

        send_command(SYSTEM_COMMAND_TOPIC, "ARM_AWAY", ADMIN_CODE)
        monitor_events.wait_for_events(armed_events("arm_away"), timeout=2.0)

        monitor_events.clear_events()

        send_command(SYSTEM_COMMAND_TOPIC, "DISARM", USER_CODE)
        monitor_events.wait_for_events(disarmed_events(), timeout=2.0)

        response = call_api("GET", "/api/arms", {}, user_token)
        check_api_response(response)

        events = response.json()
        assert len(events) == 1
        assert events[0]["arm"]["type"] == "arm_away"
        assert events[0]["arm"]["userId"] == 1
        assert events[0]["disarm"]["userId"] == 2

    finally:
        monitor_events.disconnect()


@pytest.mark.parametrize("database_data", [create_test_no_delay_v2], indirect=True)
def test_02_arm_stay_a_single_area(device_token, user_token):
    """
    Arm and disarm a single area over its own alarm control panel.
    """
    monitor_events = MonitorEventsClient(device_token)

    try:
        wait_for_monitoring_ready(device_token)
        monitor_events.clear_events()

        send_command(AREA_COMMAND_TOPIC, "ARM_HOME", ADMIN_CODE)
        monitor_events.wait_for_events(armed_events("arm_stay"), timeout=2.0)

        monitor_events.clear_events()

        send_command(AREA_COMMAND_TOPIC, "DISARM", ADMIN_CODE)
        monitor_events.wait_for_events(disarmed_events(), timeout=2.0)

    finally:
        monitor_events.disconnect()


@pytest.mark.parametrize("database_data", [create_test_no_delay_v2], indirect=True)
def test_03_reject_command_with_invalid_code(device_token, user_token):
    """
    A command without a valid access code must not change the arm state.
    """
    wait_for_monitoring_ready(device_token)

    send_command(SYSTEM_COMMAND_TOPIC, "ARM_AWAY", "9999")

    # give the monitor a chance to (incorrectly) process the command
    sleep(1)

    response = call_api("GET", "/api/monitoring/arm", {}, user_token)
    check_api_response(response)
    assert response.json()["type"] == "disarm"

    response = call_api("GET", "/api/arms/count", {}, user_token)
    check_api_response(response)
    assert response.json() == 0


@pytest.mark.parametrize("database_data", [create_test_no_delay_v2], indirect=True)
def test_04_arm_without_configured_delay(device_token, user_token):
    """
    Commands from Home Assistant are armed with exit delay, but this configuration
    has no delay. Arming must go straight to armed without the arm delay state.
    """
    monitor_events = MonitorEventsClient(device_token)

    try:
        wait_for_monitoring_ready(device_token)
        monitor_events.clear_events()

        send_command(SYSTEM_COMMAND_TOPIC, "ARM_AWAY", ADMIN_CODE)
        monitor_events.wait_for_events(armed_events("arm_away"), timeout=2.0)

        monitor_events.assert_not_received(
            MonitorEvent(name="system_state_change", payload="monitoring_arm_delay")
        )

        send_command(SYSTEM_COMMAND_TOPIC, "DISARM", ADMIN_CODE)
        monitor_events.wait_for_events(disarmed_events(), timeout=2.0)

    finally:
        monitor_events.disconnect()
