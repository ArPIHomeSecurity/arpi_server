"""
MQTT panel states when only a part of the areas is armed or disarmed while the exit
delay is running.

The delay timer hands the publishing over to the monitoring thread when it expires, so
changes made during the delay (an area disarmed, an area joining the arm) must show up
in the published states, and a replaced timer must not end the new exit delay early.
"""

import json
import logging
from time import sleep

import paho.mqtt.client as mqtt
import pytest
from data import create_test_two_areas_with_delay_v2
from dotenv import load_dotenv
from helpers import (
    MqttStateRecorder,
    call_api,
    check_api_response,
    wait_for_monitoring_ready,
)

load_dotenv(".env.pytest")

logger = logging.getLogger(__name__)

BROKER_HOST = "localhost"
BROKER_PORT = 2883

PANEL_TOPIC_PREFIX = "arpi/alarm_control_panel/"
SYSTEM_STATE_TOPIC = f"{PANEL_TOPIC_PREFIX}system/state"
HOUSE_STATE_TOPIC = f"{PANEL_TOPIC_PREFIX}house_1/state"
GARAGE_STATE_TOPIC = f"{PANEL_TOPIC_PREFIX}garage_2/state"

SYSTEM_COMMAND_TOPIC = f"{PANEL_TOPIC_PREFIX}system/state/set"
HOUSE_COMMAND_TOPIC = f"{PANEL_TOPIC_PREFIX}house_1/state/set"
GARAGE_COMMAND_TOPIC = f"{PANEL_TOPIC_PREFIX}garage_2/state/set"

# see tests/data.py: admin id=1
ADMIN_CODE = "1234"

# arm delay of the zones in create_test_two_areas_with_delay_v2, see create_zones()
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
        logger.debug("Published MQTT command %s to %s", action, topic)
    finally:
        client.loop_stop()
        client.disconnect()


def get_area_ids(user_token) -> dict:
    response = call_api("GET", "/api/areas/", {}, user_token)
    check_api_response(response)
    return {area["name"]: area["id"] for area in response.json()}


@pytest.mark.parametrize("database_data", [create_test_two_areas_with_delay_v2], indirect=True)
def test_01_area_disarmed_during_the_exit_delay(device_token, user_token):
    """
    Disarming a single area during the exit delay must survive the delay: the expiring
    timer publishes the current states, not the ones collected when the arm started.
    """
    wait_for_monitoring_ready(device_token)
    areas = get_area_ids(user_token)

    with (
        MqttStateRecorder(SYSTEM_STATE_TOPIC) as system,
        MqttStateRecorder(HOUSE_STATE_TOPIC) as house,
        MqttStateRecorder(GARAGE_STATE_TOPIC) as garage,
    ):
        send_command(SYSTEM_COMMAND_TOPIC, "ARM_AWAY", ADMIN_CODE)
        garage.wait_for("arming", timeout=2.0)

        response = call_api("PUT", f"/api/area/disarm?area_id={areas['Garage']}", {}, user_token)
        check_api_response(response)
        disarmed_index = garage.wait_for("disarmed", timeout=3.0)

        # the house is armed when the delay expires...
        house.wait_for("armed_away", timeout=ARM_DELAY + 2.0)
        # ...but the garage stays disarmed
        assert "armed_away" not in garage.payloads[disarmed_index + 1 :], garage.payloads

        send_command(SYSTEM_COMMAND_TOPIC, "DISARM", ADMIN_CODE)
        system.wait_for("disarmed", timeout=2.0)


@pytest.mark.parametrize("database_data", [create_test_two_areas_with_delay_v2], indirect=True)
def test_02_area_joins_the_running_exit_delay(device_token):
    """
    Arming a second area of the same type during the exit delay joins the running
    delay: its panel shows arming and becomes armed only when the delay expires.
    """
    wait_for_monitoring_ready(device_token)

    with (
        MqttStateRecorder(SYSTEM_STATE_TOPIC) as system,
        MqttStateRecorder(GARAGE_STATE_TOPIC) as garage,
    ):
        send_command(HOUSE_COMMAND_TOPIC, "ARM_AWAY", ADMIN_CODE)
        system.wait_for("arming", timeout=2.0)

        send_command(GARAGE_COMMAND_TOPIC, "ARM_AWAY", ADMIN_CODE)
        arming_index = garage.wait_for("arming", timeout=2.0)
        # the panel joins the exit delay, it must not report armed right away
        assert "armed_away" not in garage.payloads[:arming_index], garage.payloads

        garage.wait_for("armed_away", after_index=arming_index + 1, timeout=ARM_DELAY + 2.0)

        send_command(SYSTEM_COMMAND_TOPIC, "DISARM", ADMIN_CODE)
        system.wait_for("disarmed", timeout=2.0)


@pytest.mark.parametrize("database_data", [create_test_two_areas_with_delay_v2], indirect=True)
def test_03_new_arm_type_restarts_the_exit_delay(device_token):
    """
    Arming a second area with a different type restarts the exit delay. The expiry of
    the replaced timer must not end the new exit delay early.
    """
    wait_for_monitoring_ready(device_token)

    with MqttStateRecorder(SYSTEM_STATE_TOPIC) as system:
        send_command(HOUSE_COMMAND_TOPIC, "ARM_AWAY", ADMIN_CODE)
        system.wait_for("arming", timeout=2.0)

        # let half of the delay pass before the second arm restarts it
        sleep(ARM_DELAY / 2)
        send_command(GARAGE_COMMAND_TOPIC, "ARM_HOME", ADMIN_CODE)

        # the timer of the first arm fires in this window, it must not arm the system
        sleep(ARM_DELAY / 2 + 0.8)
        armed = [payload for payload in system.payloads if payload.startswith("armed")]
        assert not armed, system.payloads

        # the delay of the second arm expires, the mixed state is reported armed_away
        armed_index = system.wait_for("armed_away", timeout=ARM_DELAY + 2.0)

        send_command(SYSTEM_COMMAND_TOPIC, "DISARM", ADMIN_CODE)
        system.wait_for("disarmed", after_index=armed_index + 1, timeout=2.0)
