# -*- coding: utf-8 -*-
# @Author: Gábor Kovács
# @Date:   2021-02-25 20:09:09
# @Last Modified by:   Gábor Kovács
# @Last Modified time: 2021-02-25 20:09:10

import logging
import os
from multiprocessing import Process
from queue import Empty
from time import time

from sqlalchemy.engine import create_engine
from sqlalchemy.engine.url import URL
from sqlalchemy.orm.session import sessionmaker

import models
from monitoring.adapters.keypads.base import KeypadBase
from monitoring.adapters.keypads.wiegand import WiegandKeypad
from monitoring.adapters.mock.keypad import MockKeypad
from monitoring.constants import (
    LOG_ADKEYPAD,
    MONITOR_ARM_AWAY,
    MONITOR_ARM_STAY,
    MONITOR_DISARM,
    MONITOR_STOP,
    MONITOR_UPDATE_KEYPAD,
    THREAD_KEYPAD,
)

if os.uname()[4][:3] == "arm":
    from monitoring.adapters.keypads.dsc import DSCKeypad

COMMUNICATION_PERIOD = 0.5  # sec


class Keypad(Process):
    # pins
    DATA_PIN0 = 0
    DATA_PIN1 = 5
    DATA_PIN2 = 6

    def __init__(self, commands, responses):
        super(Keypad, self).__init__(name=THREAD_KEYPAD)
        self._logger = logging.getLogger(LOG_ADKEYPAD)
        self._commands = commands
        self._responses = responses
        self._codes = []
        self._keypad: KeypadBase = None

    def set_type(self, type):
        # check if running on Raspberry
        if os.uname()[4][:3] != "arm":
            self._keypad = MockKeypad(Keypad.DATA_PIN1, Keypad.DATA_PIN0)
            type = "MOCK"
        elif type == "DSC":
            self._keypad = DSCKeypad(Keypad.DATA_PIN1, Keypad.DATA_PIN0)
        elif type == "WIEGAND":
            self._keypad = WiegandKeypad(Keypad.DATA_PIN2, Keypad.DATA_PIN1, Keypad.DATA_PIN0)
        elif type is None:
            self._logger.debug("Keypad removed")
            self._keypad = None
        else:
            self._logger.error("Unknown keypad type: %s", type)
        self._logger.debug("Keypad created type: %s", type)

    def configure(self):
        # load from db
        uri = None
        try:
            uri = URL(
                drivername="postgresql+psycopg2",
                username=os.environ.get("DB_USER", None),
                password=os.environ.get("DB_PASSWORD", None),
                host=os.environ.get("DB_HOST", None),
                port=os.environ.get("DB_PORT", None),
                database=os.environ.get("DB_SCHEMA", None),
            )
        except KeyError:
            self._logger.error("Database connnection not configured")
            return

        engine = create_engine(uri)
        Session = sessionmaker(bind=engine)
        db_session = Session()

        users = db_session.query(models.User).all()
        self._codes = [user.fourkey_code for user in users]

        keypad_settings = db_session.query(models.Keypad).first()
        if keypad_settings:
            self.set_type(keypad_settings.type.name)
            self._keypad.enabled = keypad_settings.enabled
        else:
            self.set_type(None)

        if self._keypad and self._keypad.enabled:
            self._keypad.initialise()

        db_session.close()

    def run(self):
        self.configure()

        try:
            self.communicate()
        except KeyboardInterrupt:
            self._logger.info("Keyboard interrupt")
        except Exception:
            self._logger.exception("Keypad communication failed!")

        self._logger.info("Keypad manager stopped")

    def communicate(self):
        last_press = int(time())
        presses = ""
        while True:
            try:
                self._logger.debug("Wait for command...")
                message = self._commands.get(timeout=COMMUNICATION_PERIOD)
                self._logger.info("Command: %s", message)

                if message == MONITOR_UPDATE_KEYPAD:
                    self._logger.info("Updating keypad")
                    self.configure()
                    last_press = int(time())
                elif message in (MONITOR_ARM_AWAY, MONITOR_ARM_STAY) and self._keypad:
                    self._logger.info("Keypad armed")
                    self._keypad.set_armed(True)
                elif message == MONITOR_DISARM and self._keypad:
                    self._keypad.set_armed(False)
                elif message == MONITOR_STOP:
                    break

            except Empty:
                pass

            if self._keypad and self._keypad.enabled:
                self._keypad.communicate()

                if int(time()) - last_press > 10 and presses:
                    presses = ""
                    self._logger.info("Cleared presses after 3 secs")

                key_pressed = self._keypad.get_last_key()
                if key_pressed in ("0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11"):
                    presses += key_pressed
                    last_press = time()
                elif key_pressed in ("away", "stay"):
                    last_press = time()
                    pass
                else:
                    # remove unknow codes from the list
                    try:
                        key_pressed = ""
                    except IndexError:
                        pass

                if presses:
                    self._logger.debug("Presses: %s", presses)
                key_pressed = None

                if models.hash_code(presses) in self._codes:
                    self._logger.debug("Code: %s", presses)
                    self._logger.info("Accepted code => disarming")
                    self._responses.put(MONITOR_DISARM)
                    # loopback action
                    self._commands.put(MONITOR_DISARM)
                    presses = ""
                elif len(presses) == 4:
                    self._logger.info("Invalid code")
                    self._keypad.set_error(True)
                    presses = ""
