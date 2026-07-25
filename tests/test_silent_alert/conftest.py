import json
import logging
import os

import pytest
from helpers.services import monitor_service

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def monitoring_state():
    with open("status.json", "w") as f:
        json.dump({"State.MONITORING": "monitoring_stopped", "State.POWER": "network"}, f)


@pytest.fixture(scope="module", autouse=True)
def monitor(monitoring_state, mqtt, database_data):
    host = os.environ["MONITOR_HOST"]
    port = os.environ["MONITOR_PORT"]
    with monitor_service(host, port):
        yield
