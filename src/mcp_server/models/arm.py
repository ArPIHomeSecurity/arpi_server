from enum import Enum


class ArmType(str, Enum):
    """
    The types of arming for the monitoring system or areas.
    """

    ARM_AWAY = "arm_away"
    ARM_STAY = "arm_stay"


class ArmState(str, Enum):
    """
    The arm states of the monitoring system.
    """

    ARMED_AWAY = "arm_away"
    ARMED_STAY = "arm_stay"
    ARM_MIXED = "arm_mixed"
    DISARM = "disarm"


class AreaArmState(str, Enum):
    """
    The arm states of an area in the monitoring system.
    """

    ARMED_AWAY = "armed_away"
    ARMED_STAY = "armed_stay"
    DISARM = "disarm"
