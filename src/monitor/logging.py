import logging
import os
import sys

from constants import LOGGING_MODULES, TRACE
from monitor.logger import ArgusLogger
from utils.formatter import NotTooLongStringFormatter


def initialize_logging():
    """
    Initialize logging for the application
    """
    if os.environ.get("FLASK_ENV") == "development":
        formatter = NotTooLongStringFormatter(
            "%(asctime)s-[%(threadName)11s|%(name)9s] %(levelname)5s: %(message)s",
            ["threadName"],
            11,
        )
    else:
        formatter = NotTooLongStringFormatter(
            "[%(threadName)11s|%(name)9s] %(levelname)5s: %(message)s", ["threadName"], 11
        )

    logging.addLevelName(TRACE, "TRACE")

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(TRACE)

    file_handler = None
    if os.environ.get("OUTPUT_PATH"):
        file_handler = logging.FileHandler(os.environ["OUTPUT_PATH"])
        file_handler.setFormatter(formatter)


    for name, level in LOGGING_MODULES:
        logger = logging.getLogger(name)
        logger.__class__ = ArgusLogger
        logger.setLevel(level)
        logger.handlers.clear()
        logger.addHandler(console_handler)
        if file_handler:
            logger.addHandler(file_handler)

    os.environ["LOGGING_INITIALIZED"] = "true"


def print_logging():
    """
    Helper for debugging logging
    """
    rootlogger = logging.getLogger()
    for h in rootlogger.handlers:
        if h.formatter and h.formatter._fmt.startswith("%(levelname)s"):
            print(
                "Loggers: name=%s, h=%s, fmt=%s"
                % (rootlogger.name, h, h.formatter._fmt if h.formatter else None)
            )

    # get list of all logger, the handler of the loggers and their formatter
    for logger_name in logging.root.manager.loggerDict:
        logger = logging.getLogger(logger_name)
        if len(logger.handlers) > 1:
            print("Logger: ", logger_name, logger.level, len(logger.handlers))
        for handler in logger.handlers:
            if handler.formatter and handler.formatter._fmt.startswith("%(levelname)s"):
                print(
                    "Handler: name=%s level=%s, h=%s, fmt=%s"
                    % (
                        logger_name,
                        logger.level,
                        handler,
                        handler.formatter._fmt if handler.formatter else None,
                    )
                )
