import atexit
import logging
import os
from signal import SIGTERM, Signals, signal
from threading import Event

from monitor.background_service import BackgroundService
from monitor.logging import initialize_logging
from monitor.socket_io import socketio_app
from tools.ssh_service import SSHService
from utils.constants import LOG_SERVICE

stop_event = Event()
logger = logging.getLogger(LOG_SERVICE)

background_service = None


def signal_term_handler(signal_number, frame):
    logger.debug("Received signal (%s)", Signals(signal_number).name)
    stop_background_service()


def start_background_service():
    global background_service
    logger.debug("Starting background service")
    signal(SIGTERM, signal_term_handler)

    if background_service is not None:
        logger.error("Background service is already running")
        return

    background_service = BackgroundService(stop_event)

    if os.environ.get("USE_SSH_CONNECTION", "true").lower() == "true":
        SSHService().update_service_state()

    background_service.start()


def stop_background_service():
    global background_service
    logger.debug("Stopping background service")
    stop_event.set()

    # check if the background service is running
    if background_service and background_service.is_alive():
        background_service.join()
        logger.debug("Background service stopped")
        background_service = None
        stop_event.clear()


def create_app():
    initialize_logging()
    start_background_service()
    atexit.register(stop_background_service)
    return socketio_app
