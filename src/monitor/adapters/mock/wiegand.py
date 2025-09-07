import logging
from constants import LOG_ADKEYPAD
from monitor.adapters.mock.utils import DEFAULT_KEYPAD, get_keypad_state

logger = logging.getLogger(LOG_ADKEYPAD)


class WiegandReader:
    def __init__(self, *args, **kwargs):
        self._keypad_state = DEFAULT_KEYPAD.copy()

    def is_initialized(self):
        return True

    def get_pending_bit_count(self):
        self._keypad_state = get_keypad_state()
        return self._keypad_state["pending_bits"]

    def read(self):
        return self._keypad_state["data"]
