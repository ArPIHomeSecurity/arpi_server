import logging
import os
import sys
from multiprocessing import Queue
from signal import SIGTERM, signal
from threading import Event, Thread
from time import sleep

from monitoring.adapters.keypad import Keypad
from monitoring.constants import (LOG_SERVICE, LOGGING_MODULES, MONITOR_STOP,
                                  THREAD_SOCKETIO)
from monitoring.ipc import IPCServer
from monitoring.monitor import Monitor
from monitoring.notifications.notifier import Notifier
from monitoring.socket_io import start_socketio
from server.broadcast import Broadcaster


def initialize_logging():
    formatter = logging.Formatter('%(asctime)s-[%(threadName)10s|%(name)9s] %(levelname)5s: %(message)s')

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    file_handler = logging.FileHandler('monitoring.log')
    file_handler.setFormatter(formatter)

    for name, level in LOGGING_MODULES:
        logger = logging.getLogger(name)
        logger.setLevel(level)
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    logging.getLogger('SocketIOServer').setLevel(logging.INFO)
    logging.getLogger('gsmmodem.modem.GsmModem').setLevel(logging.ERROR)
    logging.getLogger('gsmmodem.serial_comms.SerialComms').setLevel(logging.ERROR)
    # logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)


def createPidFile():
    pid = str(os.getpid())
    f = open(os.environ['MONITOR_PID_FILE'], 'w')
    f.write(pid + "\n")
    f.close()


def start():
    createPidFile()
    initialize_logging()

    logger = logging.getLogger(LOG_SERVICE)

    monitor_actions = Queue()
    monitor = Monitor(monitor_actions)
    monitor.start()

    notifier_actions = Queue()
    Notifier._actions = notifier_actions
    notifier = Notifier()
    notifier.start()

    keypad_actions = Queue()
    keypad = Keypad(keypad_actions, monitor_actions)
    keypad.start()

    broadcaster = Broadcaster([monitor_actions, notifier_actions, keypad_actions])

    stop_event = Event()
    ipc_server = IPCServer(stop_event, broadcaster)
    ipc_server.start()

    def stop_service():
        logger.info("Stopping service...")
        broadcaster.send_message(MONITOR_STOP)
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
        sys.exit(0)

    def signal_term_handler(signal, frame):
        logger.debug('Received signal (SIGTERM)')
        stop_service()

    signal(SIGTERM, signal_term_handler)

    '''
    The main thread checks the health of the sub threads and crashes the application if any problem happens.
    If the application stops the service running system has to restart it clearly.

    May be later threads can be implemented safe to avoid restarting the application.
    '''
    while True:
        try:
            for thread in (monitor, ipc_server, notifier, keypad, socketio_server):
                if not thread.is_alive():
                    logger.error("Thread crashed: %s", thread.name)
                    stop_service()
            sleep(1)
        except KeyboardInterrupt:
            logger.info("Keyboard interruption!!!")
            break

    # start the socket IO server in the main thread
    try:
        start_socketio()
    except AssertionError:
        pass

    logger.info("Stopping main...")

    stop_service()


if __name__ == '__main__':
    start()
