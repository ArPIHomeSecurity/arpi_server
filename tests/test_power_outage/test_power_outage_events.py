import pytest
from data import create_test_no_delay_v2
from helpers import (
    MonitorEvent,
    MonitorEventsClient,
    call_api,
    check_api_response,
    wait_for_monitoring_ready,
)

from monitor.adapters.mock.utils import set_input_state
from utils.constants import POWER_SOURCE_BATTERY, POWER_SOURCE_NETWORK


@pytest.mark.parametrize("database_data", [create_test_no_delay_v2], indirect=True)
def test_power_outage_start_and_stop_events(device_token: str):
    monitor_events = MonitorEventsClient(device_token)

    try:
        wait_for_monitoring_ready(device_token)

        response = call_api("GET", "/api/power", {}, device_token)
        check_api_response(response)
        assert response.json()["state"] == POWER_SOURCE_NETWORK

        monitor_events.clear_events()

        # Simulate power outage by switching source from network to battery.
        set_input_state("POWER", 0)

        monitor_events.wait_for_event(
            MonitorEvent(name="power_state_change", payload=POWER_SOURCE_BATTERY),
            timeout=5.0,
        )

        response = call_api("GET", "/api/power", {}, device_token)
        check_api_response(response)
        assert response.json()["state"] == POWER_SOURCE_BATTERY

        monitor_events.clear_events()

        # Simulate power recovery by switching source back to network.
        set_input_state("POWER", 1)

        monitor_events.wait_for_event(
            MonitorEvent(name="power_state_change", payload=POWER_SOURCE_NETWORK),
            timeout=5.0,
        )

        response = call_api("GET", "/api/power", {}, device_token)
        check_api_response(response)
        assert response.json()["state"] == POWER_SOURCE_NETWORK
    finally:
        monitor_events.disconnect()