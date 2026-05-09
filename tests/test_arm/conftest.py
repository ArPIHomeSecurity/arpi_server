import os
import pytest

from monitor.adapters.mock.utils import set_input_states
from tests.data import clear_events


@pytest.fixture(scope="function", autouse=True)
def clear_arm_events():
    yield
    clear_events()


@pytest.fixture(scope="function", autouse=True)
def reset_input_states():
    # reset all input states to inactive after each test
    num_channels = int(os.environ.get("INPUT_NUMBER", 15))
    channel_values = [0] * num_channels + [1]  # 0 for channels, 1 for POWER
    set_input_states(channel_values)
    yield

    os.unlink(os.environ["MOCK_INPUT_FILE"])
    try:
        os.unlink(os.environ["MOCK_OUTPUT_FILE"])
    except FileNotFoundError:
        pass
