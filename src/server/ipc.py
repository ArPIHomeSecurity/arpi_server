# -*- coding: utf-8 -*-
# @Author: Gábor Kovács
# @Date:   2021-02-25 20:06:08
# @Last Modified by:   Gábor Kovács
# @Last Modified time: 2021-02-25 20:06:12
import json
import logging
import socket
from os import environ

from monitoring.constants import (
    ARM_AWAY,
    ARM_STAY,
    LOG_IPC,
    MONITOR_ARM_AWAY,
    MONITOR_ARM_STAY,
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

    def disarm(self, user_id):
        return self._send_message({"action": MONITOR_DISARM, "user_id": user_id})

    def get_arm(self):
        return self._send_message({"action": MONITOR_GET_ARM})

    def arm(self, arm_type, user_id):
        if arm_type == ARM_AWAY:
            return self._send_message({"action": MONITOR_ARM_AWAY, "user_id": user_id})
        elif arm_type == ARM_STAY:
            return self._send_message({"action": MONITOR_ARM_STAY, "user_id": user_id})
        else:
            print("Unknown arm type: %s" % arm_type)

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

    def sync_clock(self):
        return self._send_message({"action": MONITOR_SYNC_CLOCK})

    def set_clock(self, settings):
        message = {"action": MONITOR_SET_CLOCK}
        message = {**message, **settings}
        return self._send_message(message)

    def _send_message(self, message):
        if self._socket:
            self._socket.send(json.dumps(message).encode())
            data = self._socket.recv(1024)
            return json.loads(data.decode())
