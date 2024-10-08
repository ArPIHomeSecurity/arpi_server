"""
Update a file with the output states
"""

import fcntl
import json
import logging
import os

from constants import LOG_ADOUTPUT
from monitor.output import OUTPUT_NAMES


OUTPUT_NUMBER = int(os.environ.get("OUTPUT_NUMBER", 8))


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
        if channel is not None and (channel < 0 or channel > OUTPUT_NUMBER - 1):
            raise ValueError(
                f"Channel number must be between 0 and {OUTPUT_NUMBER - 1}!"
            )

        with open("simulator_output.json", "r", encoding="utf-8") as output_file:
            try:
                fcntl.flock(output_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                tmp_states = json.load(output_file)
                fcntl.flock(output_file, fcntl.LOCK_UN)

                for idx in range(OUTPUT_NUMBER):
                    self._states[idx] = tmp_states[OUTPUT_NAMES[idx]]
            except json.decoder.JSONDecodeError:
                self._logger.warning(
                    "Output file is invalid (=> overwriting)!\n%s",
                    output_file.read(),
                )
            except FileNotFoundError:
                self._logger.warning("Output file not found!")
            except OSError:
                self._logger.warning("Failed to lock the output file!")

        self._states[channel] = 1 if state else 0
        self._write_states()

    def _write_states(self):
        with open("simulator_output.json", "w", encoding="utf-8") as output_file:
            try:
                fcntl.flock(output_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                # write the state to the file
                states = {
                    OUTPUT_NAMES[idx]: self._states[idx]
                    for idx, state in enumerate(self._states)
                }
                output_file.write(json.dumps(states))
                fcntl.flock(output_file, fcntl.LOCK_UN)
            except OSError:
                pass


# initialize output file
oa = OutputAdapter()
