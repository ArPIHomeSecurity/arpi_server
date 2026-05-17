import json
import logging
import os

from dotenv import load_dotenv
import pytest
from helpers.services import monitor_service

load_dotenv(".env.pytest", override=True)

logger = logging.getLogger(__name__)


@pytest.fixture()
def monitoring_state(request: pytest.FixtureRequest):
    with open("status.json", "w") as f:
        monitoring_state = request.param[0]
        power_state = request.param[1]
        json.dump({"State.MONITORING": monitoring_state, "State.POWER": power_state}, f)


@pytest.fixture(scope="function", autouse=True)
def monitor(monitoring_state, mqtt, database_data):
    host = os.environ["MONITOR_HOST"]
    port = os.environ["MONITOR_PORT"]
    with monitor_service(host, port):
        yield
