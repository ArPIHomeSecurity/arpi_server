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
from monitor.config.helper import save_config
from monitor.sensor.detector import wiring_config
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
def test_02_silent_alert_cases(device_token, user_token, case):
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
