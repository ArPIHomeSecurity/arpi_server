import logging
from datetime import datetime
from threading import Thread
from time import sleep

from monitor.adapters.gsm import CallResult, CallType
from monitor.adapters.mock.utils import get_sms_messages
from utils.constants import LOG_ADGSM

logger = logging.getLogger(LOG_ADGSM)


class Sms:
    def __init__(self, idx, number, text, time):
        self.index = idx
        self.number = number
        self.text = text
        self.time = time


MESSAGES = [
    Sms(
        idx=1, number="06201234567", text="Test message 1111", time=datetime(2024, 7, 22, 12, 0, 0)
    ),
    Sms(
        idx=2,
        number="0036309876543",
        text="Test message 2222",
        time=datetime(2024, 6, 21, 11, 0, 0),
    ),
]


class GSM:
    CONNECTS = 0

    def __init__(self, pin_code, port, baud, sms_received_callback=None, enabled=True):
        self._pin_code = pin_code
        self._port = port
        self._baud = baud
        self._sms_received_callback = sms_received_callback
        self._enabled = enabled
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    def set_enabled(self, enabled):
        if self._enabled == enabled:
            return

        self._enabled = enabled
        if not enabled:
            self.destroy()

    def set_sms_received_callback(self, callback):
        self._sms_received_callback = callback

    def inject_message(self):
        """Simulate an incoming SMS for testing the receiving path."""

        while True:
            messages = get_sms_messages()  # Ensure messages are loaded

            for message in messages:
                logger.info('Message received from %s: "%s"', message["number"], message["text"])
                if self._sms_received_callback:
                    self._sms_received_callback(
                        Sms(
                            idx=message["idx"],
                            number=message["number"],
                            text=message["text"],
                            time=message["time"],
                        )
                    )

    def setup(self):
        if not self._enabled:
            logger.debug("GSM disabled")
            return False

        if GSM.CONNECTS > 0:
            logger.warning("Connection already established! %s", GSM.CONNECTS)
        GSM.CONNECTS += 1

        if not self._port or not self._baud:
            logger.error("Invalid GSM options: %s %s", self._port, self._baud)
            return False

        logger.info(
            "Connecting to GSM modem on %s with %s baud (PIN: %s)...",
            self._port,
            self._baud,
            self._pin_code or "-",
        )

        self._connected = True
        sms_actions_thread = Thread(target=self.inject_message)
        sms_actions_thread.start()
        return True

    def send_SMS(self, phone_number, message):
        if not self._connect():
            return False

        sleep(7)
        logger.info('Message sent to %s: "%s"', phone_number, message)
        return True

    def get_sms_messages(self):
        if not self._connect():
            return []

        sleep(3)
        return MESSAGES

    def delete_sms_message(self, message_id):
        if not self._connect():
            return False

        sleep(2)
        logger.info("Message deleted: %s", message_id)
        global MESSAGES
        MESSAGES = [msg for msg in MESSAGES if msg.index != message_id]
        return True

    def call(self, phone_number, call_type: CallType):
        if not self._connect():
            return CallResult.FAILED

        sleep(3)
        logger.info("Calling (%s) number: %s", call_type, phone_number)
        return CallResult.ANSWERED

    def destroy(self):
        if self._connected:
            GSM.CONNECTS -= 1
            self._connected = False

    def _connect(self) -> bool:
        return self._connected or self.setup()
