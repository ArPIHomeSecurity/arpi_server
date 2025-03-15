import logging
import os
from typing import List

from constants import LOG_MONITOR
from monitor.config_helper import AlertSensitivityConfig


class SensorHistory:
    """
    Keeps track of the last N states of a sensor and returns whether the sensor
    is alarming or not according to a given threshold.
    """

    def __init__(self, size, threshold):
        if 0 > threshold > 100:
            raise ValueError("Threshold must be between 0 and 100")
        self._threshold = threshold
        if size < 1:
            raise ValueError("Size must be greater than 0")
        self._size = size
        self._states = [False for _ in range(size)]

    def set_sensitivity(self, size: int, threshold: int):
        """
        Set the monitoring parameters for the sensor history.

        Args:
            size (int): The number of states to keep in the history.
            threshold (int): The percentage of alert states to consider the sensor alerting.
        """
        if 0 > threshold > 100:
            raise ValueError("Threshold must be between 0 and 100")
        self._threshold = threshold
        if size < 1:
            raise ValueError("Size must be greater than 0")
        self._size = size
        self._states = [False for _ in range(size)]

    def add_state(self, state: bool):
        """
        Adds the given state to the sensor history.

        Args:
            state (bool): The state to add to the history.
        """
        self._states.append(state)
        if len(self._states) > self._size:
            self._states.pop(0)

    def get_states(self) -> List[bool]:
        """
        Returns the states of the sensor history.

        Returns:
            List[bool]: The states of the sensor history.
        """
        return self._states

    def alert_states_length(self) -> int:
        """
        Returns the number of alert states in the history.

        Returns:
            int: The number of alert states in the history.
        """
        return len([e for e in self._states if e])

    def alert_above_threshold(self) -> bool:
        """
        Checks if the percentage of alert states is above the threshold.

        Returns:
            bool: True if the percentage of alert states is above the threshold, False otherwise.
        """
        return (self.alert_states_length() / len(self._states)) * 100 >= self._threshold

    def get_sensitivity(self) -> AlertSensitivityConfig:
        """
        Returns the sensitivity configuration of the sensor history.

        Returns:
            AlertSensitivityConfig: The sensitivity configuration of the sensor history.
        """
        sample_rate = int(os.environ["SAMPLE_RATE"])
        period = int(self._size / sample_rate)
        if sample_rate == 1:
            period = None
        if period == 0:
            period = None
        return AlertSensitivityConfig(period, self._threshold)


class SensorsHistory:
    """
    Tracking the history of N sensors.
    """

    DEFAULT_SIZE = 1
    DEFAULT_THRESHOLD = 100

    def __init__(self, sensor_count, size=DEFAULT_SIZE, threshold=DEFAULT_THRESHOLD) -> None:
        self._sensors: List[SensorHistory] = [
            SensorHistory(size, threshold) for _ in range(sensor_count)
        ]
        self._logger = logging.getLogger(LOG_MONITOR)

    def set_sensitivity(self, idx: int, size: int, threshold: int):
        """
        Set the monitoring parameters for the sensor at the given index.

        Args:
            idx (int): The index of the sensor.
            size (int): The number of states to keep in the history.
            threshold (int): The percentage of alert states to consider the sensor alerting.
        """
        if idx >= len(self._sensors):
            raise ValueError(f"Invalid sensor index {idx}")
        self._sensors[idx].set_sensitivity(size, threshold)

    def add_state(self, idx: int, state: bool):
        """
        Adds the given state to the sensor at the given index.

        Args:
            idx (int): The index of the sensor.
            state (bool): The state to add to the sensor.
        """
        if idx >= len(self._sensors):
            raise ValueError(f"Invalid sensor index {idx}")
        self._sensors[idx].add_state(state)

    def is_sensor_alerting(self, idx) -> bool:
        """
        Checks if the sensor at the given index is alerting.

        Args:
            idx (int): The index of the sensor.
        Returns:
            bool: True if the sensor is alerting, False otherwise.
        """
        if idx >= len(self._sensors):
            raise ValueError(f"Invalid sensor index {idx}")
        return self._sensors[idx].alert_above_threshold()

    def has_sensor_any_alert(self, idx) -> bool:
        """
        Checks if the sensor at the given index has any alert state.
        (May be still below the threshold but has some alert states)

        Args:
            idx (int): The index of the sensor.
        Returns:
            bool: True if the sensor has any alert state, False otherwise.
        """
        if idx >= len(self._sensors):
            raise ValueError(f"Invalid sensor index {idx}")
        return any(self._sensors[idx].get_states())

    def add_states(self, states: List[bool]):
        """
        Adds the given states to the sensors.

        Args:
            states (List[bool]): The states to add to the sensors.
        """
        if len(states) != len(self._sensors):
            self._logger.error(
                "Invalid number of states! %s != %s", len(states), len(self._sensors)
            )
            return

        for idx, sensor in enumerate(self._sensors):
            sensor.add_state(states[idx])

    def get_states(self, idx) -> List[bool]:
        """
        Returns the states of the sensor at the given index.

        Args:
            idx (int): The index of the sensor.
        Returns:
            List[bool]: The states of the sensor.
        """
        if idx >= len(self._sensors):
            return []
        return self._sensors[idx].get_states()

    def get_sensitivity(self, idx) -> AlertSensitivityConfig:
        """
        Returns the sensitivity configuration of the sensor at the given index.

        Args:
            idx (int): The index of the sensor.
        Returns:
            AlertSensitivityConfig: The sensitivity configuration of the sensor.
        """
        if idx >= len(self._sensors):
            return None
        return self._sensors[idx].get_sensitivity()
