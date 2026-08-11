import logging

from sqlalchemy import distinct, inspect
from sqlalchemy.future import select
from sqlalchemy.sql.expression import false, true
from sqlalchemy.sql.functions import func

from utils.constants import ARM_AWAY, ARM_DISARM, ARM_MIXED, ARM_STAY, LOG_MONITOR
from utils.models import Area, Sensor, User, Zone

logger = logging.getLogger(LOG_MONITOR)


def get_arm_delay(session, arm_type):
    if arm_type == ARM_AWAY:
        return (
            session.query(func.max(Zone.away_arm_delay).label("max_delay"))
            .filter(Zone.deleted == false(), Zone.sensors.any(Sensor.enabled == true()))
            .one()
            .max_delay
        )
    elif arm_type == ARM_STAY:
        return (
            session.query(func.max(Zone.stay_arm_delay).label("max_delay"))
            .filter(Zone.deleted == false(), Zone.sensors.any(Sensor.enabled == true()))
            .one()
            .max_delay
        )
    else:
        logger.error("Unknown arm type: %s", arm_type)


def get_alert_delay(session, arm_type):
    if arm_type == ARM_AWAY:
        return (
            session.query(func.max(Zone.away_alert_delay).label("max_delay"))
            .filter(Zone.deleted == false(), Zone.sensors.any(Sensor.enabled == true()))
            .one()
            .max_delay
        )
    elif arm_type == ARM_STAY:
        return (
            session.query(func.max(Zone.stay_alert_delay).label("max_delay"))
            .filter(Zone.deleted == false(), Zone.sensors.any(Sensor.enabled == true()))
            .one()
            .max_delay
        )
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


def get_arm_state(session) -> str:
    """
    Get the state of the areas.
    """
    count = session.execute(
        select(func.count(distinct(Area.arm_state)))
        .select_from(Area)
        .where(Area.arm_state != ARM_DISARM)
        .where(Area.deleted == False)
    ).scalar_one()
    logger.debug("Are areas mixed state %s", count)

    if count > 1:
        logger.debug("Areas state %s", ARM_MIXED)
        return ARM_MIXED

    # at most one armed state is left, so the query is unambiguous.
    # the disarmed areas have to stay excluded, otherwise DISTINCT ON would return
    # either the armed or the disarmed state depending on the row order.
    result = session.execute(
        select(Area.arm_state)
        .where(Area.arm_state != ARM_DISARM)
        .where(Area.deleted == False)
        .distinct(Area.arm_state)
    ).first()

    if result is None:
        state = ARM_DISARM
    else:
        state = result.arm_state

    logger.debug("Areas state %s", state)
    return state
