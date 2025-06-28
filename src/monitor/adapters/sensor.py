import logging

from constants import LOG_ADSENSOR

from .sensor_base import BaseSensorAdapter
from .sensor_v2 import SensorAdapterV2
from .sensor_v3 import SensorAdapterV3


def get_sensor_adapter(board_version: int) -> BaseSensorAdapter:
    if board_version == 2:
        logging.getLogger(LOG_ADSENSOR).debug("Using SensorAdapterV2")
        return SensorAdapterV2()
    elif board_version == 3:
        logging.getLogger(LOG_ADSENSOR).debug("Using SensorAdapterV3")
        return SensorAdapterV3()
    else:
        raise ValueError(f"Unsupported board version: {board_version}")
