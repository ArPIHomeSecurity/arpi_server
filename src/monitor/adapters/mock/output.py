"""
Update a file with the output states
"""

import logging
import os

from constants import LOG_ADOUTPUT
from monitor.adapters.mock.utils import set_output_states
from monitor.adapters.output_base import OutputAdapterBase


OUTPUT_NUMBER = int(os.environ.get("OUTPUT_NUMBER", 8))


class OutputAdapter(OutputAdapterBase):
    """
    Mock output adapter for simulator mode.
    """

    def __init__(self):
        self._logger = logging.getLogger(LOG_ADOUTPUT)
        self._states = [0] * OUTPUT_NUMBER

    def control_channel(self, channel: int, state: bool):
        """
        Control output by channel number
        """
        self._logger.debug("Control channel %d to %d", channel, state)
        self._states[channel] = state
        set_output_states(self._states)

    @property
    def states(self):
        """
        Get the current states of all output channels.
        """
        return self._states
