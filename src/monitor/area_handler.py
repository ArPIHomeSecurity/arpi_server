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
from monitor.communication.mqtt import SYSTEM_TOPIC_NAME, MQTTClient
from monitor.database import create_database_session, get_database_session
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

    MQTT_CLIENT_ID = "arpi_area"

    def __init__(self, broadcaster: Broadcaster):
        self._db_session = None
        self._broadcaster = broadcaster
        # topics published as area panels, used to clean up the topics of areas that
        # were renamed or started colliding since the last publish
        self._published_topics: set[tuple[int | None, str]] = set()
        self._mqtt_client: MQTTClient | None = None

        # guards the fields below, they are written from the MQTT client thread
        self._mqtt_lock: Lock | None = None
        self._failed_code_times = []
        self._locked_out_until = 0

    def initialize(self):
        self._mqtt_client = MQTTClient(
            on_command=self._handle_mqtt_command,
            topic_validator=self.is_areaname_valid,
        )
        self._mqtt_lock = Lock()
        self._mqtt_client.connect(client_id=self.MQTT_CLIENT_ID)
        self._mqtt_client.subscribe_areas()
        self._db_session = get_database_session()

    def update_mqtt_config(self):
        """
        Update the MQTT configuration.
        """
        if self._mqtt_client is not None:
            self._mqtt_client.close()
            self._mqtt_client.connect(client_id=self.MQTT_CLIENT_ID)

    def is_areaname_valid(self, item_id: int | None, item_name: str) -> bool:
        """
        Return whether a retained MQTT name belongs to a current area panel.

        System panel => item_id=None, item_name=system
        Area panel => item_id=area id, item_name=area name
        """
        if item_name == SYSTEM_TOPIC_NAME:
            return True

        with create_database_session() as session:
            for area in session.query(Area).filter(Area.deleted == False).all():
                if area.id == item_id:
                    return True

        logger.warning(
            "MQTT topic '%s / %s' does not match any current area panel", item_name, item_id
        )
        return False

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

    def _handle_mqtt_command(self, panel_id, panel_name, arm_type, code):
        """
        Handle an arm/disarm command received from MQTT (Home Assistant).

        Runs on the MQTT client thread, so it must not use the database session of
        the monitoring thread. The access code identifies the user, without a valid
        code the command is dropped.

        System panel => panel_id=None, panel_name=system
        Area panel => panel_id=area id, panel_name=area name
        """
        if self._is_locked_out():
            logger.warning(
                "Rejected MQTT command for '%s': locked out after too many invalid codes",
                panel_name,
            )
            return

        if not code:
            return

        # publish arming state to the MQTT panels while the exit delay runs, so that Home Assistant
        # shows the correct state
        self.publish_arm_states(arming=True)

        # using a new session here
        # because the MQTT client thread cannot use the active session of the monitoring thread
        user_id = None
        with create_database_session() as session:
            user = get_user_with_access_code(session, code)
            if user:
                user_id = user.id

        if not user_id:
            logger.warning("Rejected MQTT command for '%s': invalid access code", panel_name)
            if self._register_code_failure():
                logger.error(
                    "Too many invalid access codes over MQTT, ignoring commands for %s minutes",
                    MQTT_LOCKOUT_SEC // 60,
                )

            # re-publish the current arm states to the MQTT panels, so that Home Assistant
            # does not show the wrong state after a failed command
            self.publish_arm_states()
            return

        if panel_name != SYSTEM_TOPIC_NAME and panel_id is None:
            logger.error(
                "Received MQTT command for unknown area '%s' with panel id '%s'",
                panel_name,
                panel_id,
            )
            return

        if arm_type == ARM_AWAY:
            command = MonitorArmAwayCommand(user_id=user_id, area_id=panel_id, use_delay=True)
        elif arm_type == ARM_STAY:
            command = MonitorArmStayCommand(user_id=user_id, area_id=panel_id, use_delay=True)
        elif arm_type == ARM_DISARM:
            command = MonitorDisarmCommand(user_id=user_id, area_id=panel_id)
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

    def publish_areas(self):
        """
        Publish the area configs and states to the MQTT panels.

        Based on the previously published topics, remove the state and configs of areas
        that were renamed or deleted.
        """
        previously_published_topics = self._published_topics

        self._published_topics = set()
        areas = self._db_session.execute(select(Area).filter(Area.deleted == False)).scalars().all()
        for area in areas:
            # in case of a single area, we don't need to publish the area config
            # the system is enough to show the arm state in Home Assistant
            if len(areas) > 1:
                self._mqtt_client.publish_area_config(area.id, area.name)
                self._mqtt_client.publish_area_state(area.id, area.name, area.arm_state)
                self._published_topics.add((area.id, area.name))
            send_area_state(area.serialized)

        self._mqtt_client.publish_system_config()
        self._mqtt_client.publish_system_state(get_arm_state(self._db_session))
        self._published_topics.add((None, SYSTEM_TOPIC_NAME))

        orphaned_topics = previously_published_topics - self._published_topics
        for area_id, area_name in orphaned_topics:
            logger.info(
                "Removing orphaned MQTT topic for area '%s' (id=%s) that was renamed or deleted",
                area_name,
                area_id,
            )
            self._mqtt_client.delete_area(area_id, area_name)

    def publish_arm_states(self, arming=False):
        """
        Publish only the current arm states of the MQTT panels.
        """
        areas = self._db_session.execute(select(Area).filter(Area.deleted == False)).scalars().all()
        for area in areas:
            # in case of a single area, we don't need to publish the area config
            # the system is enough to show the arm state in Home Assistant
            if len(areas) > 1:
                if arming:
                    self._mqtt_client.publish_area_arming(area.id, area.name)
                else:
                    self._mqtt_client.publish_area_state(area.id, area.name, area.arm_state)

            send_area_state(area.serialized)

        if arming:
            self._mqtt_client.publish_system_arming()
        else:
            self._mqtt_client.publish_system_state(get_arm_state(self._db_session))

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

    def change_area_arm(self, arm_type, area_id=None) -> bool:
        """
        Change the arm state of the given area.

        The MQTT panels are not updated here: whether the new state or arming has to be
        published depends on the exit delay, which is only known to the caller. See
        publish_arm_states(arming=False) and publish_arm_states(arming=True).

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
            self._db_session.execute(select(Area).filter(Area.deleted == False, Area.sensors.any()))
            .scalars()
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
        self._mqtt_client = None
        self._mqtt_lock = None
        self._db_session.close()
