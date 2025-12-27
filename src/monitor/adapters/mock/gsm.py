import logging

from datetime import datetime
from time import sleep

from utils.constants import LOG_ADGSM
from monitor.adapters.gsm import CallType


class Sms:
    def __init__(self, idx, number, text, time):
        self.index = idx
        self.number = number
        self.text = text
        self.time = time


MESSAGES = [
    Sms(idx=1, number="06201234567", text="Test message 1111", time=datetime(2024, 7, 22, 12, 0, 0)),
    Sms(idx=2, number="0036309876543", text="Test message 2222", time=datetime(2024, 6, 21, 11, 0, 0)),
]


class GSM:

    CONNECTS = 0

    def __init__(self, pin_code, port, baud):
        self._logger = logging.getLogger(LOG_ADGSM)
        self._pin_code = pin_code
        self._port = port
        self._baud = baud

    def setup(self):
        if GSM.CONNECTS > 0:
            self._logger.warning("Connection already established! %s", GSM.CONNECTS)
        GSM.CONNECTS += 1

        if not self._port or not self._baud:
            self._logger.error("Invalid GSM options: %s %s", self._port, self._baud)
            return False

        self._logger.info(
            "Connecting to GSM modem on %s with %s baud (PIN: %s)...",
            self._port,
            self._baud,
            self._pin_code or "-",
        )

        return True

    def send_SMS(self, phone_number, message):
        sleep(7)
        self._logger.info('Message sent to %s: "%s"', phone_number, message)
        return True

    def get_sms_messages(self):
        sleep(3)
        return MESSAGES

    def delete_sms_message(self, message_id):
        sleep(2)
        self._logger.info("Message deleted: %s", message_id)
        global MESSAGES
        MESSAGES = [msg for msg in MESSAGES if msg.index != message_id]
        return True

    def call(self, phone_number, call_type: CallType):
        sleep(3)
        self._logger.info("Calling (%s) number: %s", call_type, phone_number)
        return False

    @property
    def incoming_dtmf(self):
        # return None
        return "1"

    def destroy(self):
        GSM.CONNECTS -= 1
