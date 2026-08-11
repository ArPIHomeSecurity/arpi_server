"""
Cleanup of retained MQTT topics when an area loses its topic.

A renamed area would leave the retained config/state of its old topic on the broker,
and a rename can also make two areas collide on the same topic: home assistant would
show ghost panels that silently ignore every command, so the monitor deletes the
topics it no longer publishes.
"""

import logging
from time import sleep, time

import pytest
from data import create_test_two_areas_v2
from dotenv import load_dotenv
from helpers import (
    call_api,
    check_api_response,
    collect_retained_messages,
    wait_for_monitoring_ready,
)

load_dotenv(".env.pytest")

logger = logging.getLogger(__name__)

PANEL_TOPIC_PREFIX = "arpi/alarm_control_panel/"


def get_area_ids(user_token) -> dict:
    response = call_api("GET", "/api/areas/", {}, user_token)
    check_api_response(response)
    return {area["name"]: area["id"] for area in response.json()}


def panel_topics(name: str) -> list:
    return [f"{PANEL_TOPIC_PREFIX}{name}/config", f"{PANEL_TOPIC_PREFIX}{name}/state"]


def wait_for_retained_topics(present: list, absent: list, timeout=10.0):
    """
    Wait until the retained panel topics match the expectation: the config update is
    processed asynchronously by the monitor.
    """
    end = time() + timeout
    panels = {}
    while time() < end:
        panels = collect_retained_messages(f"{PANEL_TOPIC_PREFIX}#")
        if all(topic in panels for topic in present) and not any(
            topic in panels for topic in absent
        ):
            return

        sleep(0.5)

    raise AssertionError(
        f"Retained topics mismatch, expected {present} without {absent}, got {sorted(panels)}"
    )


@pytest.mark.parametrize("database_data", [create_test_two_areas_v2], indirect=True)
def test_01_renaming_an_area_moves_its_topics(device_token, user_token):
    """
    After a rename the panel is published under the new topic and the retained
    config/state of the old topic is removed from the broker.
    """
    wait_for_monitoring_ready(device_token)
    areas = get_area_ids(user_token)

    response = call_api("PUT", f"/api/area/{areas['Garage']}", {"name": "Carport"}, user_token)
    check_api_response(response)

    wait_for_retained_topics(
        present=panel_topics("carport") + panel_topics("house"),
        absent=panel_topics("garage"),
    )


@pytest.mark.parametrize("database_data", [create_test_two_areas_v2], indirect=True)
def test_02_collision_after_rename_removes_both_topics(device_token, user_token):
    """
    Renaming an area onto the topic of another one makes both unavailable over MQTT,
    including the already retained topics of the area that was published before.
    """
    wait_for_monitoring_ready(device_token)

    # test_01 may have renamed an area already, work with whatever names exist
    areas = get_area_ids(user_token)
    first_name, second_name = sorted(areas)

    # the lower case name is a different area name, but sanitizes to the same topic
    response = call_api(
        "PUT", f"/api/area/{areas[first_name]}", {"name": second_name.lower()}, user_token
    )
    check_api_response(response)

    wait_for_retained_topics(
        present=[f"{PANEL_TOPIC_PREFIX}system/config"],
        absent=panel_topics(second_name.lower()) + panel_topics(first_name.lower()),
    )
