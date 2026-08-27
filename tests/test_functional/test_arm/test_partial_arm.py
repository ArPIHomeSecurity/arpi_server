"""
Arm state of a system where only a part of the areas is armed.
"""

import logging

import pytest
from tests.test_functional.data import create_test_two_areas_v2
from dotenv import load_dotenv
from tests.test_functional.helpers import (
    MonitorEvent,
    MonitorEventsClient,
    call_api,
    check_api_response,
    wait_for_monitoring_ready,
)

load_dotenv(".env.pytest")

logger = logging.getLogger(__name__)


def get_area_ids(user_token) -> dict:
    response = call_api("GET", "/api/areas/", {}, user_token)
    check_api_response(response)
    return {area["name"]: area["id"] for area in response.json()}


@pytest.mark.parametrize("database_data", [create_test_two_areas_v2], indirect=True)
def test_01_arm_state_with_one_area_armed(device_token, user_token):
    """
    Arming only the second area must report the arm state of that area, not the
    disarmed state of the first one. The arm state is derived from the areas with a
    DISTINCT query, so it must not depend on the row order of the database.
    """
    monitor_events = MonitorEventsClient(device_token)

    try:
        wait_for_monitoring_ready(device_token)
        monitor_events.clear_events()

        areas = get_area_ids(user_token)
        response = call_api(
            "PUT", f"/api/area/arm?area_id={areas['Garage']}&type=arm_away", {}, user_token
        )
        check_api_response(response)

        monitor_events.wait_for_event(
            MonitorEvent(
                name="area_state_change",
                payload={"id": areas["Garage"], "name": "Garage", "armState": "arm_away"},
                diffOptions={"exclude_paths": ["root['uiOrder']"]},
            ),
            timeout=2.0,
        )

        for _ in range(10):
            response = call_api("GET", "/api/monitoring/arm", {}, user_token)
            check_api_response(response)
            assert response.json()["type"] == "arm_away"

        response = call_api("PUT", f"/api/area/disarm?area_id={areas['Garage']}", {}, user_token)
        check_api_response(response)

        # the disarm is processed asynchronously by the monitor, wait for it to finish
        # before the test ends and the fixture clears the arm log
        monitor_events.wait_for_event(
            MonitorEvent(name="arm_state_change", payload="disarm"), timeout=2.0
        )

    finally:
        monitor_events.disconnect()


@pytest.mark.parametrize("database_data", [create_test_two_areas_v2], indirect=True)
def test_02_arm_state_with_areas_armed_differently(device_token, user_token):
    """
    Areas armed with different types report a mixed arm state.
    """
    monitor_events = MonitorEventsClient(device_token)

    try:
        wait_for_monitoring_ready(device_token)
        monitor_events.clear_events()

        areas = get_area_ids(user_token)
        response = call_api(
            "PUT", f"/api/area/arm?area_id={areas['House']}&type=arm_away", {}, user_token
        )
        check_api_response(response)
        response = call_api(
            "PUT", f"/api/area/arm?area_id={areas['Garage']}&type=arm_stay", {}, user_token
        )
        check_api_response(response)

        monitor_events.wait_for_event(
            MonitorEvent(
                name="area_state_change",
                payload={"id": areas["Garage"], "name": "Garage", "armState": "arm_stay"},
                diffOptions={"exclude_paths": ["root['uiOrder']"]},
            ),
            timeout=2.0,
        )

        response = call_api("GET", "/api/monitoring/arm", {}, user_token)
        check_api_response(response)
        assert response.json()["type"] == "arm_mixed"

        response = call_api("PUT", "/api/monitoring/disarm", {}, user_token)
        check_api_response(response)

        # see test_01: wait for the monitor to finish the disarm
        monitor_events.wait_for_event(
            MonitorEvent(name="arm_state_change", payload="disarm"), timeout=2.0
        )

    finally:
        monitor_events.disconnect()
