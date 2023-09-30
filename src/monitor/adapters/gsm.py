import logging

from serial.serialutil import PortNotOpenError

from gsmmodem.modem import GsmModem
from gsmmodem.exceptions import (
    PinRequiredError,
    IncorrectPinError,
    TimeoutException,
    CmeError,
    CmsError,
    CommandError,
    InvalidStateException
)
from constants import LOG_ADGSM
from time import sleep


class GSM(object):

    RETRY_GAP_SECONDS = 5
    MAX_RETRY = 5

    def __init__(self, pin_code, port, baud):
        self._logger = logging.getLogger(LOG_ADGSM)
        self._pin_code = pin_code
        self._port = port
        self._baud = baud
        self._modem = None

    def setup(self):
        if not self._pin_code:
            self._logger.warn("Pin code not defined")

        if not self._port or \
                not self._baud:
            self._logger.error("Invalid GSM options: %s %s", self._port, self._baud)
            return False

        self._modem = GsmModem(self._port, int(self._baud))
        self._modem.smsTextMode = True

        attempts = 0
        connected = False
        while not connected and attempts <= GSM.MAX_RETRY:
            try:
                self._logger.info(
                    "Connecting to GSM modem on %s with %s baud (PIN: %s)...",
                    self._port,
                    self._baud,
                    self._pin_code or "-",
                )

                self._modem.connect(self._pin_code)
                self._logger.info("GSM modem connected")
                connected = True
            except PinRequiredError:
                self._logger.error("SIM card PIN required!")
                self._modem = None
                return False
            except IncorrectPinError:
                self._logger.error("Incorrect SIM card PIN entered!")
                self._modem = None
                return False
            except TimeoutException as error:
                self._logger.error(
                    "No answer from GSM module: %s! Request timeout, retry in %s seconds...", str(error), GSM.RETRY_GAP_SECONDS
                )
            except CmeError as error:
                self._logger.error(
                    "CME error from GSM module: %s! Unexpected error, retry in %s seconds...", str(error), GSM.RETRY_GAP_SECONDS
                )
            except CmsError as error:
                if str(error) == "CMS 302":
                    self._logger.debug("GSM modem not ready, retry in %s seconds...", GSM.RETRY_GAP_SECONDS)
                else:
                    self._logger.error(
                        "CMS error from GSM module: %s. Unexpected error, retry in %s seconds...",
                        str(error),
                        GSM.RETRY_GAP_SECONDS,
                    )
            except Exception:
                self._logger.exception("Failed to access GSM module!")
                return False

            sleep(GSM.RETRY_GAP_SECONDS)
            attempts += 1

        return True

    def send_SMS(self, phone_number, message):
        if not self._modem:
            self.setup()

        if not self._modem:
            return False

        if message is None:
            return False

        self._logger.debug("Checking for network coverage...")
        try:
            self._modem.waitForNetworkCoverage(10)
        except CommandError as error:
            self._logger.error("Command error: %s", error)
            return False
        except InvalidStateException:
            self._logger.error("Modem is not in a valid state!")
            self.destroy()
            return False
        except TimeoutException:
            self._logger.error(
                "Network signal strength is not sufficient, "
                "please adjust modem position/antenna and try again."
            )
            self.destroy()
            return False
        except PortNotOpenError:
            self._logger.error("Modem serial port not open!")
            self.destroy()
            return False

        try:
            self._logger.info("Sending SMS to %s", phone_number)
            self._logger.debug("Sending message %s", message)
            self._modem.sendSms(phone_number, message)
        except TimeoutException:
            self._logger.error("Failed to send message: the send operation timed out")
            return False
        except CmsError as error:
            self._logger.error("Failed to send message: %s", error)
            return False

        self._logger.debug("SMS sent")
        return True

    def destroy(self):
        if self._modem:
            self._logger.debug("Closing modem")
            self._modem.close()
            self._modem = None
