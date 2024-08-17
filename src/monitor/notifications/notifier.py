import contextlib
import json
import logging
import os

from dataclasses import asdict, dataclass
from datetime import datetime
from queue import Empty, Queue
from threading import Thread
from time import sleep, time

from models import Option
from monitor.adapters.gsm import CALL_ACKNOWLEDGED, CallType
from monitor.broadcast import Broadcaster
from constants import LOG_NOTIFIER, MONITOR_DISARM, MONITOR_STOP, MONITOR_UPDATE_CONFIG, THREAD_NOTIFIER
from monitor.adapters.smtp import SMTPSender
from monitor.database import get_database_session
from monitor.notifications.notification import Notification, NotificationType
from tools.queries import get_user_with_access_code


# check if running on Raspberry
if os.environ.get("USE_SIMULATOR", "false").lower() == "false":
    from monitor.adapters.gsm import GSM
else:
    from monitor.adapters.mock.gsm import GSM


@dataclass
class Subscription:
    alert_started: bool = False
    alert_stopped: bool = False
    power_outage_started: bool = False
    power_outage_stopped: bool = False


@dataclass
class Subscriptions:
    """
    Table Option/notifications/subscriptions
    """
    call1: Subscription = None
    call2: Subscription = None
    sms1: Subscription = None
    sms2: Subscription = None
    email1: Subscription = None
    email2: Subscription = None

    def __post_init__(self):
        """
        Convert database data to Subscription object
        """
        self.call1 = Subscription(**self.call1) if self.call1 else Subscription()
        self.call2 = Subscription(**self.call2) if self.call2 else Subscription()
        self.sms1 = Subscription(**self.sms1) if self.sms1 else Subscription()
        self.sms2 = Subscription(**self.sms2) if self.sms2 else Subscription()
        self.email1 = Subscription(**self.email1) if self.email1 else Subscription()
        self.email2 = Subscription(**self.email2) if self.email2 else Subscription()


@dataclass
class SMTPOption:
    """
    Table Option/notifications/smtp
    """
    enabled: bool = False
    smtp_hostname: str = None
    smtp_port: int = None
    smtp_username: str = None
    smtp_password: str = None
    email_address_1: str = None
    email_address_2: str = None


@dataclass
class GSMOption:
    """
    Table Option/notifications/gsm
    """
    enabled: bool = False
    pin_code: str = None
    phone_number_1: str = None
    phone_number_2: str = None


@dataclass
class NotifierOptions:
    subscriptions: Subscriptions = None
    smtp: SMTPOption = None
    gsm: GSMOption = None


