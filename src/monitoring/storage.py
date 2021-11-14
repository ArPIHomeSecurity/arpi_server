# @Description: In memory storage for communicating between components
# TODO: make it thread safe???

from monitoring.socket_io import send_arm_state, send_system_state


_data = {}

ARM_STATE = 0
MONITORING_STATE = 1
POWER_STATE = 2


def get(key):
    return _data.get(key, None)


def set(key, value):
    _data[key] = value
    if key == MONITORING_STATE:
        send_system_state(value)
    elif key == ARM_STATE:
        send_arm_state(value)
