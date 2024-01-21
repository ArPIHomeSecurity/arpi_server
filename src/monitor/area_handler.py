import logging

from constants import ARM_DISARM, ARM_MIXED, LOG_MONITOR
from models import Area
from monitor.communication.mqtt import MQTTClient
from monitor.database import Session
from monitor.socket_io import send_area_state


class AreaHandler:
    def __init__(self, session):
        self._logger = logging.getLogger(LOG_MONITOR)
        self._db_session = session

        self._mqtt_client = MQTTClient()
        self._mqtt_client.connect(client_id="arpi_area")
        self._logger.debug("AreaHandler initialized")

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

        area.arm_state = arm_type
        self._mqtt_client.publish_area_state(area.name, area.arm_state)
        send_area_state(area.serialized)
        self._db_session.commit()

    def are_areas_mixed_state(self) -> bool:
        """
        Check if there are areas with more than one state.
        """
        count = (
            self._db_session.query(Area.arm_state)
            .filter(Area.arm_state != ARM_DISARM)
            .filter(Area.deleted == False)
            .distinct(Area.arm_state)
            .count()
        )
        self._logger.debug("Are areas mixed state %s", count > 1)
        return count > 1

    def get_areas_state(self):
        """
        Get the state of the areas.
        """
        if self.are_areas_mixed_state():
            self._logger.debug("Areas state %s", ARM_MIXED)
            return ARM_MIXED

        state = self._db_session.query(Area).distinct(Area.arm_state).first().arm_state
        self._logger.debug("Areas state %s", state)
        return state

    def change_areas_arm(self, arm_type):
        """
        Change the arm state of all the areas.
        Skip deleted areas or areas without a sensor.
        """
        self._logger.info("Arming areas to %s", arm_type)
        self._db_session.query(Area).filter(Area.deleted == False).filter(
            Area.sensors.any()
        ).update({"arm_state": arm_type})
        self._db_session.commit()

        self.publish_areas()
