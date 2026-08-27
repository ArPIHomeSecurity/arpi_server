"""
MQTT state of the system panel while the exit delay is running.

Home Assistant shows the exit delay as "arming", so the panel state must go through
arming before it becomes armed, and a disarm during the delay must win against the
expiring delay timer.
"""

import json
import logging
from time import sleep

import paho.mqtt.client as mqtt
import pytest
from tests.test_functional.data import create_test_with_delay_v2
from dotenv import load_dotenv
from tests.test_functional.helpers import MqttStateRecorder, wait_for_monitoring_ready

load_dotenv(".env.pytest")

logger = logging.getLogger(__name__)

BROKER_HOST = "localhost"
BROKER_PORT = 2883

SYSTEM_COMMAND_TOPIC = "arpi/alarm_control_panel/system/state/set"
SYSTEM_STATE_TOPIC = "arpi/alarm_control_panel/system/state"

# see tests/data.py: admin id=1
ADMIN_CODE = "1234"

# arm delay of the zones in create_test_with_delay_v2, see tests/data.py create_zones()
ARM_DELAY = 3


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


@pytest.mark.parametrize("database_data", [create_test_with_delay_v2], indirect=True)
def test_01_exit_delay_is_published_as_arming(device_token):
    """
    Arming with a configured exit delay goes through the arming state and ends armed.
    """
    wait_for_monitoring_ready(device_token)

    with MqttStateRecorder(SYSTEM_STATE_TOPIC, host=BROKER_HOST, port=BROKER_PORT) as recorder:
        send_command(SYSTEM_COMMAND_TOPIC, "ARM_AWAY", ADMIN_CODE)

        arming_index = recorder.wait_for("arming", timeout=2.0)
        # armed only after the exit delay has expired
        recorder.wait_for("armed_away", after_index=arming_index + 1, timeout=ARM_DELAY + 2.0)
        assert recorder.payloads[-1] == "armed_away", recorder.payloads

        send_command(SYSTEM_COMMAND_TOPIC, "DISARM", ADMIN_CODE)
        recorder.wait_for("disarmed", after_index=arming_index + 1, timeout=2.0)


@pytest.mark.parametrize("database_data", [create_test_with_delay_v2], indirect=True)
def test_02_disarm_during_the_exit_delay(device_token):
    """
    A disarm during the exit delay must win: the cancelled delay timer must not
    publish the armed state afterwards.
    """
    wait_for_monitoring_ready(device_token)

    with MqttStateRecorder(SYSTEM_STATE_TOPIC, host=BROKER_HOST, port=BROKER_PORT) as recorder:
        send_command(SYSTEM_COMMAND_TOPIC, "ARM_AWAY", ADMIN_CODE)
        arming_index = recorder.wait_for("arming", timeout=2.0)

        send_command(SYSTEM_COMMAND_TOPIC, "DISARM", ADMIN_CODE)
        disarmed_index = recorder.wait_for("disarmed", after_index=arming_index + 1, timeout=2.0)

        # wait past the end of the original delay
        sleep(ARM_DELAY + 1)
        assert "armed_away" not in recorder.payloads[disarmed_index + 1 :], (
            "the cancelled delay timer armed the panel after the disarm"
        )
