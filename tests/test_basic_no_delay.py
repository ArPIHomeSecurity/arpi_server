import logging

from dotenv import load_dotenv
import pytest

from monitor.adapters.mock.utils import set_input_state
from monitor.sensor.detector import wiring_config
from tests.data import create_test_no_delay_v2
from utils.models import SensorContactTypes
from helpers import (
    MonitorEvent,
    call_api,
    check_api_response,
    MonitorEventsClient,
    wait_for_monitoring_ready,
)


load_dotenv(".env.pytest")

logger = logging.getLogger(__name__)


@pytest.mark.parametrize("database_data", [create_test_no_delay_v2], indirect=True)
def test_arm_away(device_token, user_token):
    # connect to monitor websocket first to catch events
    monitor_events = MonitorEventsClient(device_token)
    try:
        wait_for_monitoring_ready(device_token)

        response = call_api("PUT", "/api/monitoring/arm?type=arm_away", {}, user_token)
        check_api_response(response)

        # wait for area changed to armed away
        monitor_events.wait_for_event(
            MonitorEvent(
                name="area_state_change",
                payload={"id": 1, "name": "House", "armState": "arm_away", "uiOrder": None},
                diffOptions={"exclude_paths": ["root['id']", "root['uiOrder']"]},
            ),
            timeout=1,
        )

        # get monitoring arm status
        response = call_api("GET", "/api/monitoring/arm", {}, user_token)
        check_api_response(response)

        # disarm the system
        response = call_api("PUT", "/api/monitoring/disarm", {}, user_token)
        check_api_response(response)

        # wait for area changed to disarmed
        monitor_events.wait_for_event(
            MonitorEvent(
                name="area_state_change",
                payload={"id": 1, "name": "House", "armState": "disarm", "uiOrder": None},
                diffOptions={"exclude_paths": ["root['id']", "root['uiOrder']"]},
            ),
            timeout=0.5,
        )

        # get monitoring arm status
        response = call_api("GET", "/api/monitoring/arm", {}, user_token)
        check_api_response(response)

        assert response.status_code == 200

    finally:
        monitor_events.disconnect()


@pytest.mark.parametrize("database_data", [create_test_no_delay_v2], indirect=True)
def test_arm_stay(device_token, user_token):
    """
    Test arming the system in stay mode.
    In stay mode, the system should be armed but the sensors should not trigger an alert.
    """
    monitor_events = MonitorEventsClient(device_token)

    try:
        # wait for monitoring to be ready
        wait_for_monitoring_ready(device_token)

        # call rest api to arm stay
        response = call_api("PUT", "/api/monitoring/arm?type=arm_stay", {}, user_token)
        check_api_response(response)

        # wait for area changed to armed stay
        monitor_events.wait_for_event(
            MonitorEvent(
                name="area_state_change",
                payload={"id": 1, "name": "House", "armState": "arm_stay", "uiOrder": None},
                diffOptions={"exclude_paths": ["root['id']", "root['uiOrder']"]},
            ),
            timeout=1,
        )

        # disarm the system
        response = call_api("PUT", "/api/monitoring/disarm", {}, user_token)
        check_api_response(response)

        # wait for area changed to disarmed
        monitor_events.wait_for_event(
            MonitorEvent(
                name="area_state_change",
                payload={"id": 1, "name": "House", "armState": "disarm", "uiOrder": None},
                diffOptions={"exclude_paths": ["root['id']", "root['uiOrder']"]},
            ),
            timeout=0.5,
        )

    finally:
        monitor_events.disconnect()


@pytest.mark.parametrize("database_data", [create_test_no_delay_v2], indirect=True)
def test_alert(device_token, user_token):
    monitor_events = MonitorEventsClient(device_token)

    try:
        # wait for monitoring to be ready
        wait_for_monitoring_ready(device_token)

        # call rest api to arm away
        response = call_api("PUT", "/api/monitoring/arm?type=arm_away", {}, user_token)
        check_api_response(response)

        # set channel to activate
        set_input_state("CH01", wiring_config.select_strategy(SensorContactTypes.NC).active)

        # wait for alert event (alert delay is 3 seconds in test config, so wait for 4 seconds)
        monitor_events.wait_for_event(
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
                            "name": "Test room",
                            "description": "Test room movement sensor",
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
                        "root['sensors'][0]['startTime']",
                    ],
                },
            ),
            delay=0,
            timeout=0.5,
        )

        # disarm the system
        response = call_api("PUT", "/api/monitoring/disarm", {}, user_token)
        check_api_response(response)

    finally:
        monitor_events.disconnect()
