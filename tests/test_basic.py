import logging
import os
import signal
import subprocess

from time import sleep

from monitor.adapters.mock.utils import set_input_states
import pytest
import requests

from monitor.sensor.detector import wiring_config


logger = logging.getLogger(__name__)

CHANNEL_CUT = wiring_config.open_circuit
CHANNEL_SHORTCUT = wiring_config.shortcut

POWER_LOW = 0
POWER_HIGH = 1

# def set_channel_state(channel, state):
#     channel_values = {f"CH{i:02d}": CHANNEL_CUT for i in range(1, os.environ["INPUT_NUMBER"] + 1)}
#     channel_values["POWER"] = POWER_HIGH

#     set_input_states(channel_values,)


@pytest.fixture(scope="session")
def monitor():
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

    sleep(5)  # wait for the monitor to start
    yield

    # kill the monitor process twice, at least in terminal it needs two signals to stop
    os.killpg(proc.pid, signal.SIGTERM)
    os.killpg(proc.pid, signal.SIGTERM)
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


def test_arm_away(monitor, server, user_token):
    # call rest api to arm away
    host = os.environ["SERVER_HOST"]
    port = os.environ["SERVER_PORT"]
    response = requests.put(
        f"http://{host}:{port}/api/monitoring/arm?type=arm_away",
        headers={
            "Authorization": f"Bearer {user_token}",
            "Origin": "http://localhost:8100",
        },
    )
    assert response.status_code == 200

    # get monitoring arm status
    response = requests.get(
        f"http://{host}:{port}/api/monitoring/arm",
        headers={
            "Authorization": f"Bearer {user_token}",
            "Origin": "http://localhost:8100",
        },
    )
    assert response.status_code == 200

    # disarm the system
    response = requests.put(
        f"http://{host}:{port}/api/monitoring/arm?type=disarm",
        headers={
            "Authorization": f"Bearer {user_token}",
            "Origin": "http://localhost:8100",
        },
    )
    assert response.status_code == 200


def test_alert(monitor, server, user_token):
    # call rest api to arm away
    host = os.environ["SERVER_HOST"]
    port = os.environ["SERVER_PORT"]
    response = requests.put(
        f"http://{host}:{port}/api/monitoring/arm?type=arm_away",
        headers={
            "Authorization": f"Bearer {user_token}",
            "Origin": "http://localhost:8100",
        },
    )
    assert response.status_code == 200

    # set channel to activate
