"""
Control the outputs
"""
# pylint: disable=import-outside-toplevel

import logging
from os import environ
from constants import LOG_ADOUTPUT
from monitor.adapters.output_base import OutputAdapterBase

from monitor.adapters import (
    CLOCK_PIN_V2,
    CLOCK_PIN_V3,
    DATA_IN_PIN_V2,
    DATA_IN_PIN_V3,
    DATA_OUT_PIN_V2,
    DATA_OUT_PIN_V3,
    ENABLE_PIN_V2,
    ENABLE_PIN_V3,
    LATCH_PIN_V2,
    LATCH_PIN_V3,
)

logger = logging.getLogger(LOG_ADOUTPUT)

USE_SIMULATOR = environ.get("USE_SIMULATOR", "false").lower() == "true"


def get_output_adapter(board_version: int = 0) -> OutputAdapterBase:
    """
    Get the appropriate output adapter based on the board version and
    simulation mode.
    """
    if USE_SIMULATOR:
        from monitor.adapters.mock.output import OutputAdapter as MockOutputAdapter
        return MockOutputAdapter()
    else:
        from monitor.adapters.output_v2 import OutputAdapter as OutputAdapterV2
        from monitor.adapters.output_v3 import OutputAdapter as OutputAdapterV3

        if board_version == 0:
            board_version = int(environ["BOARD_VERSION"])

        if board_version == 2:
            logger.debug("Using OutputAdapterV2")
            return OutputAdapterV2(
                latch_pin=LATCH_PIN_V2,
                enable_pin=ENABLE_PIN_V2,
                clock_pin=CLOCK_PIN_V2,
                data_in_pin=DATA_IN_PIN_V2,
                data_out_pin=DATA_OUT_PIN_V2,
            )
        if board_version == 3:
            logger.debug("Using OutputAdapterV3")
            return OutputAdapterV3(
                latch_pin=LATCH_PIN_V3,
                enable_pin=ENABLE_PIN_V3,
                clock_pin=CLOCK_PIN_V3,
                data_in_pin=DATA_IN_PIN_V3,
                data_out_pin=DATA_OUT_PIN_V3,
            )
        raise ValueError(f"Unsupported board version: {board_version}")
