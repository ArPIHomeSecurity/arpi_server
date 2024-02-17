"""
Output sign
"""

import logging
import os
from queue import Queue
from threading import Thread
from time import time

from constants import LOG_OUTPUT
from monitor.output import OUTPUT_NAMES

if os.environ.get("USE_SIMULATOR", "false").lower() == "false":
    from monitor.adapters.output import OutputAdapter
else:
    from monitor.adapters.mock.output import OutputAdapter


class OutputSign(Thread):
    """
    Generating output sign
    """

    def __init__(self, stop_event, channel, default_state, delay, duration=None):
        super().__init__(name="OutputSign")
        self._stop_event = stop_event
        self._channel = channel
        self._default_state = default_state
        self._delay = delay
        self._duration = duration
        self._output_adapter = OutputAdapter()
        self._actions = Queue()
        self._logger = logging.getLogger(LOG_OUTPUT)

    def run(self):
        self._logger.info(
            "Output sign on channel '%s' triggered (%d / %d)",
            OUTPUT_NAMES[self._channel],
            self._delay or 0,
            self._duration,
        )

        now = start_time = time()
        if self._delay == 0:
            # set it to active state
            output_state = not self._default_state
            self._output_adapter.control_channel(self._channel, output_state)
        else:
            # set it to inactive state
            output_state = self._default_state

        while not self._stop_event.is_set() and not self._stop_event.wait(timeout=1):
            # if after delay and still in default state, set it to active state
            if start_time + self._delay <= now and output_state == self._default_state:
                output_state = not self._default_state
                self._logger.debug(
                    "Output sign on channel '%s' turned %s after delay",
                    OUTPUT_NAMES[self._channel],
                    "on" if output_state else "off",
                )
            elif (
                self._duration > -1
                and start_time + self._delay + self._duration <= now
                and output_state != self._default_state
            ):
                self._logger.debug(
                    "Output sign on channel %s turned %s after duration",
                    OUTPUT_NAMES[self._channel],
                    "off" if output_state else "on",
                )
                output_state = self._default_state

            self._output_adapter.control_channel(self._channel, output_state)
            if (
                self._duration == -1
                and start_time + self._delay <= now
                and output_state != self._default_state
            ) or (
                self._duration > -1 and start_time + self._delay + self._duration <= now
            ):
                self._logger.debug("No duration, break loop after delay")
                break

            now = time()

        self._logger.debug("Waiting for stop event")
        if self._duration == -1 and self._stop_event.wait():
            self._logger.debug(
                "Output sign on channel '%s' turned off", OUTPUT_NAMES[self._channel]
            )
            output_state = self._default_state
            self._output_adapter.control_channel(self._channel, output_state)

        self._logger.debug(
            "Output sign exited on channel '%s'", OUTPUT_NAMES[self._channel]
        )
