import json
import logging
import socket
from os import environ

from constants import (
    ARM_AWAY,
    ARM_STAY,
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
    UPDATE_SECURE_CONNECTION,
    UPDATE_SSH,
)


class IPCClient(object):
    """
    Sending IPC messages from the REST API to the monitoring service
    """

    MAX_RETRIES = 5
    _socket = None

    def __init__(self):
        self._logger = logging.getLogger(LOG_IPC)
        if not self._socket:
            self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                self._logger.info("Connecting to monitor socket: %s", environ["MONITOR_INPUT_SOCKET"])
                self._socket.connect(environ["MONITOR_INPUT_SOCKET"])
                self._socket.settimeout(60)
            except (ConnectionRefusedError, FileNotFoundError):
                self._logger.error("Failed to connect to monitor socket! %s", environ["MONITOR_INPUT_SOCKET"])
                self._socket = None

    @property
    def is_connected(self):
        return self._socket is not None

    def arm(self, arm_type, user_id, area_id=None):
        if arm_type == ARM_AWAY:
            return self._send_message({
                "action": MONITOR_ARM_AWAY,
                "user_id": user_id,
                "area_id": area_id,
                "delay": False
            })
        elif arm_type == ARM_STAY:
            return self._send_message({
                "action": MONITOR_ARM_STAY,
                "user_id": user_id,
                "area_id": area_id,
                "use_delay": False
            })
        else:
            print(f"Unknown arm type: {arm_type}")

    def disarm(self, user_id, area_id=None):
        return self._send_message({
            "action": MONITOR_DISARM,
            "user_id": user_id,
            "area_id": area_id
        })

    def get_state(self):
        return self._send_message({"action": MONITOR_GET_STATE})

    def get_power_state(self):
        return self._send_message({"action": POWER_GET_STATE})

    def update_configuration(self):
        return self._send_message({"action": MONITOR_UPDATE_CONFIG})

    def update_keypad(self):
        return self._send_message({"action": MONITOR_UPDATE_KEYPAD})

    def register_card(self):
        return self._send_message({"action": MONITOR_REGISTER_CARD})

    def update_dyndns(self):
        return self._send_message({"action": UPDATE_SECURE_CONNECTION})

    def update_ssh(self):
        return self._send_message({"action": UPDATE_SSH})

    def send_test_email(self):
        return self._send_message({"action": SEND_TEST_EMAIL})

    def send_test_sms(self):
        return self._send_message({"action": SEND_TEST_SMS})
    
    def get_sms_messages(self):
        return self._send_message({"action": GET_SMS_MESSAGES})
    
    def delete_sms_message(self, message_id):
        return self._send_message({"action": DELETE_SMS_MESSAGE, "message_id": message_id})

    def make_test_call(self):
        return self._send_message({"action": MAKE_TEST_CALL})

    def send_test_syren(self, duration):
        return self._send_message({"action": SEND_TEST_SYREN, "duration": duration})

    def sync_clock(self):
        return self._send_message({"action": MONITOR_SYNC_CLOCK})

    def set_clock(self, settings):
        message = {"action": MONITOR_SET_CLOCK}
        message = {**message, **settings}
        return self._send_message(message)

    def activate_output(self, output_id):
        return self._send_message({"action": MONITOR_ACTIVATE_OUTPUT, "output_id": output_id})
    
    def deactivate_output(self, output_id):
        return self._send_message({"action": MONITOR_DEACTIVATE_OUTPUT, "output_id": output_id})

    def _send_message(self, message):
        if self._socket:
            try:
                self._socket.send(json.dumps(message).encode())
                retries = 0
                data = b""
                while retries < IPCClient.MAX_RETRIES:
                    data += self._socket.recv(4096)
                    try:
                        return json.loads(data.decode())
                    except json.JSONDecodeError:
                        if data == b"":
                            self._logger.error("Received empty response from monitor socket! Message: %s", message)
                            return
                        self._logger.warning(
                            "Received invalid JSON (may be we need another part)! Response: %s",
                            data
                        )
            except ConnectionResetError as error:
                self._logger.error("Sending message to monitor socket failed! %s", error)
