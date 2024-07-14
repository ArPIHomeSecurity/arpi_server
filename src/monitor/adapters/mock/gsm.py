import logging
from time import sleep

from constants import LOG_ADGSM
from monitor.adapters.gsm import CallType


class GSM(object):
    def __init__(self, pin_code, port, baud):
        self._logger = logging.getLogger(LOG_ADGSM)
        self._pin_code = pin_code
        self._port = port
        self._baud = baud

    def setup(self):
        if not self._port or \
                not self._baud:
            self._logger.error("Invalid GSM options: %s %s", self._port, self._baud)
            return False

        self._logger.info(
            "Connecting to GSM modem on %s with %s baud (PIN: %s)...",
            self._port,
            self._baud,
            self._pin_code or "-"
        )

        return True

    def send_SMS(self, phone_number, message):
        sleep(7)
        self._logger.info('Message sent to %s: "%s"', phone_number, message)
        return True

    def call(self, phone_number, call_type: CallType):
        sleep(3)
        self._logger.info('Calling (%s) number: %s', call_type, phone_number)
        return False

    @property
    def incoming_dtmf(self):
        # return None
        return "1"

    def destroy(self):
        pass
