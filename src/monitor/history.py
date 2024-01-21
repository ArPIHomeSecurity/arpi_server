import logging

from constants import LOG_MONITOR


class SensorHistory:
    """
    Keeps track of the last N states of a sensor and returns whether the sensor
    is alarming or not according to a given threshold.
    """

    # defaults for immediate alerting as normal behaviour
    DEFAULT_THRESHOLD = 100
    DEFAULT_SIZE = 1

    def __init__(self, size=DEFAULT_SIZE, threshold=DEFAULT_THRESHOLD):
        if 0 > threshold > 100:
            raise ValueError("Threshold must be between 0 and 100")
        self._threshold = threshold
        if size < 1:
            raise ValueError("Size must be greater than 0")
        self._size = size
        self._states = [False for _ in range(size)]

    def add(self, state):
        self._states.append(state)
        if len(self._states) > self._size:
            self._states.pop(0)

    def get_states(self):
        return self._states

    def alert_states_length(self):
        return len([e for e in self._states if e])

    def alert_above_threshold(self):
        """
        Checks if the percentage of alert states is above the threshold.

        Returns:
            bool: True if the percentage of alert states is above the threshold, False otherwise.
        """
        return (self.alert_states_length() / len(self._states)) * 100 >= self._threshold


class SensorsHistory:
    """
    Tracking the history of N sensors.
    """

    def __init__(self, sensor_count, size, threshold) -> None:
        self._sensors = [SensorHistory(size, threshold) for _ in range(sensor_count)]
        self._logger = logging.getLogger(LOG_MONITOR)

    def add_state(self, idx, state):
        if idx >= len(self._sensors):
            raise ValueError(f"Invalid sensor index {idx}")
        self._sensors[idx].add(state)

    def is_sensor_alerting(self, idx):
        if idx >= len(self._sensors):
            raise ValueError(f"Invalid sensor index {idx}")
        return self._sensors[idx].alert_above_threshold()

    def has_sensor_any_alert(self, idx):
        if idx >= len(self._sensors):
            raise ValueError(f"Invalid sensor index {idx}")
        return any(self._sensors[idx].get_states())

    def add_states(self, states):
        if len(states) != len(self._sensors):
            self._logger.error(
                "Invalid number of states! %s != %s", len(states), len(self._sensors)
            )
            return

        for idx, sensor in enumerate(self._sensors):
            sensor.add(states[idx])
