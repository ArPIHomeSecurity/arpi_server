import logging
import time

import pytest
from dotenv import load_dotenv

from monitor.adapters.mock.utils import set_input_state
from monitor.config.helper import save_config
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


SILENT_ALERT_CASES = [
    pytest.param(
        {
            "system_syren_silent": None,
            "sensor_silent": None,
            "expected_silence": False,
            "expected_sensor_silence": False,
            "expected_syren_state": True,
        },
        id="defaults",
    ),
    pytest.param(
        {
            "system_syren_silent": None,
            "sensor_silent": True,
            "expected_silence": True,
            "expected_sensor_silence": True,
            "expected_syren_state": False,
        },
        id="sensor_silent_overrides_system_default",
    ),
    pytest.param(
        {
            "system_syren_silent": None,
            "sensor_silent": False,
            "expected_silence": False,
            "expected_sensor_silence": False,
            "expected_syren_state": True,
        },
        id="sensor_loud_overrides_system_default",
    ),
    pytest.param(
        {
            "system_syren_silent": True,
            "sensor_silent": None,
            "expected_silence": True,
            "expected_sensor_silence": True,
            "expected_syren_state": False,
        },
        id="system_silent_overrides_sensor_default",
    ),
    pytest.param(
        {
            "system_syren_silent": True,
            "sensor_silent": False,
            "expected_silence": False,
            "expected_sensor_silence": False,
            "expected_syren_state": True,
        },
        id="sensor_loud_overrides_system_silent",
    ),
    pytest.param(
        {
            "system_syren_silent": True,
            "sensor_silent": True,
            "expected_silence": True,
            "expected_sensor_silence": True,
            "expected_syren_state": False,
        },
        id="sensor_silent_overrides_system_silent",
    ),
    pytest.param(
        {
            "system_syren_silent": False,
            "sensor_silent": None,
            "expected_silence": False,
            "expected_sensor_silence": False,
            "expected_syren_state": True,
        },
        id="system_loud_overrides_sensor_default",
    ),
    pytest.param(
        {
            "system_syren_silent": False,
            "sensor_silent": False,
            "expected_silence": False,
            "expected_sensor_silence": False,
            "expected_syren_state": True,
        },
        id="system_loud_overrides_sensor_loud",
    ),
    pytest.param(
        {
            "system_syren_silent": False,
            "sensor_silent": True,
            "expected_silence": False,
            "expected_sensor_silence": False,
            "expected_syren_state": True,
        },
        id="system_loud_overrides_sensor_silent",
    ),
]


