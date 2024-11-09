"""
Manage areas
"""

import logging

from sqlalchemy import select

from constants import (
    ARM_AWAY,
    ARM_DISARM,
    ARM_STAY,
    LOG_MONITOR,
    MONITORING_READY,
    MONITORING_STARTUP,
    MONITORING_UPDATING_CONFIG,
)
from models import Area
from monitor.communication.mqtt import MQTTClient
from monitor.output.handler import OutputHandler
from monitor.socket_io import send_area_state
from monitor.storage import State, States


class AreaHandler:
    """
    Class for managing areas
    """

    def __init__(self, session):
        self._logger = logging.getLogger(LOG_MONITOR)
        self._db_session = session

        self._mqtt_client = MQTTClient()
        self._mqtt_client.connect(client_id="arpi_area")
        self._logger.debug("AreaHandler initialized")

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
        for area in self._db_session.execute(
            select(Area).filter(Area.deleted == False)
        ).scalars().all():
            if monitoring_state in disarmed_states and area.arm_state != ARM_DISARM:
                area.arm_state = ARM_DISARM
                self._logger.info("Area '%s' restored to disarmed state", area.name)

            send_area_state(area.serialized)

        self._db_session.commit()

    def publish_areas(self):
        """
        Load all the areas from the database.
        """
        areas = self._db_session.query(Area).all()

        for area in areas:
            if not area.deleted:
                self._mqtt_client.publish_area_config(area.name)
                self._mqtt_client.publish_area_state(area.name, area.arm_state)
                send_area_state(area.serialized)
            else:
                self._mqtt_client.delete_area(area.name)

    def change_area_arm(self, arm_type, area_id=None):
        """
        Change the arm state of the given area.
        """
        self._logger.info("Arming area: %s to %s", area_id, arm_type)
        area = self._db_session.query(Area).get(area_id)
        if area is None and not area.deleted:
            self._logger.error("Area not found or deleted")
            return

        if area.sensors == []:
            self._logger.error("Area has no sensors")
            return

        # update output channel
        if arm_type in (ARM_AWAY, ARM_STAY):
            OutputHandler.send_area_armed(area)
        elif arm_type == ARM_DISARM:
            OutputHandler.send_area_disarmed(area)

        area.arm_state = arm_type
        self._mqtt_client.publish_area_state(area.name, area.arm_state)
        send_area_state(area.serialized)
        self._db_session.commit()

    def change_areas_arm(self, arm_type):
        """
        Change the arm state of all the areas.
        Skip deleted areas or areas without a sensor.
        """
        self._logger.info("Arming areas to %s", arm_type)
        areas = (
            self._db_session.query(Area).filter(Area.deleted == False).filter(Area.sensors.any())
        )

        for area in areas:
            area.update({"arm_state": arm_type})
            # update output channel
            if arm_type in (ARM_AWAY, ARM_STAY):
                OutputHandler.send_area_armed(area)
            elif arm_type == ARM_DISARM:
                OutputHandler.send_area_disarmed(area)

        self._db_session.commit()

        self.publish_areas()

    def close(self):
        """
        Close the area handler.
        """
        self._logger.debug("Closing MQTT client...")
        self._mqtt_client.close()
