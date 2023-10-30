import logging
import os

from threading import Event
from signal import SIGTERM, signal, Signals

from constants import LOG_SERVICE
from monitor.background_service import BackgroundService
from monitor.socket_io import socketio_app
from tools.ssh import SSH


stop_event = Event()
logger = logging.getLogger(LOG_SERVICE)


def signal_term_handler(signal_number, frame):
    logger.debug("Received signal (%s)", Signals(signal_number).name)
    stop_background_service(remove_app=False)


def start_background_service():
    logger.debug("Starting background service")
    signal(SIGTERM, signal_term_handler)

    # thread safe lock for starting the application only once
    if os.environ.get("MONITOR_RUNNING", "false").lower() == "true":
        return

    if os.environ.get("USE_SSH_CONNECTION", "true").lower() == "true":
        SSH().update_ssh_service()

    service = BackgroundService(stop_event)
    service.start()
    os.environ["MONITOR_RUNNING"] = "true"


def stop_background_service(remove_app=True):
    logger.debug("Stopping background service")
    stop_event.set()
    if remove_app:
        global socketio_app
        if socketio_app:
            print(socketio_app.wsgi_app.wsgi_app.__dict__)
            del socketio_app


def create_app():
    start_background_service()
    return socketio_app


if __name__ == "__main__":
    start_background_service()
    socketio_app.run(threaded=True, port=8081, use_reloader=False, debug=True)
