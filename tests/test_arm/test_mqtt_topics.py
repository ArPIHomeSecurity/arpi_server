"""
MQTT topics published for the Home Assistant integration when area names collide.

sanitize() is not injective, so two areas can end up on the same topics, and an area
can even collide with the panel controlling the whole system. Colliding areas must not
be published at all, otherwise their configs and states overwrite each other.
"""

import json
import logging

import pytest
from data import create_test_colliding_areas_v2
from dotenv import load_dotenv
from helpers import (
    MqttStateRecorder,
    call_api,
    check_api_response,
    collect_retained_messages,
    wait_for_monitoring_ready,
)

load_dotenv(".env.pytest")

logger = logging.getLogger(__name__)

BROKER_HOST = "localhost"
BROKER_PORT = 2883

PANEL_TOPIC_PREFIX = "arpi/alarm_control_panel/"
SYSTEM_STATE_TOPIC = f"{PANEL_TOPIC_PREFIX}system/state"


def get_area_ids(user_token) -> dict:
    response = call_api("GET", "/api/areas/", {}, user_token)
    check_api_response(response)
    return {area["name"]: area["id"] for area in response.json()}


@pytest.mark.parametrize("database_data", [create_test_colliding_areas_v2], indirect=True)
def test_01_colliding_areas_are_not_published(device_token):
    """
    Areas colliding on a topic must not publish config or state, the area without a
    collision must be published normally.
    """
    wait_for_monitoring_ready(device_token)

    panels = collect_retained_messages(
        f"{PANEL_TOPIC_PREFIX}#", host=BROKER_HOST, port=BROKER_PORT
    )

    # "A B" and "A.B" both sanitize to "a_b"
    assert f"{PANEL_TOPIC_PREFIX}a_b/config" not in panels, "colliding config was published"
    assert f"{PANEL_TOPIC_PREFIX}a_b/state" not in panels, "colliding state was published"

    # the area named "System" must not take over the system panel
    config = json.loads(panels[f"{PANEL_TOPIC_PREFIX}system/config"])
    assert config["unique_id"] == "system"
    assert panels[SYSTEM_STATE_TOPIC] == b"disarmed"

    # the area without a collision is published normally
    assert f"{PANEL_TOPIC_PREFIX}backyard/config" in panels
    assert panels[f"{PANEL_TOPIC_PREFIX}backyard/state"] == b"disarmed"


@pytest.mark.parametrize("database_data", [create_test_colliding_areas_v2], indirect=True)
def test_02_arming_the_colliding_area_keeps_the_system_panel_intact(device_token, user_token):
    """
    Arming the area named "System" must not leak its own state onto the state topic of
    the system panel. Backyard is armed away first, so arming the colliding area as stay
    results in a mixed arm state (reported as armed_away) - armed_home showing up on the
    system panel can only come from the state of the colliding area itself.
    """
    wait_for_monitoring_ready(device_token)
    areas = get_area_ids(user_token)

    with MqttStateRecorder(SYSTEM_STATE_TOPIC, host=BROKER_HOST, port=BROKER_PORT) as recorder:
        response = call_api(
            "PUT", f"/api/area/arm?area_id={areas['Backyard']}&type=arm_away", {}, user_token
        )
        check_api_response(response)
        away_index = recorder.wait_for("armed_away", timeout=2.0)

        response = call_api(
            "PUT", f"/api/area/arm?area_id={areas['System']}&type=arm_stay", {}, user_token
        )
        check_api_response(response)

        # mixed arm state, reported as armed_away again
        recorder.wait_for("armed_away", after_index=away_index + 1, timeout=2.0)
        assert "armed_home" not in recorder.payloads, (
            "the arm state of the colliding area leaked onto the system panel"
        )

        response = call_api("PUT", "/api/monitoring/disarm", {}, user_token)
        check_api_response(response)
        recorder.wait_for("disarmed", timeout=2.0)
