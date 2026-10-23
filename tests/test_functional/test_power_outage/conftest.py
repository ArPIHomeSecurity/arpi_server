import json
import logging
import os
from pathlib import Path

import pytest

from tests.test_functional.helpers.services import monitor_service

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def monitoring_state():
    status_file = Path(os.getenv("STATUS_FILE", "status.json"))
    status_file.write_text(
        json.dumps({"State.MONITORING": "monitoring_stopped", "State.POWER": "network"}),
        encoding="utf-8",
    )
    try:
        yield
    finally:
        status_file.unlink(missing_ok=True)


@pytest.fixture(scope="module", autouse=True)
def monitor(monitoring_state, mqtt, database_data):
    host = os.environ["MONITOR_HOST"]
    port = os.environ["MONITOR_PORT"]
    with monitor_service(host, port):
        yield
