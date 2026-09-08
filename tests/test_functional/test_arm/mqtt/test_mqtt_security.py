"""
Protections of the MQTT arm/disarm command path.

The command payload carries the access code of the user, which makes the command topic
an authentication interface reachable over the network.
"""

import json
import logging
from time import sleep

import paho.mqtt.client as mqtt
import pytest
from dotenv import load_dotenv

from monitor.communication.mqtt import MQTTClient
from tests.test_functional.data import create_test_no_delay_v2
from tests.test_functional.helpers import call_api, check_api_response, wait_for_monitoring_ready

load_dotenv(".env.pytest")

logger = logging.getLogger(__name__)

BROKER_HOST = "localhost"
BROKER_PORT = 2883

SYSTEM_COMMAND_TOPIC = "arpi/alarm_control_panel/system/state/set"

# see tests/data.py: admin id=1
ADMIN_CODE = "1234"


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
    finally:
        client.loop_stop()
        client.disconnect()


@pytest.fixture(scope="module", autouse=True)
def monitoring_ready(device_token):
    """
    Wait for the monitor to finish its startup before the first test.

    The autouse cleanup_database_fixture resets all sequences after every test, including
    the one of the option table, which it does not clear. A monitor still writing its
    configuration at that moment crashes on a duplicate option id, so no test may start
    while the monitor is coming up.
    """
    wait_for_monitoring_ready(device_token)


class _FakeMessage:
    def __init__(self, topic, payload, qos, retain):
        self.topic = topic
        self.payload = payload
        self.qos = qos
        self.retain = retain


class _FakeClient:
    """Records what the MQTT client publishes back to the broker."""

    def __init__(self):
        self.published = []

    def publish(self, topic, payload, qos=0, retain=False):
        self.published.append((topic, payload, retain))


@pytest.mark.parametrize("database_data", [create_test_no_delay_v2], indirect=True)
def test_01_retained_command_is_ignored_and_cleared():
    """
    A retained command is redelivered on every reconnect, so a retained disarm with a
    valid code would disarm the system again after every restart. It must be dropped and
    the topic must be cleared, otherwise it comes back with the next subscription.

    The broker only sets the retain flag when it delivers a message because of a new
    subscription, so this is exercised directly on the callback.
    """
    commands = []
    client = MQTTClient(on_arm_command=lambda *args: commands.append(args))
    fake_client = _FakeClient()

    payload = json.dumps({"action": "DISARM", "code": ADMIN_CODE}).encode()
    client._on_message(
        fake_client, None, _FakeMessage(SYSTEM_COMMAND_TOPIC, payload, qos=1, retain=True)
    )

    assert commands == [], "a retained command must not be executed"
    assert fake_client.published == [(SYSTEM_COMMAND_TOPIC, b"", True)], (
        "the retained message must be cleared on the broker"
    )


@pytest.mark.parametrize("database_data", [create_test_no_delay_v2], indirect=True)
def test_02_live_command_is_still_executed():
    """
    Guard for the retain check above: a normal command must keep working.
    """
    commands = []
    client = MQTTClient(on_arm_command=lambda *args: commands.append(args))
    fake_client = _FakeClient()

    payload = json.dumps({"action": "DISARM", "code": ADMIN_CODE}).encode()
    client._on_message(
        fake_client, None, _FakeMessage(SYSTEM_COMMAND_TOPIC, payload, qos=1, retain=False)
    )

    assert len(commands) == 1
    assert fake_client.published == []


@pytest.mark.parametrize("database_data", [create_test_no_delay_v2], indirect=True)
def test_03_cleared_retained_command_is_not_an_error():
    """
    Clearing a retained command publishes an empty message, which is delivered back to
    our own subscription. It must be dropped quietly instead of being reported as an
    invalid command.
    """
    commands = []
    client = MQTTClient(on_arm_command=lambda *args: commands.append(args))
    fake_client = _FakeClient()

    client._on_message(
        fake_client, None, _FakeMessage(SYSTEM_COMMAND_TOPIC, b"", qos=1, retain=False)
    )

    assert commands == []
    assert fake_client.published == []


@pytest.mark.parametrize("database_data", [create_test_no_delay_v2], indirect=True)
def test_04_lockout_after_repeated_invalid_codes(user_token):
    """
    Access codes are numeric and at least 4 digits long, so the command topic must not
    accept an unlimited number of guesses. After the configured number of wrong codes
    even a valid code is ignored.

    This test runs in its own module because the lockout lives in the AreaHandler, which
    is created once per module by the monitor fixture.
    """
    for attempt in range(5):
        send_command(SYSTEM_COMMAND_TOPIC, "ARM_AWAY", f"999{attempt}")

    # give the monitor a chance to process the rejected commands
    sleep(1)

    send_command(SYSTEM_COMMAND_TOPIC, "ARM_AWAY", ADMIN_CODE)
    sleep(1)

    response = call_api("GET", "/api/monitoring/arm", {}, user_token)
    check_api_response(response)
    assert response.json()["type"] == "disarm", (
        "a valid code must be ignored while the command path is locked out"
    )

    response = call_api("GET", "/api/arms/count", {}, user_token)
    check_api_response(response)
    assert response.json() == 0
