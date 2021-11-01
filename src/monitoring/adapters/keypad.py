import logging
import os
from threading import Thread
from queue import Empty
from time import time

from sqlalchemy.engine import create_engine
from sqlalchemy.engine.url import URL
from sqlalchemy.orm.session import sessionmaker
from sqlalchemy.sql.sqltypes import Boolean

import models
from monitoring.adapters.keypads.base import Action, KeypadBase
from monitoring.adapters.mock.keypad import MockKeypad
from monitoring.constants import (
    LOG_ADKEYPAD,
    MONITOR_ARM_AWAY,
    MONITOR_ARM_STAY,
    MONITOR_DISARM,
    MONITOR_REGISTER_CARD,
    MONITOR_STOP,
    MONITOR_UPDATE_KEYPAD,
    THREAD_KEYPAD,
)
from monitoring.socket_io import send_card_registered

if os.uname()[4][:3] == "arm":
    from monitoring.adapters.keypads.dsc import DSCKeypad
    from monitoring.adapters.keypads.wiegand import WiegandKeypad

COMMUNICATION_PERIOD = 0.5  # sec


class KeypadHandler(Thread):
    # pins
    DATA_PIN0 = 6
    DATA_PIN1 = 5
    DATA_PIN2 = 0

    def __init__(self, commands, responses):
        super(KeypadHandler, self).__init__(name=THREAD_KEYPAD)
        self._logger = logging.getLogger(LOG_ADKEYPAD)
        self._commands = commands
        self._responses = responses
        self._codes = []
        self._keypad: KeypadBase = None

    def set_type(self, type):
        # check if running on Raspberry
        if os.uname()[4][:3] != "arm":
            self._keypad = MockKeypad(KeypadHandler.DATA_PIN1, KeypadHandler.DATA_PIN0)
            type = "MOCK"
        elif type == "DSC":
            self._keypad = DSCKeypad(KeypadHandler.DATA_PIN1, KeypadHandler.DATA_PIN0)
        elif type == "WIEGAND":
            self._keypad = WiegandKeypad(KeypadHandler.DATA_PIN0, KeypadHandler.DATA_PIN1, KeypadHandler.DATA_PIN2)
        elif type is None:
            self._logger.debug("Keypad removed")
            self._keypad = None
        else:
            self._logger.error("Unknown keypad type: %s", type)
        self._logger.debug("Keypad created type: %s", type)

    def get_database_session(self):
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
        return Session()

    def configure(self):
        self._logger.debug("Configure keypad")
        db_session = self.get_database_session()
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
        register_card = False
        while True:
            try:
                self._logger.debug("Wait for command...")
                message = self._commands.get(timeout=COMMUNICATION_PERIOD)
                self._logger.debug("Command: %s", message)

                if message == MONITOR_UPDATE_KEYPAD:
                    self._logger.info("Updating keypad")
                    self.configure()
                    last_press = int(time())
                elif message == MONITOR_REGISTER_CARD:
                    register_card = True
                elif message in (MONITOR_ARM_AWAY, MONITOR_ARM_STAY) and self._keypad:
                    self._logger.info("Keypad armed")
                    self._keypad.set_armed(True)
                elif message == MONITOR_DISARM and self._keypad:
                    self._logger.info("Keypad disarmed")
                    self._keypad.set_armed(False)
                elif message == MONITOR_STOP:
                    break
            except Empty:
                pass

            if self._keypad and self._keypad.enabled:
                self._keypad.communicate()

                # delete pressed keys after 10 secs
                if int(time()) - last_press > 10 and presses:
                    presses = ""
                    self._logger.info("Cleared presses after 10 secs")

                # check the action from the keypad
                action = self._keypad.last_action()
                if action == Action.KEY:
                    presses += self._keypad.get_last_key()
                    self._logger.debug("Presses: '%s'", presses)
                    last_press = time()
                    if len(presses) == 4:
                        self.handle_code(presses)
                        presses = ""
                elif action == Action.CARD:
                    if register_card:
                        self.register_card(self._keypad.get_card())
                        register_card = False
                    else:
                        self.handle_card(self._keypad.get_card())
                elif action == Action.FUNCTION:
                    # function = self._keypad.get_function()
                    pass
                elif action is not None:
                    self._logger.error("Uknown keypad action: %s", action)

    def handle_code(self, presses):
        if self.check_code(presses):
            self._logger.debug("Code accepted: %s", presses)
            self._logger.info("Accepted code => disarming")
            self._responses.put(MONITOR_DISARM)
            # loopback action
            self._commands.put(MONITOR_DISARM)
        else:
            self._logger.info("Invalid code")
            self._keypad.set_error(True)

    def handle_card(self, card, register=False):
        self._logger.debug("Card: %s", card)
        if not self._keypad.get_armed():
            return

        if self.check_card(card):
            self._logger.info("Accepted card => disarming")
            self._responses.put(MONITOR_DISARM)
            # loopback action
            self._commands.put(MONITOR_DISARM)
        else:
            self._logger.info("Unknown card")
            self._keypad.set_error(True)

    def check_code(self, code) -> Boolean:
        db_session = self.get_database_session()
        users = db_session.query(models.User).all()
        access_codes = [user.fourkey_code for user in users]
        db_session.close()

        return models.hash_code(code) in access_codes

    def check_card(self, card) -> Boolean:
        db_session = self.get_database_session()
        users = db_session.query(models.User).all()
        cards = [card.card for user in users for card in user.cards]
        db_session.close()
        self._logger.debug("Card %s/%s in %s", card, models.hash_code(card), cards)
        return models.hash_code(card) in cards

    def register_card(self, card):
        """Find the first user from the database with valid card registration"""
        db_session = self.get_database_session()
        users = db_session.query(models.User).filter(models.User.card_registration_expiry >= 'NOW()').all()
        if users:
            card = models.Card(card, users[0].id)
            self._logger.debug("Card created: %s", card)
            db_session.add(card)
            users[0].card_registration_expiry = None
            db_session.commit()
            send_card_registered()
