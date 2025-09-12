# pylint: disable=import-outside-toplevel

import logging
from os import environ

from constants import LOG_ADSENSOR

from .sensor_base import SensorAdapterBase

USE_SIMULATOR = environ.get("USE_SIMULATOR", "false").lower() in ["true", "1", "yes"]
logger = logging.getLogger(LOG_ADSENSOR)


def get_sensor_adapter(board_version: int = 0) -> SensorAdapterBase:
    """
    Get the appropriate sensor adapter based on the board version and
    simulation mode.
    """
    if USE_SIMULATOR:
        from monitor.adapters.mock.sensor import SensorAdapter

        return SensorAdapter()
    else:
        from .sensor_v2 import SensorAdapter as SensorAdapterV2
        from .sensor_v3 import SensorAdapter as SensorAdapterV3

        if board_version == 0:
            board_version = int(environ["BOARD_VERSION"])

        if board_version == 2:
            logger.debug("Using SensorAdapterV2")
            return SensorAdapterV2()
        elif board_version == 3:
            logger.debug("Using SensorAdapterV3")
            return SensorAdapterV3()
        else:
            raise ValueError(f"Unsupported board version: {board_version}")
