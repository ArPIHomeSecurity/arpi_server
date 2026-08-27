"""
Managing outputs
"""

import contextlib
import logging
from queue import Empty, Queue
from threading import Event, Thread

from monitor.actions import MonitorStopCommand, MonitorUpdateConfigCommand
from monitor.adapters.output import get_output_adapter
from monitor.broadcast import Broadcaster
from monitor.communication.mqtt import MQTTClient
from monitor.database import create_database_session
from monitor.output import OUTPUT_NAMES
from monitor.output.notification import EventType, Notification, TriggerSource
from monitor.output.sign import OutputSign
from monitor.socket_io import send_output_state
from utils.constants import LOG_OUTPUT
from utils.models import Area, Output, OutputTriggerType

logger = logging.getLogger(LOG_OUTPUT)


class OutputHandler(Thread):
    """
    Class for managing outputs
    """

    MQTT_CLIENT_ID = "arpi_outputs"

    _notifications = Queue()

    @classmethod
    def send_area_armed(cls, area: Area):
        """
        Send signal when area armed
        """
        cls._notifications.put(
            Notification(type=TriggerSource.AREA, state=EventType.START, area_id=area.id)
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
        cls._notifications.put(Notification(type=TriggerSource.SYSTEM, state=EventType.START))

    @classmethod
    def send_system_disarmed(cls):
        """
        Send signal when system disarmed
        """
        cls._notifications.put(Notification(type=TriggerSource.SYSTEM, state=EventType.STOP))

    @classmethod
    def send_button_pressed(cls, output_id: int):
        """
        Send signal when manual impulse
        """
        cls._notifications.put(
            Notification(type=TriggerSource.BUTTON, state=EventType.START, output_id=output_id)
        )

    @classmethod
    def send_button_released(cls, output_id: int):
        """
        Send signal when manual impulse released
        """
        cls._notifications.put(
            Notification(type=TriggerSource.BUTTON, state=EventType.STOP, output_id=output_id)
        )

    def __init__(self, broadcaster: Broadcaster):
        super().__init__(name="OutputHandler")
        self._broadcaster = broadcaster
        self._actions = Queue()
        self._outputs = None
        self._buttons = None
        self._stop_event = None
        self._signs = {}
        self._mqtt_client: MQTTClient | None = None
        self._published_topics: set[tuple[int, str]] = set()

        self._broadcaster.register_queue(id(self), self._actions)

    def initialize_mqtt(self):
        """
        Connect to the MQTT broker from the handler thread.
        """
        self._mqtt_client = MQTTClient(
            on_output_command=self._handle_mqtt_command,
            topic_validator=self.is_outputname_valid,
        )
        self._mqtt_client.connect(client_id=self.MQTT_CLIENT_ID)
        self._mqtt_client.subscribe_outputs()

    def update_mqtt_config(self):
        """
        Update the MQTT configuration.
        """
        if self._mqtt_client is not None:
            self._mqtt_client.close()
            self._mqtt_client.connect(client_id=self.MQTT_CLIENT_ID)

    def is_outputname_valid(self, item_id: int | None, item_name: str) -> bool:
        """Return whether a retained MQTT name belongs to a current output."""
        with create_database_session() as session:
            for output in session.query(Output).all():
                if output.id == item_id:
                    return True

        logger.warning("MQTT topic '%s / %s' does not match any current output", item_name, item_id)
        return False

    def load_outputs(self):
        """
        Load outputs from database
        """
        logger.debug("Loading outputs from database")
        with create_database_session() as db_session:
            self._outputs = db_session.query(Output).all()

            # initialize output default states
            logger.info("Initializing outputs from database")
            adapter = get_output_adapter()
            for output in self._outputs:
                if output.channel is not None:
                    adapter.control_channel(output.channel, output.default_state)
                    send_output_state(output.id, output.state)

            self.publish_outputs()

            logger.debug("Loaded %s outputs", len(self._outputs))

    def publish_outputs(self):
        """
        Publish the output configs and states to MQTT.

        Based on the previously published topics, remove the state and configs of the
        outputs that were renamed or deleted.
        """
        if self._mqtt_client is None:
            return

        previously_published_topics = self._published_topics
        self._published_topics = set()
        for output in self._outputs:
            self._mqtt_client.publish_output_config(
                output.id, output.name, output.trigger_type == OutputTriggerType.BUTTON
            )
            self._mqtt_client.publish_output_state(output.id, output.name, output.state)
            self._published_topics.add((output.id, output.name))

        orphaned_topics = previously_published_topics - self._published_topics
        for output_id, output_name in orphaned_topics:
            logger.info(
                "Removing orphaned MQTT topic for output '%s' (id=%s) that was renamed or deleted",
                output_name,
                output_id,
            )
            self._mqtt_client.delete_output(output_id, output_name)

    def _handle_mqtt_command(self, output_id: int, output_name: str, state: bool):
        """
        Handle a switch command received from the MQTT broker.
        """
        output = self.get_output(output_id=output_id)
        if output is None:
            logger.warning("MQTT command for unknown output '%s' (id=%s)", output_name, output_id)
            return

        if output.trigger_type != OutputTriggerType.BUTTON:
            logger.warning(
                "MQTT command rejected for output '%s' (id=%s): only button outputs are"
                " controllable",
                output.name,
                output_id,
            )
            return

        if not output.enabled:
            logger.warning("MQTT command for disabled output '%s' (id=%s)", output.name, output_id)
            return

        logger.info("MQTT command for output '%s' (id=%s): %s", output.name, output_id, state)
        if state:
            OutputHandler.send_button_pressed(output_id)
        else:
            OutputHandler.send_button_released(output_id)

    def publish_output_state(self, output_id: int, state: bool):
        """
        Publish the state of an output changed by a sign.
        """
        if self._mqtt_client is None:
            return

        output = self.get_output(output_id=output_id)
        if output is not None:
            self._mqtt_client.publish_output_state(output_id, output.name, state)

    def run(self) -> None:
        self.initialize_mqtt()
        self.load_outputs()
        while True:
            message = None
            with contextlib.suppress(Empty):
                message = self._actions.get(timeout=0.5)

            if message is not None:
                # handle monitoring and notification actions
                match message:
                    case MonitorStopCommand():
                        break
                    case MonitorUpdateConfigCommand():
                        self.update_mqtt_config()
                        self.load_outputs()

            if not self._notifications.empty():
                self.process_notifications()

        for stop_event in self._signs.values():
            stop_event.set()

        if self._mqtt_client is not None:
            self._mqtt_client.close()

        logger.info("Output Handler stopped")

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
                logger.debug("Cannot find output for notification: %s", notification)
                continue

            stop_event = self._signs.pop(output.channel, None)
            if stop_event is not None:
                logger.debug(
                    "Stopping sign on channel %s for event %s",
                    OUTPUT_NAMES[output.channel],
                    notification,
                )
                stop_event.set()

            # start new sign
            if notification.state == EventType.START and output.enabled:
                logger.debug(
                    "Starting new sign on channel %s for event %s",
                    OUTPUT_NAMES[output.channel],
                    notification,
                )
                stop_event = Event()
                sign = OutputSign(stop_event, output, on_state_change=self.publish_output_state)
                self._signs[output.channel] = stop_event
                sign.start()
            # stop existing sign
            elif notification.state == EventType.STOP:
                pass

    def get_output(self, output_id: int | None = None, area_id: int | None = None) -> Output:
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
            logger.error("Invalid notification! Both area_id and button_id are set")

        return None
