# @Description: In memory storage for communicating between components

from threading import Lock

from monitoring.socket_io import send_arm_state, send_system_state


class States:
    """Class for storing state information"""
    _data = {}
    lock = Lock()

    ARM_STATE = 0
    MONITORING_STATE = 1
    POWER_STATE = 2

    def __new__(cls):
        if not hasattr(cls, 'instance'):
            cls.instance = super(States, cls).__new__(cls)
        return cls.instance

    @classmethod
    def get(cls, key):
        """
        Get the current states of the system
        """
        with cls.lock:
            return cls._data.get(key, None)

    @classmethod
    def set(cls, key, value):
        """
        Set the current state of the system
        """
        with cls.lock:
            cls._data[key] = value
            if key == cls.MONITORING_STATE:
                send_system_state(value)
            elif key == cls.ARM_STATE:
                send_arm_state(value)
