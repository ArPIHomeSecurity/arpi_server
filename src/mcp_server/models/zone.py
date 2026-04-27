from enum import Enum
from utils.constants import ARM_AWAY, ARM_DISARM, ARM_STAY, ARM_MIXED


class ArmType(str, Enum):
    """
    Arm types for zones.
    """

    STAY = ARM_STAY
    AWAY = ARM_AWAY
    ARM_MIXED = ARM_MIXED
    DISARM = ARM_DISARM
