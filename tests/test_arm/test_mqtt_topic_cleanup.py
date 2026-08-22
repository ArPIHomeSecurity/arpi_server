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

from monitor.communication.mqtt import AREA_TOPIC_PREFIX, SENSOR_TOPIC_PREFIX, MQTTClient

load_dotenv(".env.pytest")

logger = logging.getLogger(__name__)


def get_area_ids(user_token) -> dict:
    response = call_api("GET", "/api/areas/", {}, user_token)
    check_api_response(response)
    return {area["name"]: area["id"] for area in response.json()}


def panel_topics(name: str) -> list:
    return [f"{AREA_TOPIC_PREFIX}{name}/config", f"{AREA_TOPIC_PREFIX}{name}/state"]


def get_sensor_ids(user_token) -> dict:
    response = call_api("GET", "/api/sensors/", {}, user_token)
    check_api_response(response)
    return {sensor["name"]: sensor["id"] for sensor in response.json()}


def sensor_topics(name: str) -> list:
    return [f"{SENSOR_TOPIC_PREFIX}{name}/config", f"{SENSOR_TOPIC_PREFIX}{name}/state"]


def wait_for_retained_topics(prefix: str, present: list, absent: list, timeout=10.0):
    """
    Wait until the retained topics with the given prefix match the expectation: the config update is
    processed asynchronously by the monitor.
    """
    end = time() + timeout
    panels = {}
    while time() < end:
        panels = collect_retained_messages(f"{prefix}#")
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
        prefix=AREA_TOPIC_PREFIX,
        present=panel_topics("carport_2") + panel_topics("house_1"),
        absent=panel_topics("garage_2"),
    )


@pytest.mark.parametrize("database_data", [create_test_two_areas_v2], indirect=True)
def test_02_renaming_a_sensor_moves_its_topics(device_token, user_token):
    """
    After a rename the sensor is published under the new topic and the retained
    config/state of the old topic is removed from the broker.
    """
    wait_for_monitoring_ready(device_token)
    sensors = get_sensor_ids(user_token)

    response = call_api(
        "PUT", f"/api/sensor/{sensors['Room 1']}", {"name": "Renamed room 1"}, user_token
    )
    check_api_response(response)

    wait_for_retained_topics(
        prefix=SENSOR_TOPIC_PREFIX,
        present=sensor_topics("renamed_room_1_1"),
        absent=sensor_topics("room_1_1"),
    )


@pytest.mark.parametrize("database_data", [create_test_two_areas_v2], indirect=True)
def test_03_remove_orphan_area_on_startup(device_token, user_token):
    """
    If the monitor finds a retained topic that is not used by any area, it removes it.
    """
    # publish an area which is not in the database
    client = MQTTClient()
    client.connect()
    client.publish_area_config(area_id=999, name="orphan_area")
    client.publish_area_state(area_id=999, name="orphan_area", state="disarm")
    client.close()

    wait_for_monitoring_ready(device_token)

    wait_for_retained_topics(
        prefix=AREA_TOPIC_PREFIX, present=[], absent=panel_topics("orphan_area_999")
    )


@pytest.mark.parametrize("database_data", [create_test_two_areas_v2], indirect=True)
def test_04_remove_orphan_sensor_on_startup(device_token, user_token):
    """
    If the monitor finds a retained topic that is not used by any sensor, it removes it.
    """
    # publish a sensor which is not in the database
    client = MQTTClient()
    client.connect()
    client.publish_sensor_config(sensor_id=999, name="orphan_sensor", type="Motion")
    client.publish_sensor_state(sensor_id=999, name="orphan_sensor", state=False)
    client.close()

    wait_for_monitoring_ready(device_token)

    wait_for_retained_topics(
        prefix=SENSOR_TOPIC_PREFIX, present=[], absent=sensor_topics("orphan_sensor_999")
    )
