import logging
import os
from signal import SIGTERM, signal
from threading import Event
from time import sleep

from monitor.adapters.keypad import KeypadHandler
from monitor.broadcast import Broadcaster
from constants import LOG_SERVICE, LOGGING_MODULES, MONITOR_STOP
from monitor.ipc import IPCServer
from monitor.monitor import Monitor
from monitor.notifications.notifier import Notifier
from monitor.socket_io import start_socketio
from tools.ssh import SSH


def initialize_logging():
    formatter = logging.Formatter("%(asctime)s-[%(threadName)10s|%(name)9s] %(levelname)5s: %(message)s")

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    # file_handler = logging.FileHandler("monitoring.log")
    # file_handler.setFormatter(formatter)

    for name, level in LOGGING_MODULES:
        logger = logging.getLogger(name)
        logger.setLevel(level)
        # logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    logging.getLogger("SocketIOServer").setLevel(logging.INFO)
    logging.getLogger("gsmmodem.modem.GsmModem").setLevel(logging.ERROR)
    logging.getLogger("gsmmodem.serial_comms.SerialComms").setLevel(logging.ERROR)
    # logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)


def createPidFile():
    pid = str(os.getpid())
    with open(os.environ["MONITOR_PID_FILE"], "w") as f:
        f.write(pid + "\n")


def start():
    createPidFile()
    initialize_logging()
    SSH().update_ssh_service()

    logger = logging.getLogger(LOG_SERVICE)

    broadcaster = Broadcaster()

    monitor = Monitor(broadcaster)
    monitor.start()

    notifier = Notifier(broadcaster)
    notifier.start()

    keypad = KeypadHandler(broadcaster)
    keypad.start()

    stop_event = Event()
    ipc_server = IPCServer(stop_event, broadcaster)
    ipc_server.start()

    def stop_service():
        logger.info("Stopping service...")
        broadcaster.send_message(message={"action": MONITOR_STOP})
        stop_event.set()

        keypad.join()
        logger.debug("Keypad thread stopped")
        notifier.join()
        logger.debug("Notifier thread stopped")
        monitor.join()
        logger.debug("Monitor thread stopped")
        ipc_server.join()
        logger.debug("IPC thread stopped")
        logger.info("All threads stopped")
        os._exit(0)

    def signal_term_handler(signal, frame):
        logger.debug("Received signal (SIGTERM)")
        stop_service()

    signal(SIGTERM, signal_term_handler)

    start_socketio()

    """
    The main thread checks the health of the sub threads and crashes the application if any problem happens.
    If the application stops the service running system has to restart it clearly.

    May be later threads can be implemented safe to avoid restarting the application.
    """
    threads = (monitor, ipc_server, notifier, keypad)
    while True:
        try:
            logger.debug("Health check of threads: %s", [t.name for t in threads])
            for thread in threads:
                if not thread.is_alive():
                    logger.error("Thread crashed: %s", thread.name)
                    stop_service()
            sleep(1)
        except KeyboardInterrupt:
            logger.info("Keyboard interruption!!!")
            break

    stop_service()


if __name__ == "__main__":
    start()
