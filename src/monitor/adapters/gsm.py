import logging
import re
from enum import Enum
from multiprocessing import Event
from time import sleep

from gsmmodem.exceptions import (
    CmeError,
    CmsError,
    CommandError,
    IncorrectPinError,
    InterruptedException,
    InvalidStateException,
    PinRequiredError,
    TimeoutException,
)
from gsmmodem.modem import Call, GsmModem, ReceivedSms
from serial.serialutil import PortNotOpenError

from utils.constants import LOG_ADGSM

logger = logging.getLogger(LOG_ADGSM)


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
    CONNECTS = 0
    RETRY_GAP_SECONDS = 5
    MAX_RETRY = 5
    # upper bound for a full dial + DTMF playback + hangup cycle
    CALL_TIMEOUT_SECONDS = 120

    def __init__(self, pin_code, port, baud, sms_received_callback=None, enabled=True):
        self._pin_code = pin_code
        self._port = port
        self._baud = baud
        self._sms_received_callback = sms_received_callback
        self._enabled = enabled
        self._modem = None
        self._call_event = Event()
        self.call_result: CallResult = None

    @property
    def connected(self) -> bool:
        return self._modem is not None

    def set_enabled(self, enabled):
        if self._enabled == enabled:
            return

        self._enabled = enabled
        if not enabled:
            self.destroy()

    def set_sms_received_callback(self, callback):
        """
        The callback is passed to the modem on connect, so an already connected
        modem has to be dropped to enable the new message indications.
        """
        self._sms_received_callback = callback
        if self._modem:
            self.destroy()

        self.setup()

    def setup(self):
        if not self._enabled:
            logger.debug("GSM disabled")
            return False

        if GSM.CONNECTS > 0:
            logger.warning("Connection already established! %s", GSM.CONNECTS)
        GSM.CONNECTS += 1

        if not self._pin_code:
            logger.warning("Pin code not defined")

        if not self._port or not self._baud:
            logger.error("Invalid GSM options: %s %s", self._port, self._baud)
            return False

        self._modem = GsmModem(
            self._port,
            int(self._baud),
            smsReceivedCallbackFunc=self._sms_received_callback,
        )

        attempts = 0
        while True:
            try:
                logger.info(
                    "Connecting to GSM modem on %s with %s baud (PIN: %s)...",
                    self._port,
                    self._baud,
                    self._pin_code or "-",
                )

                self._modem.connect(self._pin_code)

                # fix for call status parsing of SIM900
                self._modem._pollCallStatusRegex = re.compile(
                    r'^\+CLCC:\s+(\d+),(\d),(\d),(\d),([^,]),"([^,]*)",(\d+)'
                )

                # set once here to keep the message parsing mode consistent for all users
                self._modem.smsTextMode = True

                logger.info("GSM modem connected")
                return True
            except PinRequiredError:
                logger.error("SIM card PIN required!")
                self._modem = None
                return False
            except IncorrectPinError:
                logger.error("Incorrect SIM card PIN entered!")
                self._modem = None
                return False
            except TimeoutException as error:
                logger.error("No answer from GSM module (request timeout): %s!", str(error))
            except CmeError as error:
                logger.error("CME error from GSM module: %s!", str(error))

            except CmsError as error:
                logger.error("CMS error from GSM module: %s!", str(error))
            except Exception:
                logger.exception("Failed to access GSM module!")
                return False

            attempts += 1
            if attempts <= GSM.MAX_RETRY:
                logger.info("Retrying to connect in %s seconds...", GSM.RETRY_GAP_SECONDS)
                sleep(GSM.RETRY_GAP_SECONDS)
            else:
                logger.error("Failed to connect to GSM modem!")
                return False

    def send_SMS(self, phone_number, message):
        if not phone_number:
            logger.warning("SMS phone number not defined")
            return False

        if not self._modem:
            self.setup()

        if not self._modem:
            return False

        if message is None:
            return False

        logger.debug("Checking for network coverage...")
        try:
            self._modem.waitForNetworkCoverage(10)
        except CommandError as error:
            logger.error("Command error: %s", error)
            return False
        except InvalidStateException:
            logger.error("Modem is not in a valid state!")
            self.destroy()
            return False
        except TimeoutException:
            logger.error(
                "Network signal strength is not sufficient, "
                "please adjust modem position/antenna and try again."
            )
            return False
        except PortNotOpenError:
            logger.error("Modem serial port not open!")
            self.destroy()
            return False

        try:
            logger.info("Sending SMS to %s", phone_number)
            logger.debug("Sending message %s", message)
            self._modem.sendSms(phone_number, message)
        except TimeoutException:
            logger.error("Failed to send message: the send operation timed out")
            return False
        except (CmsError, CmeError) as error:
            logger.error("Failed to send message: %s", error)
            return False

        logger.debug("SMS sent")
        return True

    def get_sms_messages(self) -> list[ReceivedSms]:
        if not self._modem:
            self.setup()

        if not self._modem:
            return []

        try:
            logger.info("Reading SMS messages...")
            messages = self._modem.listStoredSms()
            logger.debug("SMS messages received: %s", len(messages))
            return messages
        except TimeoutException:
            logger.error("Failed to read messages: the operation timed out")
            return []
        except (CmsError, CmeError) as error:
            logger.error("Failed to read messages: %s", error)
            return []

    def delete_sms_message(self, message_id):
        if not self._modem:
            self.setup()

        if not self._modem:
            return False

        try:
            logger.info("Deleting SMS message: %s", message_id)
            self._modem.deleteStoredSms(index=message_id)
            logger.debug("SMS message deleted")
            return True
        except TimeoutException:
            logger.error("Failed to delete message: the operation timed out")
            return False
        except (CmsError, CmeError) as error:
            logger.error("Failed to delete message: %s", error)
            return False

    def call(self, phone_number, call_type: CallType) -> CallResult:
        if not phone_number:
            logger.warning("Call phone number not defined")
            return CallResult.FAILED

        if not self._modem:
            self.setup()

        if not self._modem:
            return CallResult.FAILED

        logger.debug("Checking for network coverage...")
        try:
            self._modem.waitForNetworkCoverage(30)
        except CommandError as error:
            logger.error("Command error: %s", error)
            return CallResult.FAILED
        except InvalidStateException:
            logger.error("Modem is not in a valid state!")
            self.destroy()
            return CallResult.FAILED
        except TimeoutException:
            logger.error(
                "Network signal strength is not sufficient, "
                "please adjust modem position/antenna and try again."
            )
            return CallResult.FAILED
        except PortNotOpenError:
            logger.error("Modem serial port not open!")
            self.destroy()
            return CallResult.FAILED

        try:
            self.call_result = None
            self._call_event.clear()
            self._modem.dtmfpool = []
            self._modem.write("AT+VTD=5")
            if call_type == CallType.ALERT:
                logger.info("Alert call to number='%s'", phone_number)
                self._modem.dial(
                    number=phone_number, timeout=30, callStatusUpdateCallbackFunc=self.play_alert
                )
            elif call_type == CallType.PANIC:
                logger.info("Panic call to number='%s'", phone_number)
                self._modem.dial(
                    number=phone_number, timeout=30, callStatusUpdateCallbackFunc=self.play_panic
                )
            elif call_type == CallType.TEST:
                logger.info("Test call to number='%s'", phone_number)
                self._modem.dial(
                    number=phone_number, timeout=30, callStatusUpdateCallbackFunc=self.play_test
                )
            else:
                logger.error("Unknown call type %s", call_type)
                return CallResult.FAILED

        except TimeoutException:
            logger.error("Failed to call: the call operation timed out")
            return CallResult.FAILED
        except (CmsError, CmeError) as error:
            logger.error("Failed to call: %s", error)
            return CallResult.FAILED

        # wait for callEvent finished
        logger.info("Waiting for call to finish...")
        if not self._call_event.wait(timeout=GSM.CALL_TIMEOUT_SECONDS):
            logger.error("Call did not finish in %s seconds", GSM.CALL_TIMEOUT_SECONDS)
            return CallResult.FAILED

        if self.call_result is None:
            logger.error("Call finished with unknown result")
            return CallResult.FAILED

        incoming_dtmf = ""
        while True:
            tone = self._modem.GetIncomingDTMF()
            if tone is None:
                break
            incoming_dtmf += tone

        logger.info(
            "Call finished with result: %s, received dtmf: %s",
            self.call_result.name,
            incoming_dtmf,
        )
        if CALL_ACKNOWLEDGED in incoming_dtmf:
            logger.debug("Call was acknowledged")
            self.call_result = CallResult.ACKNOWLEDGED

        return self.call_result

    def play_dtmf(self, call: Call, dtmf: str):
        logger = logging.getLogger(LOG_ADGSM)
        logger.debug(
            "Manage call with DTMF tones: answered=%s, active=%s, state=%s",
            call.answered,
            call.active,
            self.call_result,
        )

        if call.answered:
            if call.active:
                try:
                    self.call_result = CallResult.ANSWERED
                    logger.debug("Playing DTMF tones: %s", dtmf)
                    call.sendDtmfTone(dtmf)
                    if not call.dtmfSupport:
                        logger.warning("Call does not support DTMF")
                        # force acknowledge if the call does not support DTMF
                        self.call_result = CallResult.ACKNOWLEDGED
                except TimeoutException as e:
                    logger.error("DTMF playback timeout: %s", e)
                    self.call_result = CallResult.CANCELLED
                except InterruptedException as e:
                    # Call was ended during playback
                    logger.error(
                        "DTMF playback interrupted: %s (%s Error %s)", e, e.cause.type, e.cause.code
                    )
                except CommandError as e:
                    logger.error("DTMF playback failed: %s", e)
                    self.call_result = CallResult.FAILED

                # wait for incoming dtmf
                sleep(20)

                try:
                    logger.debug("Hanging up call...")
                    call.hangup()
                except CommandError as e:
                    logger.error("Hangup failed: %s", e)
                self._call_event.set()
        else:
            # Call is no longer active (remote party ended it)
            if self.call_result is None:
                # call was not answered
                self.call_result = CallResult.BUSY

            logger.info("Call has been ended by remote party")
            self._call_event.set()

    def play_alert(self, call: Call):
        logger.debug("Manage alert call")
        self.play_dtmf(call, "111")

    def play_panic(self, call: Call):
        logger.debug("Manage panic call")
        self.play_dtmf(call, "00000")

    def play_test(self, call: Call):
        logger.debug("Manage test call")
        self.play_dtmf(call, "5")

    def destroy(self):
        if self._modem:
            logger.debug("Closing modem")
            self._modem.close()
            self._modem = None
            GSM.CONNECTS -= 1
