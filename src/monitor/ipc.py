import contextlib
import json
import logging
from select import select
import socket
from os import chmod, chown, environ, makedirs, path, remove
from pwd import getpwnam
from grp import getgrnam
from threading import Event, Thread
from time import sleep

from constants import (
    DELETE_SMS_MESSAGE,
    GET_SMS_MESSAGES,
    LOG_IPC,
    MAKE_TEST_CALL,
    MONITOR_ACTIVATE_OUTPUT,
    MONITOR_ARM_AWAY,
    MONITOR_ARM_STAY,
    MONITOR_DEACTIVATE_OUTPUT,
    MONITOR_DISARM,
    MONITOR_GET_STATE,
    MONITOR_REGISTER_CARD,
    MONITOR_SET_CLOCK,
    MONITOR_SYNC_CLOCK,
    MONITOR_UPDATE_CONFIG,
    MONITOR_UPDATE_KEYPAD,
    POWER_GET_STATE,
    SEND_TEST_EMAIL,
    SEND_TEST_SMS,
    SEND_TEST_SYREN,
    THREAD_IPC,
    UPDATE_SECURE_CONNECTION,
    UPDATE_SSH,
)
from monitor.storage import State, States
from monitor.alert import Syren
from monitor.notifications.notifier import Notifier
from monitor.output.handler import OutputHandler
from tools.clock import Clock
from tools.ssh_service import SSHService

MONITOR_INPUT_SOCKET = environ["MONITOR_INPUT_SOCKET"]


