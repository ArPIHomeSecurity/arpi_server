import contextlib
import logging
from datetime import datetime as dt
from queue import Empty, Queue
from threading import Thread
from time import sleep, time

from sqlalchemy import inspect

from monitor.actions import (
    MonitorArmAwayCommand,
    MonitorArmStayCommand,
    MonitorDisarmCommand,
    MonitoringAlertCommand,
    MonitoringAlertDelayCommand,
    MonitorRegisterCardCommand,
    MonitorStopCommand,
    MonitorUpdateKeypadCommand,
)
from monitor.adapters import V2BoardPin
from monitor.adapters.keypads import get_wiegand_keypad
from monitor.adapters.keypads.base import Action, Function, KeypadBase
from monitor.adapters.keypads.dsc import DSCKeypad
from monitor.broadcast import Broadcaster
from monitor.database import create_database_session, get_database_session
from monitor.socket_io import send_card_not_registered, send_card_registered
from monitor.storage import State, States
from utils.constants import (
    ARM_AWAY,
    ARM_STAY,
    LOG_ADKEYPAD,
    MONITORING_READY,
    THREAD_KEYPAD,
)
from utils.models import Arm, Card, Keypad, User
from utils.queries import get_alert_delay, get_arm_delay, get_arm_state, get_user_with_access_code

logger = logging.getLogger(LOG_ADKEYPAD)
COMMUNICATION_PERIOD = 0.2  # sec
CARD_REGISTRATION_EXPIRY = 120  # sec


