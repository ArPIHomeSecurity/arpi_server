"""
Output sign
"""

import logging
import os
from queue import Queue
from threading import Thread
from time import time

from constants import LOG_OUTPUT
from models import Output
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

        start_time = time()
        output_state = self._default_state
        while not self._stop_event.is_set():
            # if after delay and still in default state, set it to active state
            now = time()
            if start_time + self._delay <= now and output_state == self._default_state:
                output_state = not self._default_state
                self._logger.debug(
                    "Output sign on channel '%s' turned %s after delay",
                    OUTPUT_NAMES[self._channel],
                    "on" if output_state else "off",
                )
            elif (
                self._duration > Output.ENDLESS_DURATION
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
                self._duration == Output.ENDLESS_DURATION
                and start_time + self._delay <= now
                and output_state != self._default_state
            ):
                self._logger.debug("No duration, break loop after delay")
                break

            if (
                self._duration > Output.ENDLESS_DURATION
                and start_time + self._delay + self._duration <= now
            ):
                self._logger.debug("Duration expired, break loop")
                break

            if self._stop_event.wait(timeout=1):
                output_state = self._default_state
                self._logger.debug(
                    "Output sign on channel '%s' turned off on stop event",
                    OUTPUT_NAMES[self._channel]
                )
                self._output_adapter.control_channel(self._channel, output_state)

        if self._duration == Output.ENDLESS_DURATION:
            self._logger.debug("Waiting for stop event")
            self._stop_event.wait()

        output_state = self._default_state
        self._output_adapter.control_channel(self._channel, output_state)
        self._logger.debug(
            "Output sign on channel '%s' turned off", OUTPUT_NAMES[self._channel]
        )
        self._logger.debug(
            "Output sign exited on channel '%s'", OUTPUT_NAMES[self._channel]
        )
