"""
Update a file with the output states
"""

import json
import logging
import os
import threading

from constants import LOG_ADOUTPUT


OUTPUT_NUMBER = int(os.environ.get("OUTPUT_NUMBER", 8))

_lock = threading.Lock()


class OutputAdapter(object):
    """
    Mock output
    """

    def __init__(self):
        self._logger = logging.getLogger(LOG_ADOUTPUT)
        self._states = [0] * OUTPUT_NUMBER
        self._write_states()

    def control_channel(self, channel: int, state: bool):
        """
        Control output by channel number
        """
        self._logger.debug("Control channel %d to %d", channel, state)
        if channel < 0 or channel > OUTPUT_NUMBER - 1:
            raise ValueError(
                f"Channel number must be between 0 and {OUTPUT_NUMBER - 1}!"
            )

        with _lock:
            with open("simulator_output.json", "r", encoding="utf-8") as channels_file:
                try:
                    self._states = json.load(channels_file)
                    self._states[channel] = 1 if state else 0
                except json.decoder.JSONDecodeError:
                    self._logger.warning(
                        "Output file is invalid!\n%s", channels_file.read()
                    )

        self._write_states()

    def _write_states(self):
        with _lock:
            with open("simulator_output.json", "w", encoding="utf-8") as channels_file:
                # write the state to the file
                channels_file.write(json.dumps(self._states))


# initialize output file
oa = OutputAdapter()
