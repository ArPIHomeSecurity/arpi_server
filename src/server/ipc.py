from dataclasses import asdict
import json
import logging
import socket
from os import environ

from utils.constants import (
    ARM_AWAY,
    ARM_STAY,
    LOG_IPC,
)
from monitor.actions import (
    DeleteSMSMessageCommand,
    GetSMSMessagesCommand,
    MakeTestCallCommand,
    MonitorActivateOutputCommand,
    MonitorArmAwayCommand,
    MonitorArmStayCommand,
    MonitorCommand,
    MonitorDeactivateOutputCommand,
    MonitorDisarmCommand,
    MonitorGetStateCommand,
    MonitorRegisterCardCommand,
    MonitorSetClockCommand,
    MonitorSyncClockCommand,
    MonitorUpdateConfigCommand,
    MonitorUpdateKeypadCommand,
    PowerGetStateCommand,
    SendTestEmailCommand,
    SendTestSMSCommand,
    SendTestSyrenCommand,
    UpdateSSHCommand,
    UpdateSecureConnectionCommand,
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
                self._logger.info(
                    "Connecting to monitor socket: %s", environ["MONITOR_INPUT_SOCKET"]
                )
                self._socket.connect(environ["MONITOR_INPUT_SOCKET"])
                self._socket.settimeout(60)
            except (ConnectionRefusedError, FileNotFoundError):
                self._logger.error(
                    "Failed to connect to monitor socket! %s", environ["MONITOR_INPUT_SOCKET"]
                )
                self._socket = None

    @property
    def is_connected(self):
        return self._socket is not None

    def arm(self, arm_type, user_id, area_id=None):
        if arm_type == ARM_AWAY:
            return self._send_message(
                MonitorArmAwayCommand(user_id=user_id, area_id=area_id, use_delay=False)
            )
        elif arm_type == ARM_STAY:
            return self._send_message(
                MonitorArmStayCommand(user_id=user_id, area_id=area_id, use_delay=False)
            )
        else:
            self._logger.error("Unknown arm type: %s", arm_type)
            return {"message": "Unknown arm type"}

    def disarm(self, user_id, area_id=None):
        return self._send_message(MonitorDisarmCommand(user_id=user_id, area_id=area_id))

    def get_state(self):
        return self._send_message(MonitorGetStateCommand())

    def get_power_state(self):
        return self._send_message(PowerGetStateCommand())

    def update_configuration(self):
        return self._send_message(MonitorUpdateConfigCommand())

    def update_keypad(self):
        return self._send_message(MonitorUpdateKeypadCommand())

    def register_card(self):
        return self._send_message(MonitorRegisterCardCommand())

    def update_dyndns(self):
        return self._send_message(UpdateSecureConnectionCommand())

    def update_ssh(self):
        return self._send_message(UpdateSSHCommand())

    def send_test_email(self):
        return self._send_message(SendTestEmailCommand())

    def send_test_sms(self):
        return self._send_message(SendTestSMSCommand())

    def get_sms_messages(self):
        return self._send_message(GetSMSMessagesCommand())

    def delete_sms_message(self, message_id):
        return self._send_message(DeleteSMSMessageCommand(message_id=message_id))

    def make_test_call(self):
        return self._send_message(MakeTestCallCommand())

    def send_test_syren(self, duration):
        return self._send_message(SendTestSyrenCommand(duration=duration))

    def sync_clock(self):
        return self._send_message(MonitorSyncClockCommand())

    def set_clock(self, settings):
        return self._send_message(
            MonitorSetClockCommand(
                timezone=settings.get("timezone"),
                datetime=settings.get("datetime"),
            )
        )

    def activate_output(self, output_id):
        return self._send_message(MonitorActivateOutputCommand(output_id=output_id))

    def deactivate_output(self, output_id):
        return self._send_message(MonitorDeactivateOutputCommand(output_id=output_id))

    def _send_message(self, message: MonitorCommand) -> dict:
        payload = asdict(message)

        if self._socket:
            try:
                self._socket.send(json.dumps(payload).encode())
                retries = 0
                data = b""
                while retries < IPCClient.MAX_RETRIES:
                    data += self._socket.recv(4096)
                    try:
                        return json.loads(data.decode())
                    except json.JSONDecodeError:
                        if data == b"":
                            self._logger.error(
                                "Received empty response from monitor socket! Message: %s", payload
                            )
                            return
                        self._logger.warning(
                            "Received invalid JSON (may be we need another part)! Response: %s",
                            data,
                        )
            except ConnectionResetError as error:
                self._logger.error("Sending message to monitor socket failed! %s", error)
