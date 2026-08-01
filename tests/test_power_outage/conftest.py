import json
import logging
import os

import pytest
from helpers.services import monitor_service

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def monitoring_state():
    with open("status.json", "w", encoding="utf-8") as file_handle:
        json.dump({"State.MONITORING": "monitoring_stopped", "State.POWER": "network"}, file_handle)


@pytest.fixture(scope="module", autouse=True)
def monitor(monitoring_state, mqtt, database_data):
    host = os.environ["MONITOR_HOST"]
    port = os.environ["MONITOR_PORT"]
    with monitor_service(host, port):
        yield
