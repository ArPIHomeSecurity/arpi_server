import logging
from sqlalchemy.sql.expression import false, true

from sqlalchemy.sql.functions import func
from models import Sensor, Zone

from monitoring.constants import ARM_AWAY, ARM_STAY, LOG_MONITOR


logger = logging.getLogger(LOG_MONITOR)


def get_arm_delay(session, arm_type):
    if arm_type == ARM_AWAY:
        return session.query(
                func.max(Zone.away_arm_delay).label("max_delay")
            ).filter(Zone.deleted == false(), Zone.sensors.any(Sensor.enabled == true())) \
            .one() \
            .max_delay
    elif arm_type == ARM_STAY:
        return session.query(
                func.max(Zone.stay_arm_delay).label("max_delay")
            ).filter(Zone.deleted == false(), Zone.sensors.any(Sensor.enabled == true())) \
            .one() \
            .max_delay
    else:
        logger.error("Unknown arm type: %s", arm_type)


def get_alert_delay(session, arm_type):
    if arm_type == ARM_AWAY:
        return session.query(
                func.max(Zone.away_alert_delay).label("max_delay")
            ).filter(Zone.deleted == false(), Zone.sensors.any(Sensor.enabled == true())) \
            .one() \
            .max_delay
    elif arm_type == ARM_STAY:
        return session.query(
                func.max(Zone.stay_alert_delay).label("max_delay")
            ).filter(Zone.deleted == false(), Zone.sensors.any(Sensor.enabled == true())) \
            .one() \
            .max_delay
    else:
        logger.error("Unknown arm type: %s", arm_type)
