"""
Storage for the state of the system.

In memory storage with a file backup.
"""

from enum import Enum
import fcntl
import json
import logging
from threading import Lock
from typing import Optional

from constants import LOG_MONITOR
from monitor.socket_io import send_system_state


class State(Enum):
    """Enum for the type of the state"""
    MONITORING = "monitoring"
    POWER = "power"


class States:
    """
    Class for storing state information.
    """
    _data = None
    _lock = Lock()
    _logger = logging.getLogger(LOG_MONITOR)

    @classmethod
    def get(cls, key: State) -> Optional[any]:
        """
        Get the current states of the system
        """
        with cls._lock:
            if cls._data is None:
                cls._load()

            return cls._data.get(str(key), None)

    @classmethod
    def set(cls, key: State, value: any):
        """
        Set the current state of the system
        """
        with cls._lock:
            if cls._data is None:
                cls._load()

            cls._data[str(key)] = value  # pylint: disable=unsupported-assignment-operation
            if key == State.MONITORING:
                send_system_state(value)

            cls._save()

    @classmethod
    def _load(cls):
        """
        Open the storage
        """
        try:
            with open('status.json', "r+", encoding='utf-8') as status_file:
                fcntl.flock(status_file, fcntl.LOCK_EX)
                cls._data = json.load(status_file)
                fcntl.flock(status_file, fcntl.LOCK_UN)
        except (FileNotFoundError, json.JSONDecodeError):
            cls._data = {}

        for key in cls._data.keys():
            # pylint: disable=unsubscriptable-object
            cls._logger.debug("Data stored: %s: %s", key, cls._data[key])
            if key == State.MONITORING:
                send_system_state(cls._data[key])

        if not cls._data:
            cls._logger.debug("No data stored")

    @classmethod
    def _save(cls):
        """
        Save the current state of the system
        """
        if cls._data is not None:
            with open('status.json', 'w', encoding='utf-8') as status_file:
                fcntl.flock(status_file, fcntl.LOCK_EX)
                json.dump(cls._data, status_file, indent=4)
                fcntl.flock(status_file, fcntl.LOCK_UN)

    @classmethod
    def open(cls):
        """
        Open the storage
        """
        with cls._lock:
            cls._load()
            cls._logger.debug("Storage opened")

    @classmethod
    def close(cls):
        """
        Close the storage
        """
        with cls._lock:
            cls._save()
            cls._data = None
            cls._logger.debug("Storage closed")
