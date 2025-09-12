
import logging
from os import environ

from constants import LOG_ADKEYPAD
from monitor.adapters import V2BoardPin, V3BoardPin
from monitor.adapters.keypads.wiegand import WiegandKeypad

logger = logging.getLogger(LOG_ADKEYPAD)

USE_SIMULATOR = environ.get("USE_SIMULATOR", "false").lower() == "true"

def get_wiegand_keypad(board_version = 0):
    if board_version == 0:
        board_version = int(environ.get("BOARD_VERSION", 0))

    if USE_SIMULATOR:
        logger.debug("Using WiegandKeypad in simulator mode")
        return WiegandKeypad(
            data0=0,
            data1=1,
            beeper=2,
        )

    if board_version == 2:
        logger.debug("Using WiegandKeypad for board version 2")
        return WiegandKeypad(
            data0=V2BoardPin.KEYBUS_PIN0,
            data1=V2BoardPin.KEYBUS_PIN1,
            beeper=V2BoardPin.KEYBUS_PIN2,
        )
    elif board_version == 3:
        logger.debug("Using WiegandKeypad for board version 3")
        return WiegandKeypad(
            data0=V3BoardPin.KEYBUS_PIN0,
            data1=V3BoardPin.KEYBUS_PIN1,
            beeper=V3BoardPin.KEYBUS_PIN2,
        )
