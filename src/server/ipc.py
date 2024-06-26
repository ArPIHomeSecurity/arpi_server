import json
import logging
import socket
from os import environ

from constants import (
    ARM_AWAY,
    ARM_STAY,
    LOG_IPC,
    MONITOR_ACTIVATE_OUTPUT,
    MONITOR_ARM_AWAY,
    MONITOR_ARM_STAY,
    MONITOR_DEACTIVATE_OUTPUT,
    MONITOR_DISARM,
    MONITOR_REGISTER_CARD,
    POWER_GET_STATE,
    MONITOR_SET_CLOCK,
    MONITOR_SYNC_CLOCK,
    MONITOR_UPDATE_CONFIG,
    UPDATE_SECURE_CONNECTION,
    MONITOR_UPDATE_KEYPAD,
    MONITOR_GET_STATE,
    MONITOR_GET_ARM,
    SEND_TEST_EMAIL,
    SEND_TEST_SMS,
    SEND_TEST_SYREN,
    UPDATE_SSH,
)


class IPCClient(object):
    """
    Sending IPC messages from the REST API to the monitoring service
    """

    _socket = None

    def __init__(self):
        self._logger = logging.getLogger(LOG_IPC)
        if not self._socket:
            self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                self._socket.connect(environ["MONITOR_INPUT_SOCKET"])
            except (ConnectionRefusedError, FileNotFoundError):
                self._socket = None

    def get_arm(self):
        return self._send_message({"action": MONITOR_GET_ARM})

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
                data = self._socket.recv(1024)
                return json.loads(data.decode())
            except ConnectionResetError:
                self._logger.error("Sending message to monitor socket failed!")
