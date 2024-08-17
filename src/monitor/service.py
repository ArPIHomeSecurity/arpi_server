import atexit
import logging
import os

from threading import Event
from signal import SIGTERM, signal, Signals

from constants import LOG_SERVICE
from monitor.background_service import BackgroundService
from monitor.logging import initialize_logging
from monitor.socket_io import socketio_app
from tools.ssh_service import SSHService


stop_event = Event()
logger = logging.getLogger(LOG_SERVICE)

background_service = BackgroundService(stop_event)


def signal_term_handler(signal_number, frame):
    logger.debug("Received signal (%s)", Signals(signal_number).name)
    stop_background_service()


def start_background_service():
    logger.debug("Starting background service")
    signal(SIGTERM, signal_term_handler)

    # thread safe lock for starting the application only once
    if os.environ.get("MONITOR_RUNNING", "false").lower() == "true":
        return

    if os.environ.get("USE_SSH_CONNECTION", "true").lower() == "true":
        SSHService().update_service_state()

    background_service.start()
    os.environ["MONITOR_RUNNING"] = "true"


def stop_background_service():
    logger.debug("Stopping background service")
    stop_event.set()

    # check if the background service is running
    if background_service and background_service.is_alive():
        background_service.join()


def create_app():
    initialize_logging()
    start_background_service()
    atexit.register(stop_background_service)
    return socketio_app