class Notifier(Thread):
    DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"

    MAX_RETRY = 5
    RETRY_WAIT = 10

    _notifications = Queue()

    # TODO: consider instead of calling these methods to be notified with actions
    # and retrieve information from the database
    @classmethod
    def notify_alert_started(cls, alert_id, sensors, start_time: datetime):
        logging.getLogger(LOG_NOTIFIER).debug("Message adding alert start id: %s", alert_id)
        cls._notifications.put(
            Notification(
                type=NotificationType.ALERT_STARTED,
                id=alert_id,
                sensors=sensors,
                time=start_time.strftime(Notifier.DATETIME_FORMAT)
            )
        )

    @classmethod
    def notify_alert_stopped(cls, alert_id, stop_time):
        logging.getLogger(LOG_NOTIFIER).debug("Message adding alert stop id: %s", alert_id)
        cls._notifications.put(
            Notification(
                type=NotificationType.ALERT_STOPPED,
                id=alert_id,
                sensors=None,
                time=stop_time.strftime(Notifier.DATETIME_FORMAT)
            )
        )

    @classmethod
    def notify_power_outage_started(cls, start_time):
        logging.getLogger(LOG_NOTIFIER).debug("Message adding power outage start")
        cls._notifications.put(
            Notification(
                type=NotificationType.POWER_OUTAGE_STARTED,
                id=None,
                sensors=None,
                time=start_time.strftime(Notifier.DATETIME_FORMAT)
            )
        )

    @classmethod
    def notify_power_outage_stopped(cls, stop_time):
        logging.getLogger(LOG_NOTIFIER).debug("Message adding power outage end")
        cls._notifications.put(
            Notification(
                type=NotificationType.POWER_OUTAGE_STOPPED,
                id=None,
                sensors=None,
                time=stop_time.strftime(Notifier.DATETIME_FORMAT))
            )

    @staticmethod
    def send_test_email():
        logging.getLogger(LOG_NOTIFIER).debug("Sending test email")
        options = Notifier.load_options()
        smtp = SMTPSender(
            hostname=options.smtp.smtp_hostname,
            port=options.smtp.smtp_port,
            username=options.smtp.smtp_username,
            password=options.smtp.smtp_password
        )

        messages = {}
        if not smtp.setup():
            messages["connection"] = False
            return False, messages

        if options.smtp.email_address_1:
            messages["email1"] = smtp.send_email(
                to_address=options.smtp.email_address_1,
                subject="ArPI Test Email",
                content="This is a test email from the ArPI Home Security system!"
            )

        if options.smtp.email_address_2:
            messages["email2"] = smtp.send_email(
                to_address=options.smtp.email_address_2,
                subject="ArPI Test Email",
                content="This is a test email from the ArPI Home Security system!"
            )

        smtp.destroy()
        return True, messages

    @staticmethod
    def send_test_sms():
        logging.getLogger(LOG_NOTIFIER).debug("Sending test SMS")
        options = Notifier.load_options()
        gsm = GSM(
            pin_code=options.gsm.pin_code,
            port=os.environ["GSM_PORT"],
            baud=os.environ["GSM_PORT_BAUD"]
        )

        messages = {}
        if not gsm.setup():
            messages["connection"] = False
            return False, messages

        if options.gsm.phone_number_1:
            messages["phone1"] = gsm.send_SMS(options.gsm.phone_number_1, "ArPI Test Message")

        if options.gsm.phone_number_2:
            messages["phone2"] = gsm.send_SMS(options.gsm.phone_number_2, "ArPI Test Message")

        gsm.destroy()
        return True, messages

    @staticmethod
    def get_sms_messages():
        logging.getLogger(LOG_NOTIFIER).debug("Getting SMS messages")
        options = Notifier.load_options()
        gsm = GSM(
            pin_code=options.gsm.pin_code,
            port=os.environ["GSM_PORT"],
            baud=os.environ["GSM_PORT_BAUD"]
        )

        if not gsm.setup():
            return False, []

        messages = []
        for sms in gsm.get_sms_messages() or []:
            messages.append({
                "idx": sms.index,
                "number": sms.number,
                "time": sms.time.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                "text": sms.text
            })

        gsm.destroy()
        return True, messages

    @staticmethod
    def delete_sms_message(message_id):
        logging.getLogger(LOG_NOTIFIER).debug("Deleting SMS messages")
        options = Notifier.load_options()
        gsm = GSM(
            pin_code=options.gsm.pin_code,
            port=os.environ["GSM_PORT"],
            baud=os.environ["GSM_PORT_BAUD"]
        )

        if not gsm.setup():
            return False

        result = gsm.delete_sms_message(message_id)

        gsm.destroy()
        return result

    @staticmethod
    def make_test_call():
        logging.getLogger(LOG_NOTIFIER).debug("Doing test call")
        options = Notifier.load_options()
        gsm = GSM(
            pin_code=options.gsm.pin_code,
            port=os.environ["GSM_PORT"],
            baud=os.environ["GSM_PORT_BAUD"]
        )

        messages = {}
        if not gsm.setup():
            messages["connection"] = False
            return False, messages

        if options.gsm.phone_number_1:
            messages["phone1"] = gsm.call(options.gsm.phone_number_1, CallType.TEST)

        if options.gsm.phone_number_2:
            messages["phone2"] = gsm.call(options.gsm.phone_number_2, CallType.TEST)

        gsm.destroy()
        return True, messages

    def __init__(self, broadcaster: Broadcaster):
        super(Notifier, self).__init__(name=THREAD_NOTIFIER)
        self._actions = Queue()
        self._broadcaster = broadcaster
        self._logger = logging.getLogger(LOG_NOTIFIER)
        self._gsm = None
        self._smtp = None
        self._options: NotifierOptions = None

        self._broadcaster.register_queue(id(self), self._actions)
        self._logger.info("Notifier created")

    def run(self):
        self._logger.info("Notifier started...")

        # --------------------------------------------------------------
        # Workaround to avoid hanging of keypad process on create_engine
        sleep(5)
        # --------------------------------------------------------------
        self.setup_connections()

        while True:
            message = None
            with contextlib.suppress(Empty):
                message = self._actions.get(timeout=1)

            if message is not None:
                # handle monitoring and notification actions
                if message["action"] == MONITOR_STOP:
                    break
                elif message["action"] == MONITOR_UPDATE_CONFIG:
                    self.setup_connections()

            if not self._notifications.empty():
                self.process_notifications()

        self._logger.info("Notifier stopped")

    def setup_connections(self):
        self._options = self.load_options()

        self.destroy_gsm()
        if self._options.gsm.enabled:
            self._logger.debug("GSM enabled")
            self._gsm = GSM(
                pin_code=self._options.gsm.pin_code,
                port=os.environ["GSM_PORT"],
                baud=os.environ["GSM_PORT_BAUD"]
            )
        else:
            self._logger.debug("GSM disabled")
            self.destroy_gsm()

        # we will try to connect to verify the connection
        # but after a long time the connection is not available
        # so we need to re-connect
        self.destroy_smtp()
        if self._options.smtp.enabled:
            self._logger.debug("SMTP enabled")
            self._smtp = SMTPSender(
                hostname=self._options.smtp.smtp_hostname,
                port=self._options.smtp.smtp_port,
                username=self._options.smtp.smtp_username,
                password=self._options.smtp.smtp_password,
            )
        else:
            self._logger.debug("SMTP disabled")
            self.destroy_smtp()

    def destroy_gsm(self):
        if self._gsm:
            self._gsm.destroy()
            self._gsm = None

    def destroy_smtp(self):
        if self._smtp:
            self._smtp.destroy()
            self._smtp = None

    @staticmethod
    def load_options() -> NotifierOptions:
        logger = logging.getLogger(LOG_NOTIFIER)
        db_session = get_database_session()
        sections = {
            "subscriptions": Subscriptions,
            "smtp": SMTPOption,
            "gsm": GSMOption
        }
        options = NotifierOptions()
        for section_name, section_class in sections.items():
            section = (
                db_session.query(Option)
                .filter_by(name="notifications", section=section_name)
                .first()
            )
            try:
                data = json.loads(section.value) if section else {}
                value = section_class(**data)
                setattr(options, section_name, value)
                logger.debug(
                    "Loaded options for section: %s => %s",
                    section_name,
                    getattr(options, section_name)
                )
            except (TypeError, json.JSONDecodeError) as error:
                logger.warning("Failed to load options for section: %s! %s", section_name, error)
                setattr(options, section_name, section_class())

        db_session.close()
        return options

    def process_notifications(self):
        notification: Notification = self._notifications.get(block=False)

        # check elapsed time since last try
        if notification.last_try + Notifier.RETRY_WAIT < time():
            self.execute_notification(notification)
            notification.last_try = time()
            notification.retry += 1

        if notification.processed:
            self._logger.debug("Processed notification: %s", notification)
            return

        # send failed
        if notification.retry >= Notifier.MAX_RETRY:
            # stop retrying
            self._logger.debug(
                "Deleted message after retry(%s): %s", Notifier.MAX_RETRY, notification
            )
        else:
            # sending message failed put back to message queue
            self._notifications.put(notification)

    def handle_call_feedback(self, feedback: str) -> bool:
        db_session = get_database_session()
        user = get_user_with_access_code(db_session, feedback)
        if user:
            self._logger.info("Disarming based on dmtf code of user %s", user.name)
            self._broadcaster.send_message(message={
                "action": MONITOR_DISARM,
                "user_id": user.id
            })
            db_session.close()
            return True
        else:
            self._logger.debug("No user found for feedback...")

        user = get_user_with_access_code(db_session, feedback)
        if user:
            self._logger.info("Disarming based on dmtf code of user %s", user.name)
            self._broadcaster.send_message(message={
                "action": MONITOR_DISARM,
                "user_id": user.id
            })
            db_session.close()
            return True
        else:
            self._logger.debug("No user found for feedback...")

        db_session.close()
        return False


    def execute_notification(self, notification: Notification):
        self._logger.info("Sending message: %s", notification)

        # execute all actions in priority order
        # TODO: consider moving it to the database to allow dynamic configuration
        alert_chain = [
            Notifier.send_email_1,
            Notifier.send_email_2,
            Notifier.send_SMS_1,
            Notifier.send_SMS_2,
            Notifier.call_1,
            Notifier.call_2
        ]
        for action in alert_chain:
            try:
                action(self, notification)
            except (KeyError, TypeError) as error:
                self._logger.exception("Failed to send message: '%s'! (%s)", notification, error)
            except Exception:
                self._logger.exception("Sending message failed!")

    def send_email_1(self, notification: Notification):
        if self._smtp and getattr(self._options.subscriptions.email1, notification.type, False):
            if notification.email1_sent is False:
                template = notification.get_email_template()
                notification.email1_sent = self._smtp.send_email(
                    to_address=self._options.smtp.email_address_1,
                    subject=notification.get_email_subject(),
                    content=template.format(**asdict(notification))
                )
        else:
            notification.email1_sent = None

    def send_email_2(self, notification: Notification):
        if self._smtp and getattr(self._options.subscriptions.email2, notification.type, False):
            if notification.email2_sent is False:
                template = notification.get_email_template()
                notification.email2_sent = self._smtp.send_email(
                    to_address=self._options.smtp.email_address_2,
                    subject=notification.get_email_subject(),
                    content=template.format(**asdict(notification))
                )
        else:
            notification.email2_sent = None

    def send_SMS_1(self, notification: Notification):
        if self._gsm and getattr(self._options.subscriptions.sms1, notification.type, False):
            if notification.sms_sent1 is False:
                template = notification.get_sms_template()
                notification.sms_sent1 = self._gsm.send_SMS(
                    self._options.gsm.phone_number_1,
                    template.format(**asdict(notification))
                )
        else:
            notification.sms_sent1 = None

    def send_SMS_2(self, notification: Notification):
        if self._gsm and getattr(self._options.subscriptions.sms2, notification.type, False):
            if notification.sms_sent2 is False:
                template = notification.get_sms_template()
                notification.sms_sent2 = self._gsm.send_SMS(
                    self._options.gsm.phone_number_2,
                    template.format(**asdict(notification))
                )
        else:
            notification.sms_sent2 = None

    def call_1(self, notification: Notification):
        if self._gsm and getattr(self._options.subscriptions.call1, notification.type, False):
            if notification.call1_sent is False:
                notification.call1_sent = self._gsm.call(
                    self._options.gsm.phone_number_1, CallType.ALERT
                )
                feedback = self._gsm.incoming_dtmf

                # if the user pressed 1 (acknowledge) then we don't need to call the second number
                if feedback == CALL_ACKNOWLEDGED:
                    self._logger.info("Phone 1 acknowledged the alert")
                    notification.call1_sent = True
                    notification.call2_sent = None
                elif feedback:
                    if self.handle_call_feedback(feedback):
                        notification.call2_sent = None

        else:
            notification.call1_sent = None

    def call_2(self, notification: Notification):
        if self._gsm and getattr(self._options.subscriptions.call2, notification.type, False):
            if notification.call2_sent is False:
                notification.call2_sent = self._gsm.call(
                    self._options.gsm.phone_number_2, CallType.ALERT
                )
                feedback = self._gsm.incoming_dtmf

                # if the user pressed 1 (acknowledge) then we don't need to call the second number
                self._logger.trace("Phone 2 feedback: %s", feedback)
                if feedback == CALL_ACKNOWLEDGED:
                    self._logger.info("Phone 2 acknowledged the alert")
                    notification.call2_sent = True
                    notification.call1_sent = None
                elif feedback:
                    if self.handle_call_feedback(feedback):
                        notification.call1_sent = None
        else:
            notification.call2_sent = None
