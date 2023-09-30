import contextlib
import json
import logging
import os

from dataclasses import asdict
from datetime import datetime
from queue import Empty, Queue
from threading import Thread
from time import sleep, time

from models import Option
from monitor.broadcast import Broadcaster
from constants import LOG_NOTIFIER, MONITOR_STOP, MONITOR_UPDATE_CONFIG, THREAD_NOTIFIER
from monitor.adapters.smtp import SMTPSender
from monitor.database import Session
from monitor.notifications.notification import Notification, NotificationType


# check if running on Raspberry
if os.environ.get("USE_SIMULATOR", "false").lower() == "false":
    from monitor.adapters.gsm import GSM
else:
    from monitor.adapters.mock.gsm import GSM


"""
options = {
    "subscriptions": {
        "sms": {
            ALERT_STARTED: True,
            ALERT_STOPPED: True,
            WEEKLY_REPORT: False
        },
        "email": {
            ALERT_STARTED: False,
            ALERT_STOPPED: False,
            WEEKLY_REPORT: False
        }
    },
    "smtp": {
        'smtp_username': 'smtp_username',
        'smtp_password': 'smtp_password',
        'email_address': 'email_address'
    },
    "gsm": {
        "phone_number": "phone number"
    }
}
"""


class Notifier(Thread):
    DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"

    MAX_RETRY = 5
    RETRY_WAIT = 30

    _notifications = Queue()

    # TODO: consider instead of calling these methods to be notified with actions
    # and retrieve information from the database
    @classmethod
    def notify_alert_started(cls, alert_id, sensors, time: datetime):
        logging.getLogger(LOG_NOTIFIER).debug("Message adding alert start id: %s", alert_id)
        cls._notifications.put(
            Notification(
                type=NotificationType.ALERT_STARTED,
                id=alert_id,
                sensors=sensors,
                time=time.strftime(Notifier.DATETIME_FORMAT)
            )
        )

    @classmethod
    def notify_alert_stopped(cls, alert_id, time):
        logging.getLogger(LOG_NOTIFIER).debug("Message adding alert stop id: %s", alert_id)
        cls._notifications.put(
            Notification(
                type=NotificationType.ALERT_STOPPED,
                id=alert_id,
                sensors=None,
                time=time.strftime(Notifier.DATETIME_FORMAT)
            )
        )

    @classmethod
    def notify_power_outage_started(cls, time):
        logging.getLogger(LOG_NOTIFIER).debug("Message adding power outage start")
        cls._notifications.put(
            Notification(
                type=NotificationType.POWER_OUTAGE_STARTED,
                id=None,
                sensors=None,
                time=time.strftime(Notifier.DATETIME_FORMAT)
            )
        )

    @classmethod
    def notify_power_outage_stopped(cls, time):
        logging.getLogger(LOG_NOTIFIER).debug("Message adding power outage end")
        cls._notifications.put(
            Notification(
                type=NotificationType.POWER_OUTAGE_STOPPED,
                id=None,
                sensors=None,
                time=time.strftime(Notifier.DATETIME_FORMAT))
            )

    @staticmethod
    def send_test_email():
        logging.getLogger(LOG_NOTIFIER).debug("Sending test email")
        options = Notifier.load_options()
        smtp = SMTPSender(
            hostname=options["smtp"].get("smtp_hostname"),
            port=options["smtp"].get("smtp_port"),
            username=options["smtp"].get("smtp_username"),
            password=options["smtp"].get("smtp_password")
        )

        messages = {}
        if not smtp.setup():
            messages["connection"] = False
            return False, messages

        if options["smtp"].get("email1_address"):
            messages["email1"] = smtp.send_email(
                to_address=options["smtp"].get("email1_address"),
                subject="ArPI Test Email",
                content="This is a test email from the ArPI Home Security system!"
            )

        if options["smtp"].get("email2_address"):
            messages["email2"] = smtp.send_email(
                to_address=options["smtp"].get("email2_address"),
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
            pin_code=options["gsm"].get("pin_code"),
            port=os.environ["GSM_PORT"],
            baud=os.environ["GSM_PORT_BAUD"]
        )

        messages = {}
        if not gsm.setup():
            messages["connection"] = False
            return False, messages

        messages["phone1"] = gsm.send_SMS(options["gsm"].get("phone_number"), "ArPI Test Message")

        gsm.destroy()
        return True, messages

    def __init__(self, broadcaster: Broadcaster):
        super(Notifier, self).__init__(name=THREAD_NOTIFIER)
        self._actions = Queue()
        self._broadcaster = broadcaster
        self._logger = logging.getLogger(LOG_NOTIFIER)
        self._gsm = None
        self._smtp = None
        self._options = None

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
        if self._options["gsm"].get("enabled", False):
            self._logger.debug("GSM enabled")
            self._gsm = GSM(
                pin_code=self._options["gsm"].get("pin_code"),
                port=os.environ["GSM_PORT"],
                baud=os.environ["GSM_PORT_BAUD"]
            )
            self._gsm.setup()
        else:
            self._logger.debug("GSM disabled")
            self.destroy_gsm()

        # we will try to connect to verify the connection
        # but after a long time the connection is not available
        # so we need to re-connect
        self.destroy_smtp()
        if self._options["smtp"].get("enabled", False):
            self._logger.debug("SMTP enabled")
            self._smtp = SMTPSender(
                hostname=self._options["smtp"].get("smtp_hostname"),
                port=self._options["smtp"].get("smtp_port"),
                username=self._options["smtp"].get("smtp_username"),
                password=self._options["smtp"].get("smtp_password"),
            )
            self._smtp.setup()
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
    def load_options():
        db_session = Session()
        options = {}
        for section_name in ("smtp", "gsm", "subscriptions"):
            section = (
                db_session.query(Option)
                .filter_by(name="notifications", section=section_name)
                .first()
            )
            options[section_name] = json.loads(section.value) if section else {}

        db_session.close()
        return options

    def process_notifications(self):
        notification: Notification = self._notifications.get(block=False)

        if notification.last_try + Notifier.RETRY_WAIT < time():
            self.send_message(notification)
            notification.last_try = time()
            notification.retry += 1

        if not notification.processed:
            # send failed
            if notification.retry >= Notifier.MAX_RETRY:
                self._logger.debug("Deleted message after retry(%s): %s", Notifier.MAX_RETRY, notification)
            else:
                # sending message failed put back to message queue
                self._notifications.put(notification)

    def send_message(self, notification: Notification):
        self._logger.info("Sending message: %s", notification)
        try:
            self.notify_SMS(notification)
            self.notify_email(notification)
        except (KeyError, TypeError) as error:
            self._logger.exception("Failed to send message: '%s'! (%s)", notification, error)
        except Exception:
            self._logger.exception("Sending message failed!")

    def notify_SMS(self, notification: Notification):
        template = notification.get_sms_template()
        if (self._options["subscriptions"].get("sms", {}).get(notification.type, False) and
                notification.sms_sent == False and
                self._gsm):
            notification.sms_sent = \
                self._gsm.send_SMS(self._options["gsm"].get("phone_number"), template.format(**asdict(notification)))
        else:
            notification.sms_sent = None

    def notify_email(self, notification: Notification):
        template = notification.get_email_template()
        if (self._options["subscriptions"].get("email1", {}).get(notification.type, False) and
                notification.email1_sent is False and
                self._smtp):
            notification.email1_sent = self._smtp.send_email(
                to_address=self._options["smtp"].get("email1_address"),
                subject=notification.get_email_subject(),
                content=template.format(**asdict(notification))
            )
        else:
            notification.email1_sent = None

        if (self._options["subscriptions"].get("email2", {}).get(notification.type, False) and
                notification.email1_sent is False and
                self._smtp):
            notification.email2_sent = self._smtp.send_email(
                to_address=self._options["smtp"].get("email2_address"),
                subject=notification.get_email_subject(),
                content=template.format(**asdict(notification))
            )
        else:
            notification.email2_sent = None
