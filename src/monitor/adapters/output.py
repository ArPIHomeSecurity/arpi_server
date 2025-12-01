"""
Control the outputs
"""
# pylint: disable=import-outside-toplevel

import logging
from os import environ
from utils.constants import LOG_ADOUTPUT
from monitor.adapters.output_base import OutputAdapterBase

from monitor.adapters import V2BoardPin, V3BoardPin

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
                latch_pin=V2BoardPin.LATCH_PIN,
                enable_pin=V2BoardPin.ENABLE_PIN,
                clock_pin=V2BoardPin.CLOCK_PIN,
                data_in_pin=V2BoardPin.DATA_IN_PIN,
                data_out_pin=V2BoardPin.DATA_OUT_PIN,
            )
        if board_version == 3:
            logger.debug("Using OutputAdapterV3")
            return OutputAdapterV3(
                latch_pin=V3BoardPin.OUTPUT_LATCH_PIN,
                enable_pin=V3BoardPin.OUTPUT_ENABLE_PIN,
                clock_pin=V3BoardPin.OUTPUT_CLOCK_PIN,
                data_in_pin=V3BoardPin.OUTPUT_DATA_IN_PIN,
                data_out_pin=V3BoardPin.OUTPUT_DATA_OUT_PIN,
            )
        raise ValueError(f"Unsupported board version: {board_version}")