class KeypadHandler(Thread):
    def __init__(self, broadcaster: Broadcaster):
        super().__init__(name=THREAD_KEYPAD)
        self._actions = Queue()
        self._codes = []
        self._keypad: KeypadBase = None

        self._broadcaster = broadcaster
        self._broadcaster.register_queue(id(self), self._actions)

    def configure(self):
        logger.debug("Configure keypad")
        with create_database_session() as db_session:
            keypad_settings = db_session.query(Keypad).first()

            if keypad_settings is None or not keypad_settings.enabled:
                self._keypad = None
                logger.info("Keypad removed")
                return

            if keypad_settings.type.name == "DSC":
                self._keypad = DSCKeypad(V2BoardPin.KEYBUS_PIN1, V2BoardPin.KEYBUS_PIN0)
                self._keypad.id = keypad_settings.id
            elif keypad_settings.type.name == "WIEGAND":
                self._keypad = get_wiegand_keypad()
                self._keypad.id = keypad_settings.id
            else:
                logger.error("Unknown keypad type: %s", keypad_settings.type.name)
            logger.debug("Keypad created type: %s", keypad_settings.type.name)

            # save the database keypad id
            self._keypad.id = keypad_settings.id
            self._keypad.initialise()

    def run(self):
        try:
            self.configure()

            self.communicate()
        except Exception:
            logger.exception("Keypad thread crashed!")

        if self._keypad:
            self._keypad.close()

        logger.info("Keypad handler stopped")

    def communicate(self):
        last_press = int(time())
        presses = ""
        register_card_start = None
        while True:
            with contextlib.suppress(Empty):
                logger.trace("Wait for command...")
                message = self._actions.get(timeout=COMMUNICATION_PERIOD)
                logger.debug("Command: %s", message)
                match message:
                    case MonitorUpdateKeypadCommand():
                        logger.info("Updating keypad")
                        self.configure()
                        last_press = int(time())
                    case MonitorRegisterCardCommand():
                        register_card_start = time()
                    case MonitorArmAwayCommand(use_delay=use_delay) if self._keypad:
                        self.arm_keypad(ARM_AWAY, use_delay)
                    case MonitorArmStayCommand(use_delay=use_delay) if self._keypad:
                        self.arm_keypad(ARM_STAY, use_delay)
                    case MonitoringAlertCommand() if self._keypad:
                        self._keypad.stop_delay()
                    case MonitoringAlertDelayCommand() if self._keypad:
                        self.alert_delay()
                    case MonitorDisarmCommand() if self._keypad:
                        # TODO: if area_id is provided check if the keypad is assigned to that area
                        # currently keypads are not assigned to areas

                        # temporary hack to delay processing the disarm
                        # the monitor thread needs time to update the database
                        sleep(0.5)
                        if States.get(State.MONITORING) == MONITORING_READY:
                            logger.info("Keypad disarmed: monitoring disarmed")
                            self._keypad.set_armed(False)
                            self._keypad.stop_delay()
                    case MonitorStopCommand():
                        break

            if register_card_start and time() - register_card_start > CARD_REGISTRATION_EXPIRY:
                register_card_start = None
                send_card_not_registered()

            if self._keypad is not None:
                self._keypad.communicate()

                # delete pressed keys after 10 secs
                if int(time()) - last_press > 10 and presses:
                    presses = ""
                    logger.info("Cleared presses after 10 secs")

                # check the action from the keypad
                action = self._keypad.last_action()
                if action == Action.KEY:
                    presses += self._keypad.get_last_key()
                    logger.trace("Presses: '%s'", presses)
                    last_press = time()
                    if len(presses) == 4:
                        self.handle_access_code(presses)
                        presses = ""
                elif action == Action.CARD:
                    if register_card_start is not None:
                        self.register_card(self._keypad.get_card())
                        register_card_start = None
                    else:
                        self.handle_card(self._keypad.get_card())
                elif action == Action.FUNCTION:
                    self.handle_function(self._keypad.get_function())
                elif action is not None:
                    logger.error("Unknown keypad action: %s", action)

    def arm_keypad(self, arm_type, use_delay):
        with create_database_session() as session:
            arm_delay = get_arm_delay(session, arm_type) if use_delay else 0
            logger.info("Arm with delay: %s / %s", arm_delay, arm_type)
            self._keypad.set_armed(True)

            # wait for the arm created in the database
            # synchronizing the two threads
            arm = None
            retries = 5
            while not arm and retries > 0:
                arm = session.query(Arm).filter_by(disarm=None).first()
                retries -= 1
                sleep(1)

            if not arm:
                logger.error("Arm not created")
                return

            logger.debug("Arm: %s", arm)
            if arm_delay is not None and arm_delay > 0:
                self._keypad.start_delay(arm.time, arm_delay)

    def alert_delay(self):
        with create_database_session() as session:
            arm_type = get_arm_state(session)
            alert_delay = get_alert_delay(session, arm_type)
            logger.info("Alert with delay: %s / %s", alert_delay, arm_type)

            # TODO: for now we don't have a reference time as for delayed arm
            # we need to add the alerts to the database
            if alert_delay and alert_delay > 0:
                self._keypad.start_delay(dt.now(), alert_delay)

    def handle_access_code(self, presses):
        user = get_user_with_access_code(get_database_session(), presses)
        if user:
            logger.debug("Code accepted: %s", presses)
            logger.info("Accepted code => disarming")
            self._broadcaster.send_message(
                message=MonitorDisarmCommand(user_id=user.id, keypad_id=self._keypad.id)
            )
        else:
            logger.debug("Invalid code")
            self._keypad.set_error(True)

    def handle_card(self, card):
        logger.debug("Card: %s", card)
        if not self._keypad.get_armed():
            return

        db_card = self.get_card_by_number(card)
        if db_card and db_card.enabled:
            logger.info("Accepted card => disarming")
            self._broadcaster.send_message(
                message=MonitorDisarmCommand(user_id=db_card.user_id, keypad_id=self._keypad.id)
            )
        else:
            logger.info("Unknown card")
            self._keypad.set_error(True)

    def handle_function(self, function: Function):
        logger.debug("Handling function: %s", function)
        if Function.AWAY == function:
            self._broadcaster.send_message(
                MonitorArmAwayCommand(keypad_id=self._keypad.id, use_delay=True)
            )
        elif Function.STAY == function:
            self._broadcaster.send_message(
                MonitorArmStayCommand(keypad_id=self._keypad.id, use_delay=True)
            )
        else:
            logger.error("Unknown function: %s", function)

    def get_card_by_number(self, card_number) -> Card | None:
        """
        Find the first card from the database matching the card number
        """
        with create_database_session() as db_session:
            users = db_session.query(User).all()

            cards = []
            for user in users:
                cards.extend(user.cards)

            for tmp_card in cards:
                if tmp_card.check_card(card_number):
                    return tmp_card

        return None

    def register_card(self, card_number):
        """
        Find the first user from the database with valid card registration

        Parameters
        card_number : str - card number to register
        """
        with create_database_session() as db_session:
            users = db_session.query(User).filter(User.card_registration_expiry >= "NOW()").all()
            if users:
                cards = db_session.query(Card).all()
                for tmp_card in cards:
                    if tmp_card.check_card(card_number):
                        # ensure any changes are committed
                        state = inspect(tmp_card)
                        if state.modified:
                            db_session.commit()

                        logger.info("Card already registered")
                        send_card_not_registered()
                        return

                card_number = Card(card_number, users[0].id)
                logger.debug("Card created: %s", card_number)
                db_session.add(card_number)
                users[0].card_registration_expiry = None
                db_session.commit()
                send_card_registered()
