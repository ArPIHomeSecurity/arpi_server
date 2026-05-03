import json
import logging
import os
import signal
import subprocess

from time import sleep

import pytest
import requests
import socketio

from dotenv import load_dotenv

from monitor.adapters.mock.utils import set_input_state
from monitor.sensor.detector import wiring_config
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


@pytest.fixture(scope="session")
def monitoring_state():
    with open("status.json", "w") as f:
        json.dump({"State.MONITORING": "monitoring_stopped", "State.POWER": "network"}, f)


@pytest.fixture(scope="session")
def monitor(monitoring_state):
    host = os.environ["MONITOR_HOST"]
    port = os.environ["MONITOR_PORT"]
    proc = subprocess.Popen(
        [
            "uv",
            "run",
            "flask",
            "--app",
            "monitor.service:create_app",
            "run",
            "--no-reload",
            f"--host={host}",
            f"--port={port}",
        ],
        start_new_session=True,
    )

    logger.debug("Monitor process started with PID %s", proc.pid)

    # wait for the monitor to start
    for _ in range(30):
        try:
            sio = socketio.SimpleClient()
            sio.connect(f"http://{host}:{port}?token=invalid_token")
            break
        except socketio.exceptions.ConnectionError:
            logger.debug("Monitor is ready")
            break
        except Exception as e:
            logger.exception("Failed to connect to monitor Socket.IO: %s", e)
        finally:
            sio.disconnect()

        logger.debug("Waiting for monitor to be ready...")
        sleep(0.5)
    else:
        raise RuntimeError("Monitor did not become ready in time")

    yield

    # kill the monitor process twice, at least in terminal it needs two signals to stop
    os.killpg(proc.pid, signal.SIGKILL)
    proc.wait()


@pytest.fixture(scope="session")
def server():
    host = os.environ["SERVER_HOST"]
    port = os.environ["SERVER_PORT"]

    proc = subprocess.Popen(
        [
            "uv",
            "run",
            "flask",
            "--debug",
            "--app",
            "server",
            "run",
            f"--host={host}",
            f"--port={port}",
        ],
        start_new_session=True,
    )

    # wait for the server to start
    for _ in range(30):
        try:
            response = requests.get(f"http://{host}:{port}/api/version")
            if response.status_code == 200:
                logger.debug("Server is ready")
                break
        except requests.ConnectionError:
            pass
        logger.debug("Waiting for server to be ready...")
        sleep(0.5)
    else:
        raise RuntimeError("Server did not become ready in time")

    yield

    os.killpg(proc.pid, signal.SIGTERM)
    proc.wait()


@pytest.fixture(scope="session", name="device_token")
def register_device(monitor, server):
    # call rest api to register device
    host = os.environ["SERVER_HOST"]
    port = os.environ["SERVER_PORT"]
    response = requests.post(
        f"http://{host}:{port}/api/user/register_device",
        json={"registration_code": "ABCD1234"},
        headers={"Origin": "http://localhost:8100"},
    )
    logger.debug("Register device response: %s", response.text)
    yield response.json()["device_token"]


@pytest.fixture(scope="session", name="user_token")
def authenticate(device_token):
    # call rest api to login
    host = os.environ["SERVER_HOST"]
    port = os.environ["SERVER_PORT"]
    response = requests.post(
        f"http://{host}:{port}/api/user/authenticate",
        json={
            "device_token": device_token,
            "access_code": "1234",
        },
        headers={
            "Authorization": f"Bearer {device_token}",
            "Origin": "http://localhost:8100",
        },
    )
    logger.debug("Login response: %s", response.text)

    yield response.json()["user_token"]


def test_arm_away(monitor, server, device_token, user_token):
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
            ),
            timeout=2,
        )

        # get monitoring arm status
        response = call_api("GET", "/api/monitoring/arm", {}, user_token)
        check_api_response(response)

        assert response.status_code == 200

    finally:
        monitor_events.disconnect()


def test_alert(monitor, server, device_token, user_token):
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
                            "delay": 3,
                            "silent": True,
                            "monitorPeriod": None,
                            "monitorThreshold": 100,
                        }
                    ],
                },
                diffOptions={
                    "ignore_order": True,
                    "exclude_paths": ["root['startTime']", "root['sensors'][0]['startTime']"],
                },
            ),
            delay=3,
            timeout=0.5,
        )

    finally:
        monitor_events.disconnect()
