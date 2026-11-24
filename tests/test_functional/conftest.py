# pylint: disable=wrong-import-position
import contextlib

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

from monitor.adapters.mock.utils import (
    DEFAULT_ZIGBEE_DATA,
    SIMULATOR_ZIGBEE_FILE,
    initialize_input_states,
    protected_read,
    reset_zigbee_devices,
    set_zigbee_devices,
)
from tests.test_functional.data import cleanup_database, clear_database
from tests.test_functional.helpers import wait_for_sensors_inactive
from tests.test_functional.helpers.services import server_service

logger = logging.getLogger(__name__)


@pytest.fixture(autouse=True)
def setup_logging():
    logging.getLogger("bellows").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("serialx").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("zigpy").setLevel(logging.WARNING)


@pytest.fixture(scope="session")
def database_host():
    logger.debug("Starting database...")
    DB_HOST = environ["DB_HOST"]
    subprocess.run(["docker", "rm", "-f", "argus-test-database"], capture_output=True, check=False)
    subprocess.run(
        ["docker", "volume", "create", "argus-test-database"], capture_output=True, check=True
    )
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
            check=False,
        )
        if result.returncode == 0:
            logger.debug("Database is ready")
            break
        logger.debug("Waiting for database to be ready...")
        sleep(1)
    else:
        raise RuntimeError("Database did not become ready in time")

    try:
        yield
    finally:
        subprocess.run(["docker", "rm", "-fv", "argus-test-database"], check=True)
        subprocess.run(["docker", "volume", "rm", "argus-test-database"], check=True)


@pytest.fixture(scope="module")
def database_data(request, database_host):
    logger.debug("Running database initialization and data population")
    subprocess.run(["uv", "run", "flask", "--app", "server:app", "db", "upgrade"], check=True)

    seed_function = getattr(request, "param", None)
    if seed_function:
        logger.debug("Applying database seed function: %s", seed_function.__name__)
        seed_function()

    initialize_input_states(int(os.environ.get("INPUT_NUMBER", "15")), power_state=1)

    try:
        yield
    finally:
        clear_database()


@pytest.fixture(scope="module")
def zigbee_state(database_data):
    zigbee_path = Path(SIMULATOR_ZIGBEE_FILE)
    zigbee_file_exists = zigbee_path.exists()
    original_zigbee_data = protected_read(SIMULATOR_ZIGBEE_FILE, DEFAULT_ZIGBEE_DATA)

    try:
        reset_zigbee_devices()
        yield
    finally:
        reset_zigbee_devices()
        if zigbee_file_exists:
            set_zigbee_devices(original_zigbee_data)


@pytest.fixture(scope="session")
def mqtt():
    path = Path(__file__).parents[2]
    config_path = path / "scripts" / "mosquitto" / "mosquitto.dev.conf"
    subprocess.run(["docker", "rm", "-f", "argus-mqtt-test"], capture_output=True, check=False)
    subprocess.run(
        ["docker", "volume", "create", "argus-mqtt-test"], capture_output=True, check=True
    )
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
    else:
        logger.debug("MQTT broker started successfully")

    try:
        yield
    finally:
        subprocess.run(["docker", "rm", "-f", "argus-mqtt-test"], check=True)
        subprocess.run(["docker", "volume", "rm", "argus-mqtt-test"], check=True)


@pytest.fixture(scope="module", autouse=True)
def server(database_data):
    host = os.environ["SERVER_HOST"]
    port = os.environ["SERVER_PORT"]
    with server_service(host, port):
        yield

    with contextlib.suppress(FileNotFoundError):
        os.unlink(os.environ["SIMULATOR_INPUT_FILE"])

    with contextlib.suppress(FileNotFoundError):
        os.unlink(os.environ["SIMULATOR_OUTPUT_FILE"])

    with contextlib.suppress(FileNotFoundError):
        os.unlink(os.environ["SIMULATOR_KEYPAD_FILE"])

    with contextlib.suppress(FileNotFoundError):
        os.unlink(os.environ["SIMULATOR_ZIGBEE_FILE"])


@pytest.fixture(scope="module", name="device_token")
def register_device(server):
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


@pytest.fixture(autouse=True)
def reset_input_states(database_data, device_token):
    logger.debug("Resetting input states...")
    num_channels = int(os.environ.get("INPUT_NUMBER", "15"))
    initialize_input_states(num_channels, power_state=1)
    reset_zigbee_devices()
    wait_for_sensors_inactive(device_token)
    yield


@pytest.fixture(scope="function", autouse=True)
def cleanup_database_fixture():
    yield
    cleanup_database()
