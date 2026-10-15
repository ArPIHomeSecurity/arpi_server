from time import monotonic, sleep

import pytest
from zigpy.zcl.clusters.security import IasZone

from monitor.adapters.mock.utils import (
    set_input_state,
    set_zigbee_signal,
    set_zigbee_trouble,
)
from monitor.sensor.detector import wiring_config
from tests.test_functional.data import create_test_v3_zigbee
from tests.test_functional.helpers import (
    MonitorEvent,
    MonitorEventsClient,
    call_api,
    check_api_response,
    wait_for_monitoring_ready,
)
from utils.models import SensorContactTypes

IEEE_ADDRESS = "11:22:33:44:55:66:77:88"
ENDPOINT = "1"
CLUSTER_ID = int(IasZone.cluster_id)
ATTRIBUTE_ID = int(IasZone.AttributeDefs.zone_status.id)


def _set_healthy_mock_state():
    for channel, two_eol in ((1, True), (2, False), (3, False)):
        strategy = wiring_config.select_strategy(
            SensorContactTypes.NC,
            two_eol=two_eol,
        )
        set_input_state(f"CH{channel:02d}", strategy.default)

    set_zigbee_trouble(IEEE_ADDRESS, ENDPOINT, False)
    set_zigbee_signal(IEEE_ADDRESS, ENDPOINT, CLUSTER_ID, ATTRIBUTE_ID, "alarm", False)


def _get_sensor_error(user_token, sensor_id=None):
    path = "/api/sensor/error"
    if sensor_id is not None:
        path += f"?sensorId={sensor_id}"

    response = call_api("GET", path, {}, user_token)
    check_api_response(response)
    return response.json()


def _wait_for_sensor_error(user_token, expected, sensor_id=None, timeout=5):
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        if _get_sensor_error(user_token, sensor_id) is expected:
            return
        sleep(0.1)

    assert _get_sensor_error(user_token, sensor_id) is expected


@pytest.mark.parametrize("database_data", [create_test_v3_zigbee], indirect=True)
@pytest.mark.parametrize(
    ("fault_name", "fault_value"),
    [
        pytest.param("cut", wiring_config.open_circuit, id="cut"),
        pytest.param("shortcut", wiring_config.shortcut, id="shortcut"),
    ],
)
def test_wired_double_eol_error_state(device_token, user_token, fault_name, fault_value):
    monitor_events = MonitorEventsClient(device_token)
    try:
        wait_for_monitoring_ready(device_token)
        _set_healthy_mock_state()
        _wait_for_sensor_error(user_token, False)
        monitor_events.clear_events()

        set_input_state("CH01", fault_value)
        monitor_events.wait_for_event(
            MonitorEvent(name="sensors_error_change", payload=True),
            timeout=5,
        )
        assert _get_sensor_error(user_token, sensor_id=1) is True

        monitor_events.clear_events()
        set_input_state(
            "CH01",
            wiring_config.select_strategy(
                SensorContactTypes.NC,
                two_eol=True,
            ).default,
        )
        monitor_events.wait_for_event(
            MonitorEvent(name="sensors_error_change", payload=False),
            timeout=5,
        )
        assert _get_sensor_error(user_token, sensor_id=1) is False
    finally:
        try:
            _set_healthy_mock_state()
        finally:
            monitor_events.disconnect()


@pytest.mark.parametrize("database_data", [create_test_v3_zigbee], indirect=True)
def test_zigbee_ias_zone_trouble_error_state(device_token, user_token):
    monitor_events = MonitorEventsClient(device_token)
    try:
        wait_for_monitoring_ready(device_token)
        _set_healthy_mock_state()
        _wait_for_sensor_error(user_token, False)
        monitor_events.clear_events()

        set_zigbee_trouble(IEEE_ADDRESS, ENDPOINT, True)
        monitor_events.wait_for_event(
            MonitorEvent(name="sensors_error_change", payload=True),
            timeout=5,
        )
        assert _get_sensor_error(user_token, sensor_id=4) is True

        monitor_events.clear_events()
        set_zigbee_trouble(IEEE_ADDRESS, ENDPOINT, False)
        monitor_events.wait_for_event(
            MonitorEvent(name="sensors_error_change", payload=False),
            timeout=5,
        )
        assert _get_sensor_error(user_token, sensor_id=4) is False
    finally:
        try:
            _set_healthy_mock_state()
        finally:
            monitor_events.disconnect()