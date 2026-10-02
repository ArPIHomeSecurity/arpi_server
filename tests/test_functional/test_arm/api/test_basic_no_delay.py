import logging

import pytest
from dotenv import load_dotenv

from monitor.adapters.mock.utils import set_input_state, set_zigbee_capability
from monitor.sensor.detector import wiring_config
from tests.test_functional.data import create_test_no_delay_v2
from tests.test_functional.helpers import (
    MonitorEvent,
    MonitorEventsClient,
    call_api,
    check_api_response,
    wait_for_monitoring_ready,
)
from utils.models import SensorContactTypes

load_dotenv(".env.pytest")

logger = logging.getLogger(__name__)


@pytest.mark.parametrize("database_data", [create_test_no_delay_v2], indirect=True)
def test_01_arm_away(device_token, user_token):
    # connect to monitor websocket first to catch events
    monitor_events = MonitorEventsClient(device_token)
    try:
        wait_for_monitoring_ready(device_token)

        response = call_api("PUT", "/api/monitoring/arm?type=arm_away", {}, user_token)
        check_api_response(response)

        # wait for area changed to armed away
        monitor_events.wait_for_events(
            [
                MonitorEvent(
                    name="area_state_change",
                    payload={"id": 1, "name": "House", "armState": "arm_away", "uiOrder": None},
                    diffOptions={"exclude_paths": ["root['id']", "root['uiOrder']"]},
                ),
                MonitorEvent(
                    name="system_state_change",
                    payload="monitoring_armed",
                ),
                MonitorEvent(
                    name="arm_state_change",
                    payload="arm_away",
                ),
            ],
            timeout=0.5,
        )

        # get monitoring arm status
        response = call_api("GET", "/api/monitoring/arm", {}, user_token)
        check_api_response(response)

        monitor_events.wait_for_events(
            [
                MonitorEvent(
                    name="system_state_change",
                    payload="monitoring_armed",
                ),
                MonitorEvent(
                    name="arm_state_change",
                    payload="arm_away",
                ),
            ],
            timeout=0.5,
        )

        # disarm the system
        response = call_api("PUT", "/api/monitoring/disarm", {}, user_token)
        check_api_response(response)

        # wait for area changed to disarmed
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

        # get monitoring arm status
        response = call_api("GET", "/api/monitoring/arm", {}, user_token)
        check_api_response(response)

        assert response.status_code == 200

    finally:
        monitor_events.disconnect()


@pytest.mark.parametrize("database_data", [create_test_no_delay_v2], indirect=True)
def test_02_arm_stay(device_token, user_token):
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
        monitor_events.wait_for_events(
            [
                MonitorEvent(
                    name="area_state_change",
                    payload={"id": 1, "name": "House", "armState": "arm_stay", "uiOrder": None},
                    diffOptions={"exclude_paths": ["root['id']", "root['uiOrder']"]},
                ),
                MonitorEvent(
                    name="system_state_change",
                    payload="monitoring_armed",
                ),
                MonitorEvent(
                    name="arm_state_change",
                    payload="arm_stay",
                ),
            ],
            timeout=0.5,
        )

        # disarm the system
        response = call_api("PUT", "/api/monitoring/disarm", {}, user_token)
        check_api_response(response)

        # wait for area changed to disarmed
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


@pytest.mark.parametrize("database_data", [create_test_no_delay_v2], indirect=True)
def test_03_alert(device_token, user_token):
    monitor_events = MonitorEventsClient(device_token)

    try:
        # wait for monitoring to be ready
        wait_for_monitoring_ready(device_token)
        monitor_events.clear_events()

        # call rest api to arm away
        response = call_api("PUT", "/api/monitoring/arm?type=arm_away", {}, user_token)
        check_api_response(response)

        monitor_events.wait_for_events(
            [
                MonitorEvent(
                    name="area_state_change",
                    payload={"id": 1, "name": "House", "armState": "arm_away", "uiOrder": None},
                    diffOptions={"exclude_paths": ["root['id']", "root['uiOrder']"]},
                ),
                MonitorEvent(
                    name="system_state_change",
                    payload="monitoring_armed",
                ),
                MonitorEvent(
                    name="arm_state_change",
                    payload="arm_away",
                ),
            ],
            timeout=0.5,
        )

        # set channel to activate
        set_input_state("CH01", wiring_config.select_strategy(SensorContactTypes.NC).active)

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
                        "silent": False,
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
                                "silent": False,
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

        # check for alert in the event log
        response = call_api("GET", "/api/arms/count", {}, user_token)
        check_api_response(response)

        assert response.status_code == 200
        assert response.json() == 1

        response = call_api("GET", "/api/arms/count?has_alert=true", {}, user_token)
        check_api_response(response)

        assert response.status_code == 200
        assert response.json() == 1

        # get arm events
        response = call_api("GET", "/api/arms", {}, user_token)
        check_api_response(response)
        logger.debug(f"API response: {response.json()}")

        assert response.status_code == 200
        events = response.json()
        assert isinstance(events, list)
        assert len(events) == 1

        event = events[0]
        assert event["arm"]["type"] == "arm_away"
        assert event["arm"]["userId"] == 1
        assert event["disarm"]["userId"] == 1

        alert = event["alert"]
        assert alert["alertType"] == "alert_away"
        assert len(alert["sensors"]) == 1
        assert alert["sensors"][0]["channel"] == 0
        assert alert["sensors"][0]["typeId"] == 1
        assert alert["sensors"][0]["silent"] is False

        sensor_changes = event["sensorChanges"]
        assert len(sensor_changes) == 1
        sensors = sensor_changes[0]["sensors"]
        assert len(sensors) == 3
        assert {sensor["channel"] for sensor in sensors} == {0, 1, 2}
        assert {sensor["typeId"] for sensor in sensors} == {1, 2, 3}

    finally:
        monitor_events.disconnect()


