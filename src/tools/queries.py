import logging
from sqlalchemy.sql.expression import false, true

from sqlalchemy.sql.functions import func
from models import Sensor, User, Zone, hash_code

from constants import ARM_AWAY, ARM_STAY, LOG_MONITOR


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


def get_user_with_access_code(session, code) -> User:
    users = session.query(User).all()
    code_hash = hash_code(code)
    logger.debug("User access code %s/%s in %s", code, code_hash, [u.fourkey_code for u in users])
    return next(filter(lambda u: u.fourkey_code == code_hash, users), None)
