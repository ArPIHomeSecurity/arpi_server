# -*- coding: utf-8 -*-
# @Author: Gábor Kovács
# @Date:   2021-02-25 20:09:57
# @Last Modified by:   Gábor Kovács
# @Last Modified time: 2021-02-25 20:09:57

import logging
import os

from constants import LOG_ADGSM


class GSM(object):
    def __init__(self):
        self._logger = logging.getLogger(LOG_ADGSM)
        self._options = None

    def setup(self):
        self._options = {}
        self._options["pin_code"] = "4321"
        self._options["port"] = os.environ["GSM_PORT"]
        self._options["baud"] = os.environ["GSM_PORT_BAUD"]

        self._logger.info(
            "Connecting to GSM modem on %s with %s baud (PIN: %s)...",
            self._options["port"],
            self._options["baud"],
            self._options["pin_code"],
        )

        return True

    def destroy(self):
        pass

    def sendSMS(self, phone_number, message):
        self._logger.info('Message sent to %s: "%s"', phone_number, message)
        return True
