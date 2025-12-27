# pylint: disable=import-outside-toplevel

import logging
from os import environ

from utils.constants import LOG_ADPOWER
from monitor.adapters.power_base import PowerAdapterBase


USE_SIMULATOR = environ.get("USE_SIMULATOR", "false").lower() in ["true", "1", "yes"]
logger = logging.getLogger(LOG_ADPOWER)


def get_power_adapter(board_version: int = 0) -> PowerAdapterBase:
    """
    Get the appropriate sensor adapter based on the board version and
    simulation mode.
    """
    if USE_SIMULATOR:
        from monitor.adapters.mock.power import PowerAdapter

        return PowerAdapter()
    else:
        from monitor.adapters.power_v2 import PowerAdapter as PowerAdapterV2
        from monitor.adapters.power_v3 import PowerAdapter as PowerAdapterV3

        if board_version == 0:
            board_version = int(environ["BOARD_VERSION"])

        if board_version == 2:
            logger.debug(f"Using PowerAdapterV{board_version}")
            return PowerAdapterV2()
        elif board_version == 3:
            logger.debug(f"Using PowerAdapterV{board_version}")
            return PowerAdapterV3()
        else:
            raise ValueError(f"Unsupported board version: {board_version}")
