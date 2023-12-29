import contextlib
import logging
import os

from datetime import datetime as dt
from queue import Empty, Queue
from threading import Thread
from time import time

from sqlalchemy.engine import create_engine
from sqlalchemy.engine.url import URL
from sqlalchemy.orm.session import sessionmaker
from sqlalchemy.sql.sqltypes import Boolean

from models import Arm, Card, Keypad, User, hash_code
from monitor.storage import States
from monitor.adapters import KEYBUS_PIN0, KEYBUS_PIN1, KEYBUS_PIN2
from monitor.adapters.keypads.base import Action, Function, KeypadBase
from monitor.adapters.mock.keypad import MockKeypad
from monitor.broadcast import Broadcaster
from constants import (
    ARM_AWAY,
    ARM_STAY,
    LOG_ADKEYPAD,
    MONITOR_ARM_AWAY,
    MONITOR_ARM_STAY,
    MONITOR_DISARM,
    MONITOR_REGISTER_CARD,
    MONITOR_STOP,
    MONITOR_UPDATE_KEYPAD,
    MONITORING_ALERT,
    MONITORING_ALERT_DELAY,
    THREAD_KEYPAD,
)
from monitor.socket_io import send_card_registered
from tools.queries import get_alert_delay, get_arm_delay

if os.environ.get("USE_SIMULATOR", "false").lower() == "false":
    from monitor.adapters.keypads.dsc import DSCKeypad
    from monitor.adapters.keypads.wiegand import WiegandKeypad

COMMUNICATION_PERIOD = 0.2  # sec