@pytest.mark.parametrize("database_data", [create_test_no_delay_v2], indirect=True)
def test_04_zigbee_alert(device_token, user_token):
    monitor_events = MonitorEventsClient(device_token)
    ieee_address = "11:22:33:44:55:66:77:88"
    capability_key = "1/a:0500:0002"

    try:
        wait_for_monitoring_ready(device_token)
        monitor_events.clear_events()

        response = call_api("PUT", "/api/monitoring/arm?type=arm_away", {}, user_token)
        check_api_response(response)

        monitor_events.wait_for_events(
            [
                MonitorEvent(
                    name="area_state_change",
                    payload={"id": 1, "name": "House", "armState": "arm_away", "uiOrder": None},
                    diffOptions={"exclude_paths": ["root['id']", "root['uiOrder']"]},
                ),
                MonitorEvent(name="system_state_change", payload="monitoring_armed"),
                MonitorEvent(name="arm_state_change", payload="arm_away"),
            ],
            timeout=0.5,
        )

        set_zigbee_capability(ieee_address, capability_key, True)

        monitor_events.wait_for_events(
            [
                MonitorEvent(
                    name="alert_state_change",
                    payload={
                        "id": 1,
                        "alertType": "alert_away",
                        "startTime": "2026-05-02 19:09:40",
                        "endTime": None,
                        "silent": False,
                        "sensors": [
                            {
                                "sensorId": 4,
                                "channel": None,
                                "typeId": 3,
                                "name": "Zigbee Door",
                                "description": "Test Zigbee contact sensor",
                                "startTime": "2026-05-02 21:09:30",
                                "endTime": None,
                                "delay": 0,
                                "silent": False,
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
                MonitorEvent(name="sensors_state_change", payload=True),
                MonitorEvent(name="syren_state_change", payload=True),
            ],
            delay=0,
            timeout=1.0,
        )

        response = call_api("PUT", "/api/monitoring/disarm", {}, user_token)
        check_api_response(response)

        monitor_events.wait_for_events(
            [
                MonitorEvent(
                    name="area_state_change",
                    payload={"id": 1, "name": "House", "armState": "disarm", "uiOrder": None},
                    diffOptions={"exclude_paths": ["root['id']", "root['uiOrder']"]},
                ),
                MonitorEvent(name="system_state_change", payload="monitoring_ready"),
                MonitorEvent(name="arm_state_change", payload="disarm"),
            ],
            timeout=0.5,
        )

        for path in ("/api/arms/count", "/api/arms/count?has_alert=true"):
            response = call_api("GET", path, {}, user_token)
            check_api_response(response)
            assert response.status_code == 200
            assert response.json() == 1

        response = call_api("GET", "/api/arms", {}, user_token)
        check_api_response(response)
        assert response.status_code == 200
        events = response.json()
        assert isinstance(events, list)
        assert len(events) == 1

        event = events[0]
        assert event["arm"]["type"] == "arm_away"
        assert event["arm"]["userId"] == 1
        assert event["disarm"]["userId"] == 1

        alert = event["alert"]
        assert alert["alertType"] == "alert_away"
        assert alert["silent"] is False
        assert len(alert["sensors"]) == 1
        alert_sensor = alert["sensors"][0]
        assert alert_sensor["name"] == "Zigbee Door"
        assert alert_sensor["description"] == "Test Zigbee contact sensor"
        assert alert_sensor["channel"] is None
        assert alert_sensor["typeId"] == 3
        assert alert_sensor["silent"] is False
        assert alert_sensor["delay"] == 0

        sensor_changes = event["sensorChanges"]
        assert len(sensor_changes) == 1
        sensors = sensor_changes[0]["sensors"]
        assert len(sensors) == 4
        assert {sensor["channel"] for sensor in sensors} == {0, 1, 2, None}
        assert {sensor["typeId"] for sensor in sensors} == {1, 2, 3}
        zigbee_sensors = [sensor for sensor in sensors if sensor["channel"] is None]
        assert len(zigbee_sensors) == 1
        assert zigbee_sensors[0]["sensorId"] == alert_sensor["sensorId"]
        assert zigbee_sensors[0]["name"] == "Zigbee Door"
        assert zigbee_sensors[0]["typeId"] == 3

    finally:
        try:
            set_zigbee_capability(ieee_address, capability_key, False)
        finally:
            monitor_events.disconnect()
