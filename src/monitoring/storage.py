# @Description: In memory storage for communicating between components
# TODO: make it thread safe???

_data = {}

ARM_STATE = 0
MONITORING_STATE = 1
POWER_STATE = 2


def get(key):
    return _data.get(key, None)


def set(key, value):
    _data[key] = value
