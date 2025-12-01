"""
Managing outputs
"""

import contextlib
import logging
import os

from queue import Empty, Queue
from threading import Event, Thread

from utils.constants import LOG_OUTPUT, MONITOR_STOP, MONITOR_UPDATE_CONFIG
from utils.models import Area, Output, OutputTriggerType
from monitor.broadcast import Broadcaster
from monitor.database import get_database_session
from monitor.output import OUTPUT_NAMES
from monitor.output.notification import Notification, EventType, TriggerSource
from monitor.output.sign import OutputSign
from monitor.socket_io import send_output_state

from monitor.adapters.output import get_output_adapter


class OutputHandler(Thread):
    """
    Class for managing outputs
    """

    _notifications = Queue()

    @classmethod
    def send_area_armed(cls, area: Area):
        """
        Send signal when area armed
        """
        cls._notifications.put(
            Notification(
                type=TriggerSource.AREA, state=EventType.START, area_id=area.id
            )
        )

    @classmethod
    def send_area_disarmed(cls, area: Area):
        """
        Send signal when area disarmed
        """
        cls._notifications.put(
            Notification(type=TriggerSource.AREA, state=EventType.STOP, area_id=area.id)
        )

    @classmethod
    def send_system_armed(cls):
        """
        Send signal when system armed
        """
        cls._notifications.put(
            Notification(type=TriggerSource.SYSTEM, state=EventType.START)
        )

    @classmethod
    def send_system_disarmed(cls):
        """
        Send signal when system disarmed
        """
        cls._notifications.put(
            Notification(type=TriggerSource.SYSTEM, state=EventType.STOP)
        )

    @classmethod
    def send_button_pressed(cls, output_id: int):
        """
        Send signal when manual impulse
        """
        cls._notifications.put(
            Notification(
                type=TriggerSource.BUTTON, state=EventType.START, output_id=output_id
            )
        )

    @classmethod
    def send_button_released(cls, output_id: int):
        """
        Send signal when manual impulse released
        """
        cls._notifications.put(
            Notification(
                type=TriggerSource.BUTTON, state=EventType.STOP, output_id=output_id
            )
        )

    def __init__(self, broadcaster: Broadcaster):
        super().__init__(name="OutputHandler")
        self._broadcaster = broadcaster
        self._actions = Queue()
        self._logger = logging.getLogger(LOG_OUTPUT)
        self._outputs = None
        self._buttons = None
        self._stop_event = None
        self._signs = {}

        self._broadcaster.register_queue(id(self), self._actions)

    def load_outputs(self):
        """
        Load outputs from database
        """
        self._logger.debug("Loading outputs from database")
        db_session = get_database_session()
        self._outputs = db_session.query(Output).all()

        # initialize output default states
        self._logger.info("Initializing outputs from database")
        adapter = get_output_adapter()
        for output in self._outputs:
            if output.channel is not None:
                adapter.control_channel(output.channel, output.default_state)
                send_output_state(output.id, output.state)

        db_session.close()

        self._logger.debug("Loaded %s outputs", len(self._outputs))

    def run(self) -> None:
        self.load_outputs()
        while True:
            message = None
            with contextlib.suppress(Empty):
                message = self._actions.get(timeout=0.5)

            if message is not None:
                # handle monitoring and notification actions
                if message["action"] == MONITOR_STOP:
                    break
                elif message["action"] == MONITOR_UPDATE_CONFIG:
                    self.load_outputs()

            if not self._notifications.empty():
                self.process_notifications()

        for stop_event in self._signs.values():
            stop_event.set()

        self._logger.info("Output Handler stopped")

    def process_notifications(self) -> None:
        """
        Process notifications and send signals to outputs
        """
        while True:
            try:
                notification = self._notifications.get(block=False)
            except Empty:
                break

            output_args = {
                TriggerSource.AREA: {"area_id": notification.area_id},
                TriggerSource.SYSTEM: {},
                TriggerSource.BUTTON: {"output_id": notification.output_id},
            }

            output = self.get_output(**output_args.get(notification.type, {}))
            if output is None:
                self._logger.debug(
                    "Cannot find output for notification: %s", notification
                )
                continue

            stop_event = self._signs.pop(output.channel, None)
            if stop_event is not None:
                self._logger.debug(
                    "Stopping sign on channel %s for event %s",
                    OUTPUT_NAMES[output.channel],
                    notification,
                )
                stop_event.set()

            # start new sign
            if notification.state == EventType.START and output.enabled:
                self._logger.debug(
                    "Starting new sign on channel %s for event %s",
                    OUTPUT_NAMES[output.channel],
                    notification,
                )
                stop_event = Event()
                sign = OutputSign(stop_event, output)
                self._signs[output.channel] = stop_event
                sign.start()
            # stop existing sign
            elif notification.state == EventType.STOP:
                pass

    def get_output(self, output_id: int = None, area_id: int = None) -> Output:
        """
        Get output assigned to area
        """
        if area_id is None and output_id is None:
            # system notification
            for output in self._outputs:
                if output.trigger_type == OutputTriggerType.SYSTEM:
                    return output

            return None
        elif area_id is not None:
            # area notification
            for output in self._outputs:
                if output.area_id == area_id:
                    return output
        elif area_id is None and output_id is not None:
            # button notification
            for output in self._outputs:
                if output.id == output_id:
                    return output
        else:
            # invalid notification
            self._logger.error(
                "Invalid notification! Both area_id and button_id are set"
            )

        return None