@pytest.mark.parametrize("database_data", [create_test_no_delay_v2], indirect=True)
@pytest.mark.parametrize("case", SILENT_ALERT_CASES)
def test_silent_alert_cases(device_token, user_token, case):
    monitor_events = MonitorEventsClient(device_token)

    try:
        wait_for_monitoring_ready(device_token)

        # Configure system-level syren behavior directly in DB.
        save_config(
            "syren",
            "timing",
            {"silent": case["system_syren_silent"], "delay": 0, "duration": 0},
        )

        # Configure sensor-level silent alert only.
        response = call_api(
            "PUT",
            "/api/sensor/1",
            {"silentAlert": case["sensor_silent"]},
            user_token,
        )
        check_api_response(response, expected_status=[200, 204])

        response = call_api("GET", "/api/sensor/1", {}, user_token)
        check_api_response(response)
        sensor = response.json()
        assert sensor["silentAlert"] == case["sensor_silent"]

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

        # Trigger alert on CH01. The seeded sensor is instant by default.
        set_input_state("CH01", wiring_config.select_strategy(SensorContactTypes.NC).active)
        time.sleep(0.1)  # Allow time for the alert to be processed.
        set_input_state("CH01", wiring_config.select_strategy(SensorContactTypes.NC).default)

        monitor_events.wait_for_events(
            [
                MonitorEvent(
                    name="alert_state_change",
                    payload={
                        "id": 1,
                        "alertType": "alert_away",
                        "startTime": "2026-05-02 19:09:40",
                        "endTime": None,
                        "silent": case["expected_silence"],
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
                                "silent": case["expected_sensor_silence"],
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
                    payload=case["expected_syren_state"],
                ),
            ],
            timeout=2.0,
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


@pytest.mark.parametrize("database_data", [create_test_no_delay_v2], indirect=True)
def test_loud_alert_not_overridden_by_silent_sensor(device_token, user_token):
    monitor_events = MonitorEventsClient(device_token)

    try:
        wait_for_monitoring_ready(device_token)

        # Keep system-level silent unset so sensor-level settings are used.
        save_config("syren", "timing", {"silent": None, "delay": 0, "duration": 0})

        # First sensor starts a silent alert, second sensor should force loud syren.
        response = call_api("PUT", "/api/sensor/1", {"silentAlert": False}, user_token)
        check_api_response(response, expected_status=[200, 204])

        response = call_api("PUT", "/api/sensor/2", {"silentAlert": True}, user_token)
        check_api_response(response, expected_status=[200, 204])

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

        # Trigger first (silent) sensor and keep it active while the second sensor joins the alert.
        set_input_state("CH01", wiring_config.select_strategy(SensorContactTypes.NC).active)

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
            timeout=2.0,
        )

        monitor_events.clear_events()

        # Trigger second sensor configured as loud; alert should become loud and syren turns on.
        set_input_state("CH02", wiring_config.select_strategy(SensorContactTypes.NC).active)

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
                            },
                            {
                                "sensorId": 2,
                                "channel": 1,
                                "typeId": 3,
                                "name": "Room 2",
                                "description": "Test room 2 door sensor",
                                "startTime": "2026-05-02 21:09:30",
                                "endTime": None,
                                "delay": 0,
                                "silent": True,
                                "monitorPeriod": None,
                                "monitorThreshold": 100,
                            },
                        ],
                    },
                    diffOptions={
                        "ignore_order": True,
                        "exclude_paths": [
                            "root['id']",
                            "root['startTime']",
                            "root['sensors'][0]['sensorId']",
                            "root['sensors'][0]['startTime']",
                            "root['sensors'][1]['sensorId']",
                            "root['sensors'][1]['startTime']",
                        ],
                    },
                ),
                MonitorEvent(
                    name="sensors_state_change",
                    payload=True,
                ),
            ],
            timeout=2.0,
        )

        # Reset inputs.
        set_input_state("CH01", wiring_config.select_strategy(SensorContactTypes.NC).default)
        set_input_state("CH02", wiring_config.select_strategy(SensorContactTypes.NC).default)
        time.sleep(0.1)

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


@pytest.mark.parametrize("database_data", [create_test_no_delay_v2], indirect=True)
def test_silent_alert_changes_to_loud_with_second_sensor(device_token, user_token):
    monitor_events = MonitorEventsClient(device_token)

    try:
        wait_for_monitoring_ready(device_token)

        # Keep system-level silent unset so sensor-level settings are used.
        save_config("syren", "timing", {"silent": None, "delay": 0, "duration": 0})

        # First sensor starts a silent alert, second sensor should force loud syren.
        response = call_api("PUT", "/api/sensor/1", {"silentAlert": True}, user_token)
        check_api_response(response, expected_status=[200, 204])

        response = call_api("PUT", "/api/sensor/2", {"silentAlert": False}, user_token)
        check_api_response(response, expected_status=[200, 204])

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

        # Trigger first (silent) sensor and keep it active while the second sensor joins the alert.
        set_input_state("CH01", wiring_config.select_strategy(SensorContactTypes.NC).active)

        monitor_events.wait_for_events(
            [
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
                                "name": "Room 1",
                                "description": "Test room 1 movement sensor",
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
                    payload=False,
                ),
            ],
            timeout=2.0,
        )

        monitor_events.clear_events()

        # Trigger second sensor configured as loud; alert should become loud and syren turns on.
        set_input_state("CH02", wiring_config.select_strategy(SensorContactTypes.NC).active)

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
                                "silent": True,
                                "monitorPeriod": None,
                                "monitorThreshold": 100,
                            },
                            {
                                "sensorId": 2,
                                "channel": 1,
                                "typeId": 3,
                                "name": "Room 2",
                                "description": "Test room 2 door sensor",
                                "startTime": "2026-05-02 21:09:30",
                                "endTime": None,
                                "delay": 0,
                                "silent": False,
                                "monitorPeriod": None,
                                "monitorThreshold": 100,
                            },
                        ],
                    },
                    diffOptions={
                        "ignore_order": True,
                        "exclude_paths": [
                            "root['id']",
                            "root['startTime']",
                            "root['sensors'][0]['sensorId']",
                            "root['sensors'][0]['startTime']",
                            "root['sensors'][1]['sensorId']",
                            "root['sensors'][1]['startTime']",
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
            timeout=2.0,
        )

        # Reset inputs.
        set_input_state("CH01", wiring_config.select_strategy(SensorContactTypes.NC).default)
        set_input_state("CH02", wiring_config.select_strategy(SensorContactTypes.NC).default)
        time.sleep(0.1)

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