class IPCServer(Thread):
    """
    Class for handling the actions from the server and executing them on monitoring.
    """

    BROADCASTED_ACTIONS = [
        MONITOR_ARM_AWAY,
        MONITOR_ARM_STAY,
        MONITOR_DISARM,
        MONITOR_UPDATE_CONFIG,
        MONITOR_UPDATE_KEYPAD,
        MONITOR_REGISTER_CARD,
        UPDATE_SECURE_CONNECTION,
    ]

    def __init__(self, stop_event: Event, broadcaster):
        """
        Constructor
        """
        super(IPCServer, self).__init__(name=THREAD_IPC)
        self._logger = logging.getLogger(LOG_IPC)
        self._stop_event = stop_event
        self._broadcaster = broadcaster
        self._initialize_socket()
        self._logger.info("IPC server created")

    def _initialize_socket(self):

        _socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        _socket.settimeout(60)
        _socket.setblocking(False)

        with contextlib.suppress(OSError):
            remove(MONITOR_INPUT_SOCKET)

        self.create_socket_file()
        _socket.bind(MONITOR_INPUT_SOCKET)
        _socket.listen(1)

        try:
            chmod(MONITOR_INPUT_SOCKET, int(environ["PERMISSIONS"], 8))
            chown(MONITOR_INPUT_SOCKET, getpwnam(environ["USERNAME"]).pw_uid, getgrnam(environ["GROUPNAME"]).gr_gid)
            self._logger.info("Socket permissions fixed")
        except KeyError as error:
            self._logger.error("Failed to fix permission and/or owner!")
            self._logger.debug("Error: %s", error)

        self._sockets = [_socket]

    def create_socket_file(self):
        """
        Create the socket file for the IPC server to listen to.
        """
        filename = MONITOR_INPUT_SOCKET
        if not path.exists(path.dirname(filename)):
            self._logger.debug("Create socket file: %s", MONITOR_INPUT_SOCKET)
            makedirs(path.dirname(filename))
            with open(MONITOR_INPUT_SOCKET, "w", encoding="utf-8"):
                pass
            self._logger.debug("Create socket file: %s", MONITOR_INPUT_SOCKET)

    def run(self):
        self._logger.info("IPC server started")

        try:
            self.communicate()
        except Exception:
            self._logger.exception("IPC server crashed!")

        self._logger.info("IPC server stopped")

    def communicate(self):
        """
        Communicate with the clients.
        """
        # read all the messages
        while not self._stop_event.is_set():

            self._logger.trace("Waiting for connection...")
            readable, _, exceptional = select(self._sockets, [], self._sockets, 1)

            for read_socket in readable:
                if read_socket is self._sockets[0]:
                    connection, _ = self._sockets[0].accept()
                    self._sockets.append(connection)
                else:
                    self.process_data(read_socket)

            for exc_socket in exceptional:
                self._logger.error("Exceptional socket: %s", exc_socket)
                self._sockets.remove(exc_socket)
                exc_socket.close()

        with contextlib.suppress(FileNotFoundError):
            remove(MONITOR_INPUT_SOCKET)

    def process_data(self, connection):
        """
        Process the data received from the client and send the response.
        """
        try:
            data = connection.recv(1024)
        except ConnectionResetError as error:
            self._logger.error("Connection reset: %s", error)
            return

        if not data:
            self._logger.debug("No data received")
            self._sockets.remove(connection)
            connection.close()
            return

        self._logger.debug("Received action: '%s'", data)

        response = self.handle_actions(json.loads(data.decode()))

        try:
            connection.send(json.dumps(response).encode())
        except BrokenPipeError:
            self._sockets.remove(connection)
            connection.close()

    def handle_actions(self, message):
        """
        Return value:
        {
            "result": boolean, # True if succeeded
            "message": string, # Error message
            "value: dict # value to return
        }
        """
        return_value = {"result": True}
        if message["action"] in self.BROADCASTED_ACTIONS:
            # broadcast message
            self._logger.info("IPC action received: %s", message["action"])
            self._broadcaster.send_message(message=message)
        elif message["action"] == MONITOR_GET_STATE:
            return_value["value"] = {"state": States.get(State.MONITORING)}
        elif message["action"] == POWER_GET_STATE:
            return_value["value"] = {"state": States.get(State.POWER)}
        elif message["action"] == UPDATE_SSH:
            self._logger.info("Update ssh connection...")
            ssh = SSHService()
            ssh.update_service_state()
            ssh.update_access_local_network()
            ssh.update_password_authentication()
        elif message["action"] == SEND_TEST_SMS:
            succeeded, results = Notifier.send_test_sms()
            return_value["result"] = succeeded
            return_value["message"] = "Error in SMS sending!" if not succeeded else ""
            return_value["other"] = results
        elif message["action"] == GET_SMS_MESSAGES:
            result, messages = Notifier.get_sms_messages()
            return_value["result"] = result
            return_value["value"] = messages
        elif message["action"] == DELETE_SMS_MESSAGE:
            result = Notifier.delete_sms_message(message["message_id"])
            return_value["result"] = result
        elif message["action"] == SEND_TEST_EMAIL:
            succeeded, results = Notifier.send_test_email()
            return_value["result"] = succeeded
            return_value["message"] = "Error in email sending!" if not succeeded else ""
            return_value["other"] = results
        elif message["action"] == MAKE_TEST_CALL:
            succeeded, results = Notifier.make_test_call()
            return_value["result"] = succeeded
            return_value["message"] = "Error in call sending!" if not succeeded else ""
            return_value["other"] = results
        elif message["action"] == SEND_TEST_SYREN:
            self.test_syren(message["duration"])
        elif message["action"] == MONITOR_SYNC_CLOCK:
            if not Clock().sync_clock():
                return_value["result"] = False
                return_value["message"] = "Failed to sync time"
        elif message["action"] == MONITOR_SET_CLOCK:
            if not Clock().set_clock(message):
                return_value["result"] = False
                return_value["message"] = "Failed to update date/time and zone"
        elif message["action"] == MONITOR_ACTIVATE_OUTPUT:
            OutputHandler.send_button_pressed(message["output_id"])
        elif message["action"] == MONITOR_DEACTIVATE_OUTPUT:
            OutputHandler.send_button_released(message["output_id"])
        else:
            return_value["result"] = False
            return_value["message"] = f"Unknown command: {message}"

        return return_value

    def test_syren(self, duration=5):
        """
        Test syren for a given duration.
        """
        self._logger.debug("Testing syren %ss...", duration)
        Syren.start_syren(silent=False, delay=0, duration=duration)
        sleep(duration)
        Syren.stop_syren()
