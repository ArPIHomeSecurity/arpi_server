# pylint: disable=wrong-import-position
from dotenv import load_dotenv

load_dotenv(".env.pytest", override=True)

import logging
import os
import subprocess
from os import environ
from pathlib import Path
from time import sleep

import pytest
import requests
from data import cleanup_database, clear_database
from helpers.services import server_service

from monitor.adapters.mock.utils import set_input_states

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

    seed_function = request.param
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
            "127.0.0.1:2883:1883",
            "-p",
            "127.0.0.1:2001:9001",
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


@pytest.fixture(scope="module", autouse=True)
def server(database_data):
    host = os.environ["SERVER_HOST"]
    port = os.environ["SERVER_PORT"]
    with server_service(host, port):
        yield


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


@pytest.fixture(scope="function", autouse=True)
def reset_input_states():
    logger.debug("Resetting input states...")
    num_channels = int(os.environ.get("INPUT_NUMBER", 15))
    channel_values = [0] * num_channels + [1]  # 0 for channels, 1 for POWER
    set_input_states(channel_values)
    yield

    try:
        os.unlink(os.environ["MOCK_INPUT_FILE"])
    except FileNotFoundError:
        pass
    try:
        os.unlink(os.environ["MOCK_OUTPUT_FILE"])
    except FileNotFoundError:
        pass


@pytest.fixture(scope="function", autouse=True)
def cleanup_database_fixture():
    yield
    cleanup_database()
