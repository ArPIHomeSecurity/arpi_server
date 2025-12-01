import logging
from sqlalchemy import distinct, inspect
from sqlalchemy.sql.expression import false, true

from sqlalchemy.sql.functions import func
from sqlalchemy.future import select
from utils.models import Area, Sensor, User, Zone

from utils.constants import ARM_AWAY, ARM_DISARM, ARM_MIXED, ARM_STAY, LOG_MONITOR


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
    for tmp_user in users:
        if tmp_user.check_access_code(code):
            state = inspect(tmp_user)
            if state.modified:
                session.commit()

            return tmp_user


def get_arm_state(session):
    """
    Get the state of the areas.
    """
    count = (
        session.execute(
            select(func.count(distinct(Area.arm_state)))
            .select_from(Area)
            .where(Area.arm_state != ARM_DISARM)
            .where(Area.deleted == False)
        ).scalar_one()
    )
    logger.debug("Are areas mixed state %s", count)

    if count > 1:
        logger.debug("Areas state %s", ARM_MIXED)
        return ARM_MIXED

    state = session.execute(
        select(Area.arm_state)
        .where(Area.deleted == False)
        .distinct(Area.arm_state)
    ).first().arm_state

    logger.debug("Areas state %s", state)
    return state
