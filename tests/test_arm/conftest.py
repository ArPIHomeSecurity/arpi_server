import json
import logging
import os
import pytest

from monitor.adapters.mock.utils import set_input_states
from data import clear_events
from helpers.services import monitor_service


logger = logging.getLogger(__name__)


@pytest.fixture(scope="function", autouse=True)
def clear_arm_events():
    yield
    clear_events()


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
