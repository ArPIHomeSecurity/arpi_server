"""
Manage areas
"""

import logging
from threading import Lock
from time import monotonic

from sqlalchemy import select

from monitor.actions import (
    MonitorArmAwayCommand,
    MonitorArmStayCommand,
    MonitorDisarmCommand,
)
from monitor.broadcast import Broadcaster
from monitor.communication.mqtt import SYSTEM_TOPIC_NAME, MQTTClient, sanitize
from monitor.database import get_database_session
from monitor.output.handler import OutputHandler
from monitor.socket_io import send_area_state
from monitor.storage import State, States
from utils.constants import (
    ARM_AWAY,
    ARM_DISARM,
    ARM_STAY,
    LOG_MONITOR,
    MONITORING_READY,
    MONITORING_STARTUP,
    MONITORING_UPDATING_CONFIG,
)
from utils.models import Area
from utils.queries import get_arm_state, get_user_with_access_code

logger = logging.getLogger(LOG_MONITOR)

# Access codes are numeric and at least 4 digits long, so an unthrottled command topic
# is a 10.000 attempt brute force away from disarming the system. Every attempt also
# costs a bcrypt verification per user, so this bounds the CPU cost as well.
MQTT_MAX_CODE_ATTEMPTS = 5
MQTT_ATTEMPT_WINDOW_SEC = 5 * 60
MQTT_LOCKOUT_SEC = 15 * 60