class KeypadHandler(Thread):
    def __init__(self, broadcaster: Broadcaster):
        super(KeypadHandler, self).__init__(name=THREAD_KEYPAD)
        self._logger = logging.getLogger(LOG_ADKEYPAD)
        self._actions = Queue()
        self._codes = []
        self._keypad: KeypadBase = None
        self._db_session = None
        self._broadcaster = broadcaster

        self._broadcaster.register_queue(id(self), self._actions)

    def get_database_session(self):
        if not self._db_session:
            url = None
            try:
                url = URL.create(
                    drivername="postgresql+psycopg2",
                    username=os.environ.get("DB_USER", None),
                    password=os.environ.get("DB_PASSWORD", None),
                    host=os.environ.get("DB_HOST", None),
                    port=os.environ.get("DB_PORT", None),
                    database=os.environ.get("DB_SCHEMA", None)
                )
            except KeyError:
                self._logger.error("Database connnection not configured")
                return

            engine = create_engine(url)
            Session = sessionmaker(bind=engine)
            self._db_session = Session()

        return self._db_session

    def configure(self):
        self._logger.debug("Configure keypad")
        db_session = self.get_database_session()
        keypad_settings = db_session.query(Keypad).first()

        if keypad_settings is None or not keypad_settings.enabled:
            self._keypad = None
            self._logger.info("Keypad removed")
            db_session.close()
            return

        # check if running on Raspberry
        if os.environ.get("USE_SIMULATOR", "true").lower() == "true":
            self._keypad = MockKeypad(KEYBUS_PIN1, KEYBUS_PIN0)
            keypad_settings.type.name = "MOCK"
            # see data.py -=> env_test_01
            keypad = db_session.query(Keypad).filter_by(type_id=3).first()
            if keypad:
                self._keypad._id = keypad.id
        elif keypad_settings.type.name == "DSC":
            self._keypad = DSCKeypad(KEYBUS_PIN1, KEYBUS_PIN0)
            self._keypad._id = keypad_settings.id
        elif keypad_settings.type.name == "WIEGAND":
            self._keypad = WiegandKeypad(KEYBUS_PIN0, KEYBUS_PIN1, KEYBUS_PIN2)
            self._keypad._id = keypad_settings.id
        else:
            self._logger.error("Unknown keypad type: %s", keypad_settings.type.name)
        self._logger.debug("Keypad created type: %s", keypad_settings.type.name)
        db_session.close()

        # save the database keypad id
        self._keypad.id = keypad_settings.id
        self._keypad.initialise()

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
            with contextlib.suppress(Empty):
                self._logger.debug("Wait for command...")
                message = self._actions.get(timeout=COMMUNICATION_PERIOD)
                self._logger.debug("Command: %s", message)

                if message["action"] == MONITOR_UPDATE_KEYPAD:
                    self._logger.info("Updating keypad")
                    self.configure()
                    last_press = int(time())
                elif message["action"] == MONITOR_REGISTER_CARD:
                    register_card = True
                elif message["action"] == MONITOR_ARM_AWAY and self._keypad:
                    self.arm_keypad(ARM_AWAY, message.get("delay", True))
                elif message["action"] == MONITOR_ARM_STAY and self._keypad:
                    self.arm_keypad(ARM_STAY, message.get("delay", True))
                elif message["action"] == MONITORING_ALERT and self._keypad:
                    self._keypad.stop_delay()
                elif message["action"] == MONITORING_ALERT_DELAY and self._keypad:
                    self.alert_delay()
                elif message["action"] == MONITOR_DISARM and self._keypad:
                    self._logger.info("Keypad disarmed")
                    self._keypad.set_armed(False)
                    self._keypad.stop_delay()
                elif message["action"] == MONITOR_STOP:
                    break

            if self._keypad is not None:
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
                        self.handle_access_code(presses)
                        presses = ""
                elif action == Action.CARD:
                    if register_card:
                        self.register_card(self._keypad.get_card())
                        register_card = False
                    else:
                        self.handle_card(self._keypad.get_card())
                elif action == Action.FUNCTION:
                    self.handle_function(self._keypad.get_function())
                elif action is not None:
                    self._logger.error("Unknown keypad action: %s", action)

    def arm_keypad(self, arm_type, delay):
        arm_delay = get_arm_delay(self.get_database_session(), arm_type) if delay else 0
        self._logger.info("Arm with delay: %s / %s", arm_delay, arm_type)
        self._keypad.set_armed(True)

        # wait for the arm created in the database
        # synchronizing the two threads
        arm = None
        while not arm:
            arm = self.get_database_session().query(Arm).filter_by(disarm=None).first()
        self._logger.debug("Arm: %s", arm)

        if arm_delay is not None and arm_delay > 0:
            self._keypad.start_delay(arm.time, arm_delay)

    def alert_delay(self):
        arm_type = States.get(States.ARM_STATE)
        alert_delay = get_alert_delay(self.get_database_session(), arm_type)
        self._logger.info("Alert with delay: %s / %s", alert_delay, arm_type)

        # TODO: for now we don't have a reference time as for delayed arm
        # we need to add the alerts to the database
        if alert_delay and alert_delay > 0:
            self._keypad.start_delay(dt.now(), alert_delay)

    def handle_access_code(self, presses):
        user = self.get_user_by_access_code(presses)
        if user:
            self._logger.debug("Code accepted: %s", presses)
            self._logger.info("Accepted code => disarming")
            self._broadcaster.send_message(message={
                "action": MONITOR_DISARM,
                "user_id": user.id,
                "keypad_id": self._keypad._id
            })
        else:
            self._logger.info("Invalid code")
            self._keypad.set_error(True)

    def handle_card(self, card):
        self._logger.debug("Card: %s", card)
        if not self._keypad.get_armed():
            return

        db_card = self.get_card_by_number(card)
        if db_card and db_card.enabled:
            self._logger.info("Accepted card => disarming")
            self._broadcaster.send_message(message={
                "action": MONITOR_DISARM,
                "user_id": db_card.user_id,
                "keypad_id": self._keypad.id
            })
        else:
            self._logger.info("Unknown card")
            self._keypad.set_error(True)

    def handle_function(self, function: Function):
        self._logger.debug("Handling function: %s", function)
        if Function.AWAY == function:
            self._broadcaster.send_message({"action": MONITOR_ARM_AWAY, "keypad_id": self._keypad._id})
        elif Function.STAY == function:
            self._broadcaster.send_message({"action": MONITOR_ARM_STAY, "keypad_id": self._keypad._id})
        else:
            self._logger.error("Unknown function: %s", function)

    def get_user_by_access_code(self, code) -> Boolean:
        db_session = self.get_database_session()
        users = db_session.query(User).all()
        db_session.close()

        code_hash = hash_code(code)
        self._logger.debug("User access code %s/%s in %s", code, code_hash, [u.fourkey_code for u in users])
        return next(filter(lambda u: u.fourkey_code == code_hash, users), None)

    def get_card_by_number(self, number) -> Card:
        db_session = self.get_database_session()
        users = db_session.query(User).all()

        cards = []
        for user in users:
            cards.extend(user.cards)

        db_session.close()
        card_hash = hash_code(number)
        self._logger.debug("Card %s/%s in %s", number, card_hash, [c.code for c in cards])
        return next(filter(lambda c: c.code == card_hash, cards), None)

    def register_card(self, card):
        """Find the first user from the database with valid card registration"""
        db_session = self.get_database_session()
        users = db_session.query(User).filter(User.card_registration_expiry >= 'NOW()').all()
        if users:
            card = Card(card, users[0].id)
            self._logger.debug("Card created: %s", card)
            db_session.add(card)
            users[0].card_registration_expiry = None
            db_session.commit()
            send_card_registered()
