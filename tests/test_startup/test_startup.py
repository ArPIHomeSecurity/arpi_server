import pytest

from helpers import MonitorEventsClient, wait_for_monitoring_ready, wait_for_monitoring_state
from data import create_test_no_delay_v2
from utils.constants import MONITORING_ARMED


@pytest.mark.parametrize("monitoring_state", [["monitoring_stopped", "network"]], indirect=True)
@pytest.mark.parametrize("database_data", [create_test_no_delay_v2], indirect=True)
def test_monitoring_stopped(device_token: str, user_token: str):
    """
    Test starting after normal shutdown.
    """
    # connect to monitor websocket first to catch events
    monitor_events = MonitorEventsClient(device_token)

    try:
        # wait for the monitor to emit the expected event
        wait_for_monitoring_ready(device_token)
    finally:
        monitor_events.disconnect()


@pytest.mark.parametrize("monitoring_state", [["monitoring_startup", "network"]], indirect=True)
@pytest.mark.parametrize("database_data", [create_test_no_delay_v2], indirect=True)
def test_monitoring_startup(device_token: str, user_token: str):
    """
    Test starting after crashed in startup phase.
    """
    # connect to monitor websocket first to catch events
    monitor_events = MonitorEventsClient(device_token)

    try:
        # wait for the monitor to emit the expected event
        wait_for_monitoring_ready(device_token)
    finally:
        monitor_events.disconnect()


@pytest.mark.parametrize(
    "monitoring_state", [["monitoring_invalid_config", "network"]], indirect=True
)
@pytest.mark.parametrize("database_data", [create_test_no_delay_v2], indirect=True)
def test_monitoring_invalid_config(device_token: str, user_token: str):
    """
    Test starting after crashed in invalid config phase.
    """
    # connect to monitor websocket first to catch events
    monitor_events = MonitorEventsClient(device_token)

    try:
        # wait for the monitor to emit the expected event
        wait_for_monitoring_ready(device_token)
    finally:
        monitor_events.disconnect()


@pytest.mark.parametrize(
    "monitoring_state", [["monitoring_updating_config", "network"]], indirect=True
)
@pytest.mark.parametrize("database_data", [create_test_no_delay_v2], indirect=True)
def test_monitoring_updating_config(device_token: str, user_token: str):
    """
    Test starting after crashed in updating config phase.
    """
    # connect to monitor websocket first to catch events
    monitor_events = MonitorEventsClient(device_token)

    try:
        # wait for the monitor to emit the expected event
        wait_for_monitoring_ready(device_token)
    finally:
        monitor_events.disconnect()


@pytest.mark.parametrize("monitoring_state", [["monitoring_armed", "network"]], indirect=True)
@pytest.mark.parametrize("database_data", [create_test_no_delay_v2], indirect=True)
def test_monitoring_armed(device_token: str, user_token: str):
    """
    Test starting after crashed in armed phase.
    We need a state of database with armed area(s) for this test,
    otherwise the monitor will restore the ready state instead of armed.
    """
    # connect to monitor websocket first to catch events
    monitor_events = MonitorEventsClient(device_token)

    try:
        # wait for the monitor to emit the expected event
        wait_for_monitoring_state(MONITORING_ARMED, device_token)
    finally:
        monitor_events.disconnect()
