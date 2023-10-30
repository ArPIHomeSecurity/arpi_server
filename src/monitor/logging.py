import logging
import os
import sys

from constants import LOGGING_MODULES
from tools.formatter import NotTooLongStringFormatter


def initialize_logging():
    """
    Initialize logging for the application
    """
    formatter = NotTooLongStringFormatter(
        "%(asctime)s-[%(threadName)11s|%(name)9s] %(levelname)5s: %(message)s",
        ["threadName"],
        11
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.DEBUG)

    # file_handler = logging.FileHandler("monitoring.log")
    # file_handler.setFormatter(formatter)

    for name, level in LOGGING_MODULES:
        logger = logging.getLogger(name)
        logger.setLevel(level)
        logger.handlers.clear()
        # logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    logging.getLogger("SocketIOServer").setLevel(logging.INFO)
    logging.getLogger("gsmmodem.modem.GsmModem").setLevel(logging.ERROR)
    logging.getLogger("gsmmodem.serial_comms.SerialComms").setLevel(logging.ERROR)
    # logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)

    os.environ["LOGGING_INITIALIZED"] = "true"


def print_logging():
    """
    Helper for debugging logging
    """
    rootlogger = logging.getLogger()
    for h in rootlogger.handlers:
        if h.formatter and h.formatter._fmt.startswith("%(levelname)s"):
            print("Loggers: name=%s, h=%s, fmt=%s" % (rootlogger.name, h, h.formatter._fmt if h.formatter else None))

    # get list of all logger, the handler of the loggers and their formatter
    for logger_name in logging.root.manager.loggerDict:
        logger = logging.getLogger(logger_name)
        if len(logger.handlers) > 1:
            print("Logger: ", logger_name, logger.level, len(logger.handlers))
        for handler in logger.handlers:
            if handler.formatter and handler.formatter._fmt.startswith("%(levelname)s"):
                print("Handler: name=%s level=%s, h=%s, fmt=%s" % (logger_name, logger.level, handler, handler.formatter._fmt if handler.formatter else None))
