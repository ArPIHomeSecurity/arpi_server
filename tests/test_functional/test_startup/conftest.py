import json
import logging
import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

from tests.test_functional.helpers.services import monitor_service

load_dotenv(".env.pytest", override=True)

logger = logging.getLogger(__name__)


@pytest.fixture()
def monitoring_state(request: pytest.FixtureRequest):
    status_file = Path(os.getenv("STATUS_FILE", "status.json"))
    monitoring_state, power_state = request.param
    status_file.write_text(
        json.dumps({"State.MONITORING": monitoring_state, "State.POWER": power_state}),
        encoding="utf-8",
    )
    try:
        yield
    finally:
        status_file.unlink(missing_ok=True)


@pytest.fixture(scope="function", autouse=True)
def monitor(monitoring_state, mqtt, database_data):
    host = os.environ["MONITOR_HOST"]
    port = os.environ["MONITOR_PORT"]
    with monitor_service(host, port):
        yield
