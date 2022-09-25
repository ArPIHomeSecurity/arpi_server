# -*- coding: utf-8 -*-
# @Author: Gábor Kovács
# @Date:   2021-02-25 20:09:17
# @Last Modified by:   Gábor Kovács
# @Last Modified time: 2021-02-25 20:09:17

import json
import logging
import os

from gsmmodem.modem import GsmModem
from gsmmodem.exceptions import PinRequiredError, IncorrectPinError, TimeoutException, CmeError, CmsError, CommandError
from models import Option
from constants import LOG_ADGSM
from monitoring.database import Session
from time import sleep


class GSM(object):

    RETRY_GAP = 5

    def __init__(self):
        self._logger = logging.getLogger(LOG_ADGSM)
        self._modem = None
        self._options = None

    def setup(self):
        db_session = Session()
        section = db_session.query(Option).filter_by(name="notifications", section="gsm").first()
        db_session.close()

        self._options = json.loads(section.value) if section else {"pin_code": ""}
        self._options["port"] = os.environ["GSM_PORT"]
        self._options["baud"] = os.environ["GSM_PORT_BAUD"]

        if not self._options["pin_code"]:
            self._logger.info("Pin code not defined, skip connecting to GSM modem")
            return False

        self._modem = GsmModem(self._options["port"], int(self._options["baud"]))
        self._modem.smsTextMode = True

        connected = False
        while not connected:
            try:
                self._logger.info(
                    "Connecting to GSM modem on %s with %s baud (PIN: %s)...",
                    self._options["port"],
                    self._options["baud"],
                    self._options["pin_code"],
                )

                self._modem.connect(self._options["pin_code"])
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
                    "No answer from GSM module: %s! Request timeout, retry in %s seconds...", str(error), GSM.RETRY_GAP
                )
            except CmeError as error:
                self._logger.error(
                    "CME error from GSM module: %s! Unexpected error, retry in %s seconds...", str(error), GSM.RETRY_GAP
                )
            except CmsError as error:
                if str(error) == "CMS 302":
                    self._logger.debug("GSM modem not ready, retry in %s seconds...", GSM.RETRY_GAP)
                else:
                    self._logger.error(
                        "CMS error from GSM module: %s. Unexpected error, retry in %s seconds...",
                        str(error),
                        GSM.RETRY_GAP,
                    )
            except Exception:
                self._logger.exception("Failed to access GSM module!")
                return False

            sleep(GSM.RETRY_GAP)

        return True

    def destroy(self):
        if self._modem is not None:
            self._logger.debug("Closing modem")
            self._modem.close()

    def sendSMS(self, phone_number, message):
        if not self._modem:
            self.setup()

        if not self._modem:
            return False

        if message is None:
            return False

        self._logger.debug("Checking for network coverage...")
        try:
            self._modem.waitForNetworkCoverage(5)
        except CommandError as error:
            self._logger.error("Command error: %s", error)
            return False
        except TimeoutException:
            self._logger.error(
                "Network signal strength is not sufficient, "
                "please adjust modem position/antenna and try again."
            )
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
