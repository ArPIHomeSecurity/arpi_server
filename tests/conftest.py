import json
import logging
import os
import signal
from pathlib import Path
import subprocess

from os import environ
from time import sleep

import pytest

from dotenv import load_dotenv
import requests
import socketio

from data import clear_database

load_dotenv(".env.pytest", override=True)

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def database_host():
    logger.debug("Starting database...")
    DB_HOST = environ["DB_HOST"]
    subprocess.run(["docker", "volume", "create", "argus-test-database"], check=True)

    subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "-it",
            "--name",
            "argus-test-database",
            "-v",
            f"{DB_HOST}:/var/run/postgresql",
            "-v",
            "argus-test-database:/var/lib/postgresql/data",
            "-e",
            "POSTGRES_USER=argus",
            "-e",
            "POSTGRES_PASSWORD=argus",
            "-e",
            "POSTGRES_DB=argus",
            "postgres:15",
        ],
        check=True,
    )

    # wait for the database to be ready
    DB_USER = environ["DB_USER"]
    for _ in range(30):
        result = subprocess.run(
            ["docker", "exec", "argus-test-database", "pg_isready", "-U", DB_USER],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            logger.debug("Database is ready")
            break
        logger.debug("Waiting for database to be ready...")
        sleep(1)
    else:
        raise RuntimeError("Database did not become ready in time")

    yield

    subprocess.run(["docker", "rm", "-fv", "argus-test-database"], check=True)

    subprocess.run(["docker", "volume", "rm", "argus-test-database"], check=True)


@pytest.fixture(scope="module")
def database_data(request, database_host):
    logger.debug("Running database initialization and data population")
    subprocess.run(["uv", "run", "flask", "--app", "server:app", "db", "upgrade"], check=True)

    seed_function = getattr(request, "param")
    logger.debug("Applying database seed function: %s", seed_function.__name__)
    seed_function()

    yield

    clear_database()


@pytest.fixture(scope="session")
def mqtt():
    path = Path(__file__).parent.parent
    config_path = path / "scripts" / "mosquitto" / "mosquitto.dev.conf"
    subprocess.run(["docker", "rm", "-f", "argus-mqtt-test"], check=False)
    subprocess.run(["docker", "volume", "create", "argus-mqtt-test"], check=True)
    result = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "-it",
            "--name",
            "argus-mqtt-test",
            "-p",
            "127.0.0.1:1883:1883",
            "-p",
            "127.0.0.1:9001:9001",
            "-v",
            f"{config_path}:/mosquitto/config/mosquitto.conf:ro",
            "eclipse-mosquitto",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        logger.error("Failed to start MQTT broker: %s", result.stderr)
        raise RuntimeError("Failed to start MQTT broker")

    yield

    subprocess.run(["docker", "rm", "-f", "argus-mqtt-test"], check=True)


@pytest.fixture(scope="module")
def monitoring_state():
    with open("status.json", "w") as f:
        json.dump({"State.MONITORING": "monitoring_stopped", "State.POWER": "network"}, f)


@pytest.fixture(scope="module", autouse=True)
def monitor(monitoring_state, mqtt, database_data):
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


@pytest.fixture(scope="module", autouse=True)
def server(database_data):
    host = os.environ["SERVER_HOST"]
    port = os.environ["SERVER_PORT"]

    proc = subprocess.Popen(
        [
            "uv",
            "run",
            "flask",
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


@pytest.fixture(scope="module", name="device_token")
def register_device():
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


@pytest.fixture(scope="module", name="user_token")
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
