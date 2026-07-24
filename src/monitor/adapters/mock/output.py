"""
Update a file with the output states
"""

import logging
import os
from threading import Lock

from monitor.adapters.mock.utils import get_output_states, set_output_states
from monitor.adapters.output_base import OutputAdapterBase
from utils.constants import LOG_ADOUTPUT

logger = logging.getLogger(LOG_ADOUTPUT)

OUTPUT_NUMBER = int(os.environ.get("OUTPUT_NUMBER", 8))

# shared state and lock across all instances (similar to hardware adapters)
_shared_states = [0] * OUTPUT_NUMBER
_state_lock = Lock()


class OutputAdapter(OutputAdapterBase):
    """
    Mock output adapter for simulator mode.
    """

    def __init__(self):
        # Initialize shared state from file if it exists
        with _state_lock:
            try:
                file_states = get_output_states()
                if len(file_states) == OUTPUT_NUMBER:
                    # Update the shared states with file contents
                    for i, state in enumerate(file_states):
                        _shared_states[i] = 1 if state else 0
            except (FileNotFoundError, OSError, ValueError):
                logger.debug("Could not read initial state from file, using defaults")

    def is_initialized(self) -> bool:
        return True

    def control_channel(self, channel: int, state: bool):
        """
        Control output by channel number
        """
        logger.debug("Control channel %d to %d", channel, state)
        with _state_lock:
            _shared_states[channel] = 1 if state else 0
            set_output_states(_shared_states)

    @property
    def states(self):
        """
        Get the current states of all output channels.
        """
        with _state_lock:
            return _shared_states.copy()
