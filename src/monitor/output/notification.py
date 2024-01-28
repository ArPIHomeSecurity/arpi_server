"""
This module contains the Notification class, which represents a notification for an output.
"""

from dataclasses import dataclass
from enum import Enum


class EventType(Enum):
    """
    The type of event that is triggered.
    """

    STOP = 0
    START = 1


class TriggerSource(Enum):
    """
    The source of the event that is triggered.
    """

    AREA = 0
    SYSTEM = 1
    BUTTON = 2


@dataclass
class Notification:
    """
    Represents a notification for an output.
    """

    type: TriggerSource
    state: EventType
    area_id: int = None
    output_id: int = None

    def __str__(self):
        return (
            "Notification("
            f"type={self.type}, "
            f"state={self.state}, "
            f"area_id={self.area_id}, "
            f"output_id={self.output_id}"
            ")"
        )
