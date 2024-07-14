import logging
from multiprocessing import Event
import re
from enum import Enum
from time import sleep

from serial.serialutil import PortNotOpenError

from gsmmodem.modem import GsmModem, Call
from gsmmodem.exceptions import (
    PinRequiredError,
    IncorrectPinError,
    TimeoutException,
    CmeError,
    CmsError,
    CommandError,
    InvalidStateException,
    InterruptedException
)
from constants import LOG_ADGSM


class CallType(Enum):
    ALERT = 1
    PANIC = 2
    TEST = 3


class CallResult(Enum):
    ANSWERED = 1
    CANCELLED = 2
    ACKNOWLEDGED = 3
    BUSY = 4
    FAILED = 5

CALL_ACKNOWLEDGED = "1"

class GSM:

    RETRY_GAP_SECONDS = 5
    MAX_RETRY = 5

    call_event = Event()
    call_result: CallResult = None

    def __init__(self, pin_code, port, baud):
        self._logger = logging.getLogger(LOG_ADGSM)
        self._pin_code = pin_code
        self._port = port
        self._baud = baud
        self._modem = None

    def setup(self):
        if not self._pin_code:
            self._logger.warning("Pin code not defined")

        if not self._port or \
                not self._baud:
            self._logger.error("Invalid GSM options: %s %s", self._port, self._baud)
            return False

        self._modem = GsmModem(self._port, int(self._baud))
        # fix for call status parsing of SIM900

        attempts = 0
        while True:
            try:
                self._logger.info(
                    "Connecting to GSM modem on %s with %s baud (PIN: %s)...",
                    self._port,
                    self._baud,
                    self._pin_code or "-",
                )

                self._modem.connect(self._pin_code)

                # fix for call status parsing of SIM900
                self._modem._pollCallStatusRegex = \
                    re.compile('^\+CLCC:\s+(\d+),(\d),(\d),(\d),([^,]),"([^,]*)",(\d+)')

                self._logger.info("GSM modem connected")
                return True
            except PinRequiredError:
                self._logger.error("SIM card PIN required!")
                self._modem = None
                return False
            except IncorrectPinError:
                self._logger.error("Incorrect SIM card PIN entered!")
                self._modem = None
                return False
            except TimeoutException as error:
                self._logger.error("No answer from GSM module (request timeout): %s!", str(error))
            except CmeError as error:
                self._logger.error("CME error from GSM module: %s!", str(error))

            except CmsError as error:
                self._logger.error("CMS error from GSM module: %s!", str(error))
            except Exception:
                self._logger.exception("Failed to access GSM module!")
                return False

            attempts += 1
            if attempts <= GSM.MAX_RETRY:
                self._logger.info("Retrying to connect in %s seconds...", GSM.RETRY_GAP_SECONDS)
                sleep(GSM.RETRY_GAP_SECONDS)
            else:
                self._logger.error("Failed to connect to GSM modem!")
                return False

    def send_SMS(self, phone_number, message):
        if not phone_number:
            self._logger.warning("SMS phone number not defined")
            return False

        if not self._modem:
            self.setup()

        self._modem.smsTextMode = True

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
        except (CmsError, CmeError) as error:
            self._logger.error("Failed to send message: %s", error)
            return False

        self._logger.debug("SMS sent")
        return True

    def call(self, phone_number, call_type: CallType) -> bool:
        if not phone_number:
            self._logger.warning("Call phone number not defined")
            return False

        if not self._modem:
            self.setup()

        if not self._modem:
            return False

        self._logger.debug("Checking for network coverage...")
        try:
            self._modem.waitForNetworkCoverage(30)
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
            return False
        except PortNotOpenError:
            self._logger.error("Modem serial port not open!")
            self.destroy()
            return False

        try:
            GSM.call_event.clear()
            self._modem.dtmfpool = []
            self._modem.write("AT+VTD=5")
            if call_type == CallType.ALERT:
                self._logger.info("Alert call to number='%s'", phone_number)
                self._modem.dial(
                    number=phone_number, timeout=30, callStatusUpdateCallbackFunc=GSM.play_alert
                )
            elif call_type == CallType.PANIC:
                self._logger.info("Panic call to number='%s'", phone_number)
                self._modem.dial(
                    number=phone_number, timeout=30, callStatusUpdateCallbackFunc=GSM.play_panic
                )
            elif call_type == CallType.TEST:
                self._logger.info("Test call to number='%s'", phone_number)
                self._modem.dial(
                    number=phone_number, timeout=30, callStatusUpdateCallbackFunc=GSM.play_test
                )
            else:
                self._logger.error("Unknown call type %s", call_type)
                return False

        except TimeoutException:
            self._logger.error("Failed to call: the call operation timed out")
            return False
        except (CmsError, CmeError) as error:
            self._logger.error("Failed to call: %s", error)
            return False

        # wait for callEvent finished
        self._logger.info("Waiting for call to finish...")
        self.call_event.wait()

        call_result = GSM.call_result
        GSM.call_result = None

        # call result as text
        self._logger.trace(
            "Call finished with result: %s, received dtmf: %s",
            call_result.name,
            self._modem.dtmfpool
        )
        if self._modem.dtmfpool == [CALL_ACKNOWLEDGED]:
            self._logger.debug("Call was acknowledged")
            call_result = CallResult.ACKNOWLEDGED

        return (
            call_result == CallResult.ANSWERED or
            call_result == CallResult.ACKNOWLEDGED or
            call_result == CallResult.CANCELLED
        )

    @property
    def incoming_dtmf(self) -> str:
        return "".join(self._modem.dtmfpool)

    @staticmethod
    def play_dtmf(call: Call, dtmf: str):
        logger = logging.getLogger(LOG_ADGSM)
        logger.debug(
            "Manage call with DTMF tones: answered=%s, active=%s, state=%s",
            call.answered, call.active, GSM.call_result
        )

        if call.answered:
            if call.active:
                try:
                    GSM.call_result = CallResult.ANSWERED
                    logger.debug("Playing DTMF tones: %s", dtmf)
                    call.sendDtmfTone(dtmf)
                except TimeoutException as e:
                    logger.error("DTMF playback timeout: %s", e)
                    GSM.call_result = CallResult.CANCELLED
                except InterruptedException as e:
                    # Call was ended during playback
                    logger.error(
                        "DTMF playback interrupted: %s (%s Error %s)", e, e.cause.type, e.cause.code
                    )
                except CommandError as e:
                    logger.error("DTMF playback failed: %s", e)
                    GSM.call_result = CallResult.FAILED

                # wait for incoming dtmf
                sleep(20)

                try:
                    logger.debug("Hanging up call...")
                    call.hangup()
                except CommandError as e:
                    logger.error("Hangup failed: %s", e)
                GSM.call_event.set()
        else:
            # Call is no longer active (remote party ended it)
            if GSM.call_result is None:
                # call was not answered
                GSM.call_result = CallResult.BUSY

            logger.info("Call has been ended by remote party")
            GSM.call_event.set()

    @staticmethod
    def play_alert(call: Call):
        logger = logging.getLogger(LOG_ADGSM)
        logger.debug("Manage alert call")

        GSM.play_dtmf(call, "111")

    @staticmethod
    def play_panic(call):
        logger = logging.getLogger(LOG_ADGSM)
        logger.debug("Manage panic call")

        GSM.play_dtmf(call, "00000")

    @staticmethod
    def play_test(call):
        logger = logging.getLogger(LOG_ADGSM)
        logger.debug("Manage test call")

        GSM.play_dtmf(call, "5")

    def destroy(self):
        if self._modem:
            self._logger.debug("Closing modem")
            self._modem.close()
            self._modem = None
