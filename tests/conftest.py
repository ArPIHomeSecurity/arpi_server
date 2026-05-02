import logging
from pathlib import Path
import subprocess

from os import environ
from time import sleep

import pytest

from dotenv import load_dotenv

from data import create_test_with_v2

load_dotenv(".env.pytest", override=True)

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session", autouse=True)
def database_host():
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


@pytest.fixture(scope="session", autouse=True)
def database_data(database_host):
    logger.debug("Running database initialization and data population")
    subprocess.run(["uv", "run", "flask", "--app", "server:app", "db", "upgrade"], check=True)

    # result = subprocess.run(
    #     ["uv", "run", "python", "src/bin/data.py", "-c", "test_with_v2"],
    #     check=False,
    #     capture_output=True,
    #     text=True,
    # )

    # if result.returncode != 0:
    #     logger.error("Data population output: %s", result.stderr)
    #     raise RuntimeError("Data population failed")

    create_test_with_v2()

    yield


@pytest.fixture(scope="session", autouse=True)
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
