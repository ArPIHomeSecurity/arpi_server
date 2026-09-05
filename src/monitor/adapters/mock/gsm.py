import logging
from dataclasses import dataclass
from threading import Lock, Thread
from time import sleep

from monitor.adapters.gsm import CallResult, CallType
from monitor.adapters.mock.utils import get_sms_messages
from utils.constants import LOG_ADGSM

logger = logging.getLogger(LOG_ADGSM)


@dataclass
class Sms:
    idx: int
    number: str
    text: str
    time: str


message_lock = Lock()
MESSAGES: dict[str, Sms] = {}


class GSM:
    CONNECTS = 0

    def __init__(self, pin_code, port, baud, sms_received_callback=None, enabled=True):
        self._pin_code = pin_code
        self._port = port
        self._baud = baud
        self._sms_received_callback = sms_received_callback
        self._enabled = enabled
        self.connected = False

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

        while self.connected:
            messages = get_sms_messages()  # Ensure messages are loaded

            for message in messages:
                logger.info(
                    'Message(%s) received from %s: "%s"',
                    message["idx"],
                    message["number"],
                    message["text"],
                )
                sms = Sms(
                    idx=message["idx"],
                    number=message["number"],
                    text=message["text"],
                    time=message["time"],
                )
                with message_lock:
                    MESSAGES[sms.idx] = sms

                if self._sms_received_callback:
                    self._sms_received_callback(sms)

            sleep(1)

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

        self.connected = True
        sms_actions_thread = Thread(target=self.inject_message)
        sms_actions_thread.start()
        return True

    def send_SMS(self, phone_number, message):
        if not self.connected:
            return False

        sleep(7)
        logger.info('Message sent to %s: "%s"', phone_number, message)
        return True

    def get_sms_messages(self):
        if not self.connected:
            return []

        sleep(3)
        return list(MESSAGES.values())

    def delete_sms_message(self, message_id):
        if not self.connected:
            return False

        sleep(2)
        logger.info("Message deleted: %s", message_id)
        with message_lock:
            if message_id in MESSAGES:
                MESSAGES.pop(message_id)

        return True

    def call(self, phone_number, call_type: CallType):
        if not self.connected:
            return CallResult.FAILED

        sleep(3)
        logger.info("Calling (%s) number: %s", call_type, phone_number)
        return CallResult.ANSWERED

    def destroy(self):
        if self.connected:
            GSM.CONNECTS -= 1
            self.connected = False

    def _connect(self) -> bool:
        return self.connected or self.setup()