class AreaHandler:
    """
    Class for managing areas
    """

    def __init__(self, session, broadcaster: Broadcaster):
        self._db_session = session
        self._broadcaster = broadcaster
        # sanitized area name => area id, used to route the MQTT commands
        self._area_ids_by_topic = {}
        # topics published as area panels, used to clean up the topics of areas that
        # were renamed or started colliding since the last publish
        self._published_topics = set()

        # guards the fields below, they are written from the MQTT client thread
        self._mqtt_lock = Lock()
        self._failed_code_times = []
        self._locked_out_until = 0

        self._mqtt_client = MQTTClient(on_command=self._handle_mqtt_command)
        self._mqtt_client.connect(client_id="arpi_area")
        logger.debug("AreaHandler initialized")

    def _register_code_failure(self) -> bool:
        """
        Record a rejected access code and return True if the lockout was triggered by it.
        """
        now = monotonic()
        with self._mqtt_lock:
            self._failed_code_times = [
                attempt
                for attempt in self._failed_code_times
                if now - attempt < MQTT_ATTEMPT_WINDOW_SEC
            ]
            self._failed_code_times.append(now)
            if len(self._failed_code_times) < MQTT_MAX_CODE_ATTEMPTS:
                return False

            self._failed_code_times = []
            self._locked_out_until = now + MQTT_LOCKOUT_SEC
            return True

    def _is_locked_out(self) -> bool:
        """
        Return True while MQTT commands are rejected because of too many wrong codes.
        """
        with self._mqtt_lock:
            return monotonic() < self._locked_out_until

    def _handle_mqtt_command(self, panel_name, arm_type, code):
        """
        Handle an arm/disarm command received from MQTT (Home Assistant).

        Runs on the MQTT client thread, so it must not use the database session of
        the monitoring thread. The access code identifies the user, without a valid
        code the command is dropped.
        """
        if self._is_locked_out():
            logger.warning(
                "Rejected MQTT command for '%s': locked out after too many invalid codes",
                panel_name,
            )
            return

        user_id = None
        with get_database_session() as db_session:
            user = get_user_with_access_code(db_session, code) if code else None
            if user is not None:
                user_id = user.id

        if user_id is None:
            logger.warning("Rejected MQTT command for '%s': invalid access code", panel_name)
            if self._register_code_failure():
                logger.error(
                    "Too many invalid access codes over MQTT, ignoring commands for %s minutes",
                    MQTT_LOCKOUT_SEC // 60,
                )
            return

        if panel_name == SYSTEM_TOPIC_NAME:
            area_id = None
        else:
            area_id = self._area_ids_by_topic.get(panel_name)
            if area_id is None:
                logger.error("Received MQTT command for unknown area '%s'", panel_name)
                return

        if arm_type == ARM_AWAY:
            command = MonitorArmAwayCommand(user_id=user_id, area_id=area_id, use_delay=True)
        elif arm_type == ARM_STAY:
            command = MonitorArmStayCommand(user_id=user_id, area_id=area_id, use_delay=True)
        elif arm_type == ARM_DISARM:
            command = MonitorDisarmCommand(user_id=user_id, area_id=area_id)
        else:
            logger.error("Received MQTT command with unknown arm type '%s'", arm_type)
            return

        logger.info(
            "MQTT command from user id=%s for '%s': %s",
            user_id,
            panel_name,
            arm_type,
        )
        self._broadcaster.send_message(command)

    def _has_own_topic(self, area) -> bool:
        """
        Return True if the area owns its MQTT topics, False if it collides with
        another area or the system panel and must not be published.
        """
        return self._area_ids_by_topic.get(sanitize(area.name)) == area.id

    def _panel_areas(self):
        """
        The areas published as their own MQTT panel.
        """
        return [
            area
            for area in self._db_session.query(Area).filter(Area.deleted == False).all()
            if self._has_own_topic(area)
        ]

    def publish_arm_states(self):
        """
        Publish the current arm states of the MQTT panels (monitoring thread only).
        """
        for area in self._panel_areas():
            self._mqtt_client.publish_area_state(area.name, area.arm_state)

        self._mqtt_client.publish_system_state(get_arm_state(self._db_session))

    def publish_arming(self):
        """
        Show the MQTT panels as arming while the exit delay runs (monitoring thread
        only). The areas staying disarmed keep their disarmed state, they are not
        part of the running arm.
        """
        for area in self._panel_areas():
            if area.arm_state == ARM_DISARM:
                self._mqtt_client.publish_area_state(area.name, area.arm_state)
            else:
                self._mqtt_client.publish_area_arming(area.name)

        self._mqtt_client.publish_system_arming()

    def load_areas(self):
        """
        Load all the areas from the database.
        """
        disarmed_states = [
            MONITORING_STARTUP,
            MONITORING_READY,
            MONITORING_UPDATING_CONFIG,
        ]

        # restore the arm state of the areas if the monitoring state is disarmed
        monitoring_state = States.get(State.MONITORING)
        self._db_session.expire_all()
        for area in (
            self._db_session.execute(select(Area).filter(Area.deleted == False)).scalars().all()
        ):
            if monitoring_state in disarmed_states and area.arm_state != ARM_DISARM:
                area.arm_state = ARM_DISARM
                logger.info("Area '%s' restored to disarmed state", area.name)

            send_area_state(area.serialized)

        self._db_session.commit()

    def publish_areas(self):
        """
        Load all the areas from the database.
        """
        areas = self._db_session.query(Area).all()

        area_ids_by_topic = {}
        # sanitize() is not injective ("A B" and "A.B" both become "a_b"), so two areas can
        # end up on the same topics. Their configs and states would overwrite each other and
        # routing a command to either of them would be a guess, so colliding areas (including
        # an area colliding with the system panel) are not published over MQTT at all.
        colliding_topics = set()
        for area in areas:
            if area.deleted:
                continue

            topic_name = sanitize(area.name)
            if topic_name == SYSTEM_TOPIC_NAME:
                logger.warning(
                    "Area '%s' collides with the system panel topic, it is not available over MQTT",
                    area.name,
                )
            elif topic_name in area_ids_by_topic or topic_name in colliding_topics:
                logger.warning(
                    "Area '%s' collides with another area on the MQTT topic '%s', "
                    "neither of them is available over MQTT",
                    area.name,
                    topic_name,
                )
                colliding_topics.add(topic_name)
                area_ids_by_topic.pop(topic_name, None)
            else:
                area_ids_by_topic[topic_name] = area.id

        self._area_ids_by_topic = area_ids_by_topic

        # Topics that lost their area (renamed or now colliding) keep their retained
        # config/state on the broker: home assistant would show a ghost panel that
        # silently ignores every command, so those topics are cleaned up. Ghosts of
        # areas changed while the monitor was not running are not detected.
        published_topics = set(area_ids_by_topic)
        for topic_name in (self._published_topics | colliding_topics) - published_topics:
            logger.info("Deleting MQTT topics of the removed area panel '%s'", topic_name)
            self._mqtt_client.delete_area(topic_name)
        self._published_topics = published_topics

        for area in areas:
            if not area.deleted:
                if self._has_own_topic(area):
                    self._mqtt_client.publish_area_config(area.id, area.name)
                    self._mqtt_client.publish_area_state(area.name, area.arm_state)
                send_area_state(area.serialized)
            else:
                self._mqtt_client.delete_area(area.name)

        self._mqtt_client.publish_system_config()
        self._mqtt_client.publish_system_state(get_arm_state(self._db_session))

    def change_area_arm(self, arm_type, area_id=None) -> bool:
        """
        Change the arm state of the given area.

        The MQTT panels are not updated here: whether the new state or arming has to be
        published depends on the exit delay, which is only known to the caller. See
        publish_arm_states() and publish_arming().

        Return True if the area was found and the arm state was changed.
        """
        logger.info("Arming area id=%s to %s", area_id, arm_type)
        area = self._db_session.query(Area).get(area_id)
        if area is None or area.deleted:
            logger.error("Area not found or deleted")
            return False

        if area.sensors == []:
            logger.error("Area has no sensors")
            return False

        if area.arm_state == arm_type:
            logger.info("Area id=%s already in state %s", area_id, arm_type)
            return False

        logger.info("Area id=%s state changed from %s to %s", area.id, area.arm_state, arm_type)

        # update output channel
        if arm_type in (ARM_AWAY, ARM_STAY):
            OutputHandler.send_area_armed(area)
        elif arm_type == ARM_DISARM:
            OutputHandler.send_area_disarmed(area)

        area.arm_state = arm_type
        send_area_state(area.serialized)
        self._db_session.commit()

        return True

    def change_areas_arm(self, arm_type) -> bool:
        """
        Change the arm state of all the areas.
        Skip deleted areas or areas without a sensor.

        The MQTT panels are not updated here, see change_area_arm().

        Return True if at least one area was found and the arm state was changed.
        """
        logger.info("Arming areas to %s", arm_type)
        areas = (
            self._db_session.query(Area)
            .filter(Area.deleted == False)
            .filter(Area.sensors.any())
            .all()
        )

        arm_changed = False
        for area in areas:
            if area.arm_state == arm_type:
                logger.info("Area id=%s already in state %s", area.id, arm_type)
                continue

            logger.info("Area id=%s state changed from %s to %s", area.id, area.arm_state, arm_type)
            area.arm_state = arm_type
            arm_changed = True

            # update output channel
            if arm_type in (ARM_AWAY, ARM_STAY):
                OutputHandler.send_area_armed(area)
            elif arm_type == ARM_DISARM:
                OutputHandler.send_area_disarmed(area)

        self._db_session.commit()

        for area in areas:
            send_area_state(area.serialized)

        return arm_changed

    def close(self):
        """
        Close the area handler.
        """
        logger.debug("Closing MQTT client...")
        self._mqtt_client.close()
