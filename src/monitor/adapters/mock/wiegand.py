

import fcntl
import json
import logging

from constants import LOG_ADKEYPAD

EMPTY_DATA = {
    "pending_bits": 0,
    "data": []
}


class WiegandReader:

    def __init__(self, *args, **kwargs):
        self._keypad_data = EMPTY_DATA
        self._logger = logging.getLogger(LOG_ADKEYPAD)
        self._logger.info("Wiegand keypad created mock")
        self._load()

    def is_initialized(self):
        return True

    def _load(self):
        # write+create if not exists
        with open("simulator_keypad.json", "r+", encoding="utf-8") as keypad_file:
            fcntl.flock(keypad_file, fcntl.LOCK_EX)
            self._keypad_data = json.load(keypad_file)
            self._logger.trace("Loaded keypad data: %s", self._keypad_data)
            keypad_file.seek(0)
            keypad_file.truncate()
            json.dump(EMPTY_DATA, keypad_file)
            fcntl.flock(keypad_file, fcntl.LOCK_UN)

    def get_pending_bit_count(self):
        self._load()
        return self._keypad_data["pending_bits"]

    def read(self):
        tmp = self._keypad_data
        self._keypad_data = EMPTY_DATA
        return tmp["data"]
