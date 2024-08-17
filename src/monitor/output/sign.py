"""
Output sign
"""

import logging
import os
from queue import Queue
from threading import Thread
from time import sleep, time

from constants import LOG_OUTPUT
from models import Output
from monitor.database import get_database_session
from monitor.output import OUTPUT_NAMES
from monitor.socket_io import send_output_state

if os.environ.get("USE_SIMULATOR", "false").lower() == "false":
    from monitor.adapters.output import OutputAdapter
else:
    from monitor.adapters.mock.output import OutputAdapter


class OutputSign(Thread):
    """
    Generating output sign
    """

    def __init__(self, stop_event, output: Output):
        super().__init__(name="OutputSign")
        self._stop_event = stop_event
        self._output = output
        self._output_adapter = OutputAdapter()
        self._actions = Queue()
        self._logger = logging.getLogger(LOG_OUTPUT)

        # set as daemon to avoid blocking the application
        self.daemon = True

    def run(self):
        session = get_database_session()
        channel = self._output.channel
        delay = self._output.delay
        duration = self._output.duration
        default_state = self._output.default_state

        # update state in database
        session.query(Output).filter_by(id=self._output.id).update({"state": True})
        session.commit()
        send_output_state(self._output.id, True)

        self._logger.info(
            "Output sign on channel '%s' triggered (%d / %d)",
            OUTPUT_NAMES[channel],
            delay or 0,
            duration,
        )

        start_time = time()
        output_state = default_state
        while not self._stop_event.is_set():
            # if after delay and still in default state, set it to active state
            now = time()
            if start_time + delay <= now and output_state == default_state:
                output_state = not default_state
                self._logger.debug(
                    "Output sign on channel '%s' turned %s after delay",
                    OUTPUT_NAMES[channel],
                    "on" if output_state else "off",
                )
            elif (
                duration > Output.ENDLESS_DURATION
                and start_time + delay + duration <= now
                and output_state != default_state
            ):
                self._logger.debug(
                    "Output sign on channel %s turned %s after duration",
                    OUTPUT_NAMES[channel],
                    "off" if output_state else "on",
                )
                output_state = default_state

            self._output_adapter.control_channel(channel, output_state)

            if (
                duration == Output.ENDLESS_DURATION
                and start_time + delay <= now
                and output_state != default_state
            ):
                self._logger.debug("No duration, break loop after delay")
                break

            if (
                duration > Output.ENDLESS_DURATION
                and start_time + delay + duration <= now
            ):
                self._logger.debug("Duration expired, break loop")
                break

            if self._stop_event.wait(timeout=1):
                output_state = default_state
                self._logger.debug(
                    "Output sign on channel '%s' turned off on stop event",
                    OUTPUT_NAMES[channel],
                )
                self._output_adapter.control_channel(channel, output_state)

        if duration == Output.ENDLESS_DURATION:
            self._logger.debug("Waiting for stop event")
            self._stop_event.wait()
            start_time = time()

        # stop delay
        sleep(delay)
        output_state = default_state
        self._output_adapter.control_channel(channel, output_state)
        self._logger.debug(
            "Output sign on channel '%s' turned off", OUTPUT_NAMES[channel]
        )
        self._logger.debug("Output sign exited on channel '%s'", OUTPUT_NAMES[channel])

        # update state in database
        session.query(Output).filter_by(id=self._output.id).update({"state": False})
        session.commit()        
        send_output_state(self._output.id, False)
