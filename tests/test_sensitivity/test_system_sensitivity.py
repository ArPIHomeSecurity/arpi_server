import logging
import time

import pytest
from data import create_test_no_delay_v2
from dotenv import load_dotenv
from helpers import (
    MonitorEvent,
    MonitorEventsClient,
    call_api,
    check_api_response,
    wait_for_monitoring_ready,
)

from monitor.adapters.mock.utils import set_input_state
from monitor.sensor.detector import wiring_config
from utils.models import SensorContactTypes

load_dotenv(".env.pytest")

logger = logging.getLogger(__name__)


TEST_CASES = [
    pytest.param(
        {
            "system": {"monitor_period": 3, "monitor_threshold": 50},
            "sensor": {"monitorPeriod": None, "monitorThreshold": None},
            "sensor_activation_steps": [("active", 0.6), ("default", 1.0)],
            "expect_alert": False,
            "sensor_expected_monitor_period": 3,
            "sensor_expected_monitor_threshold": 50,
            "trigger_timeout": 3.0,
        },
        id="system_only_sensitivity",
    ),
    pytest.param(
        {
            "system": {"monitor_period": 3, "monitor_threshold": 50},
            "sensor": {"monitorPeriod": None, "monitorThreshold": 100},
            "sensor_activation_steps": [("active", 0.3), ("default", 0.1)],
            "expect_alert": True,
            "sensor_expected_monitor_period": None,
            "sensor_expected_monitor_threshold": 100,
            "trigger_timeout": 1.0,
        },
        id="sensor_instant_overrides_system",
    ),
    pytest.param(
        {
            "system": {"monitor_period": 3, "monitor_threshold": 50},
            "sensor": {"monitorPeriod": 10, "monitorThreshold": 80},
            "sensor_activation_steps": [("active", 5.0), ("default", 6.0)],
            "expect_alert": False,
            "sensor_expected_monitor_period": 10,
            "sensor_expected_monitor_threshold": 80,
            "trigger_timeout": 4.0,
        },
        id="sensor_longer_overrides_system",
    ),
    pytest.param(
        {
            "system": {"monitor_period": 10, "monitor_threshold": 50},
            "sensor": {"monitorPeriod": 3, "monitorThreshold": 80},
            "sensor_activation_steps": [("active", 1.0), ("default", 2.0)],
            "expect_alert": False,
            "sensor_expected_monitor_period": 10,
            "sensor_expected_monitor_threshold": 80,
            "trigger_timeout": 4.0,
        },
        id="sensor_shorter_overrides_system",
    ),
    pytest.param(
        {
            "system": {"monitor_period": 3, "monitor_threshold": 50},
            "sensor": {"monitorPeriod": None, "monitorThreshold": None},
            "sensor_activation_steps": [
                ("active", 1.0),
                ("default", 1.0),
                ("active", 1.0),
                ("default", 0.1),
            ],
            "expect_alert": True,
            "sensor_expected_monitor_period": 3,
            "sensor_expected_monitor_threshold": 50,
            "trigger_timeout": 4.0,
        },
        id="sensor_multiple_activation_steps",
    ),
]


@pytest.mark.parametrize("database_data", [create_test_no_delay_v2], indirect=True)
@pytest.mark.parametrize("case", TEST_CASES)
def test_01_sensitivity_cases(device_token, user_token, case):
    monitor_events = MonitorEventsClient(device_token)

    try:
        wait_for_monitoring_ready(device_token)

        # Set the system sensitivity
        response = call_api(
            "PUT",
            "/api/config/alert/sensitivity",
            case["system"],
            user_token,
        )
        check_api_response(response)

        # Verify that the system sensitivity was set correctly
        response = call_api("GET", "/api/config/alert/sensitivity", {}, user_token)
        check_api_response(response)
        assert response.json()["value"] == case["system"]

        # Set the sensor sensitivity
        response = call_api(
            "PUT",
            "/api/sensor/1",
            case["sensor"],
            user_token,
        )
        check_api_response(response)

        # Verify that the sensor sensitivity was set correctly
        response = call_api("GET", "/api/sensor/1", {}, user_token)
        check_api_response(response)
        sensor = response.json()
        assert sensor["monitorPeriod"] == case["sensor"]["monitorPeriod"]
        assert sensor["monitorThreshold"] == case["sensor"]["monitorThreshold"]

        wait_for_monitoring_ready(device_token)
        monitor_events.clear_events()

        response = call_api("PUT", "/api/monitoring/arm?type=arm_away", {}, user_token)
        check_api_response(response)

        # Wait for the system and the area to be armed before proceeding with the test steps
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
            timeout=5.0,
        )

        monitor_events.clear_events()
        strategy = wiring_config.select_strategy(SensorContactTypes.NC)

        for state_name, delay in case["sensor_activation_steps"]:
            set_input_state("CH01", getattr(strategy, state_name))
            time.sleep(delay)

        if case["expect_alert"]:
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
                                    "monitorPeriod": case["sensor_expected_monitor_period"],
                                    "monitorThreshold": case["sensor_expected_monitor_threshold"],
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
                timeout=case["trigger_timeout"],
            )
        else:
            assert not any(event.name == "alert_state_change" for event in monitor_events._received)

            response = call_api("GET", "/api/monitoring/state", {}, user_token)
            check_api_response(response)
            assert response.json()["state"] == "monitoring_armed"

            monitor_events.clear_events()
            set_input_state("CH01", strategy.active)

            monitor_events.wait_for_events(
                [
                    # MonitorEvent(
                    #     name="alert_state_change",
                    #     payload={
                    #         "id": 1,
                    #         "alertType": "alert_away",
                    #         "startTime": "2026-05-02 19:09:40",
                    #         "endTime": None,
                    #         "silent": True,
                    #         "sensors": [
                    #             {
                    #                 "sensorId": 1,
                    #                 "channel": 0,
                    #                 "typeId": 1,
                    #                 "name": "Room 1",
                    #                 "description": "Test room 1 movement sensor",
                    #                 "startTime": "2026-05-02 21:09:30",
                    #                 "endTime": None,
                    #                 "delay": 0,
                    #                 "silent": True,
                    #                 "monitorPeriod": case["sensor_expected_monitor_period"],
                    #                 "monitorThreshold": case["sensor_expected_monitor_threshold"],
                    #             }
                    #         ],
                    #     },
                    #     diffOptions={
                    #         "ignore_order": True,
                    #         "exclude_paths": [
                    #             "root['id']",
                    #             "root['startTime']",
                    #             "root['sensors'][0]['sensorId']",
                    #             "root['sensors'][0]['startTime']",
                    #         ],
                    #     },
                    # ),
                    MonitorEvent(
                        name="sensors_state_change",
                        payload=True,
                    ),
                    # MonitorEvent(
                    #     name="syren_state_change",
                    #     payload=True,
                    # ),
                ],
                timeout=case["trigger_timeout"],
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

        response = call_api("GET", "/api/arms/count", {}, user_token)
        check_api_response(response)
        assert response.json() == 1

        response = call_api("GET", "/api/arms/count?has_alert=true", {}, user_token)
        check_api_response(response)
        assert response.json() == 1

    finally:
        monitor_events.disconnect()
