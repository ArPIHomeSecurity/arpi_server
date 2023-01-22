import contextlib
import json
import logging
import os
import smtplib
from dataclasses import asdict
from queue import Empty, Queue
from smtplib import SMTPException
from threading import Thread
from time import sleep, time

from models import Option
from monitoring.broadcast import Broadcaster
from constants import LOG_NOTIFIER, MONITOR_STOP, MONITOR_UPDATE_CONFIG, THREAD_NOTIFIER
from monitoring.notifications.notification import Notification, NotificationType
from monitoring.database import Session
from monitoring.notifications.templates import (
    ALERT_STARTED_EMAIL,
    ALERT_STARTED_SMS,
    ALERT_STOPPED_EMAIL,
    ALERT_STOPPED_SMS,
)

# check if running on Raspberry
if os.uname()[4][:3] == "arm":
    from monitoring.adapters.gsm import GSM
else:
    from monitoring.adapters.mock.gsm import GSM



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
    "email": {
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
    MAX_RETRY = 5
    RETRY_WAIT = 30

    _notifications = Queue()

    # TODO: consider instead of calling these methods to be notified with actions
    # and retrieve information from the database
    @classmethod
    def notify_alert_started(cls, alert_id, sensors, time):
        logging.getLogger(LOG_NOTIFIER).debug("Message adding (start): %s", alert_id)
        cls._notifications.put(
            Notification(type=NotificationType.ALERT_STARTED, id=alert_id, sensors=sensors, time=time)
        )

    @classmethod
    def notify_alert_stopped(cls, alert_id, time):
        logging.getLogger(LOG_NOTIFIER).debug("Message adding (stop): %s", alert_id)
        cls._notifications.put(Notification(type=NotificationType.ALERT_STOPPED, id=alert_id, sensors=None, time=time))

    def __init__(self, broadcaster: Broadcaster):
        super(Notifier, self).__init__(name=THREAD_NOTIFIER)
        self._actions = Queue()
        self._broadcaster = broadcaster
        self._logger = logging.getLogger(LOG_NOTIFIER)
        self._gsm = GSM()
        self._options = None
        self._db_session = None

        self._broadcaster.register_queue(id(self), self._actions)
        self._logger.info("Notifier created")

    def run(self):
        self._logger.info("Notifier started...")

        # --------------------------------------------------------------
        # Workaround to avoid hanging of keypad process on create_engine
        sleep(5)
        # --------------------------------------------------------------
        self._db_session = Session()
        self._options = self.get_options()
        self._logger.info("Subscription configuration: %s", self._options["subscriptions"])

        self._gsm.setup()
        while True:
            message = None
            with contextlib.suppress(Empty):
                message = self._actions.get(timeout=1)

            if message is not None:
                # handle monitoring and notification actions
                if message["action"] == MONITOR_STOP:
                    break
                elif message["action"] == MONITOR_UPDATE_CONFIG:
                    self._options = self.get_options()
                    self._gsm.destroy()
                    self._gsm = GSM()
                    self._gsm.setup()

            if not self._notifications.empty():
                self.process_notifications()

        self._db_session.close()
        self._logger.info("Notifier stopped")

    def get_options(self):
        options = {}
        for section_name in ("email", "gsm", "subscriptions"):
            section = (
                self._db_session.query(Option)
                .filter_by(name="notifications", section=section_name)
                .first()
            )
            options[section_name] = json.loads(section.value) if section else ""
        self._logger.debug(f"Notifier loaded subscriptions: {options}")
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
        self._logger.debug("Options: %s", self._options)
        try:
            if notification.type == NotificationType.ALERT_STARTED:
                self.notify_alert_started_SMS(notification)
                self.notify_alert_started_email(notification)
            elif notification.type == NotificationType.ALERT_STOPPED:
                self.notify_alert_stopped_SMS(notification)
                self.notify_alert_stopped_email(notification)
            else:
                self._logger.error("Unknown notification type!")

        except (KeyError, TypeError) as error:
            self._logger.exception("Failed to send message: '%s'! (%s)", notification, error)
        except Exception:
            self._logger.exception("Sending message failed!")

    def notify_alert_started_SMS(self, notification: Notification):
        if self._options["subscriptions"]["sms"][NotificationType.ALERT_STARTED] and notification.sms_sent == False:
            notification.sms_sent = self.notify_SMS(ALERT_STARTED_SMS.format(**asdict(notification)))
        else:
            notification.sms_sent = None 

    def notify_alert_stopped_SMS(self, notification: Notification):
        if self._options["subscriptions"]["sms"][NotificationType.ALERT_STOPPED] and notification.sms_sent == False:
            notification.sms_sent = self.notify_SMS(ALERT_STOPPED_SMS.format(**asdict(notification)))
        else:
            notification.sms_sent = None

    def notify_alert_started_email(self, notification: Notification):
        if self._options["subscriptions"]["email1"][NotificationType.ALERT_STARTED] and notification.email1_sent == False:
            notification.email1_sent = self.notify_email(
                self._options["email"]["email1_address"], "Alert started", ALERT_STARTED_EMAIL.format(**asdict(notification))
            )
        else:
            notification.email1_sent = None

        if self._options["subscriptions"]["email2"][NotificationType.ALERT_STARTED] and notification.email1_sent == False:
            notification.email2_sent = self.notify_email(
                self._options["email"]["email2_address"], "Alert started", ALERT_STARTED_EMAIL.format(**asdict(notification))
            )
        else:
            notification.email2_sent = None

    def notify_alert_stopped_email(self, notification: Notification):
        if self._options["subscriptions"]["email1"][NotificationType.ALERT_STOPPED] and notification.email2_sent == False:
            notification.email1_sent = self.notify_email(
                self._options["email"]["email1_address"], "Alert stopped", ALERT_STOPPED_EMAIL.format(**asdict(notification))
            )
        else:
            notification.email1_sent = None

        if self._options["subscriptions"]["email2"][NotificationType.ALERT_STOPPED] and notification.email2_sent == False:
            notification.email2_sent = self.notify_email(
                self._options["email"]["email2_address"], "Alert stopped", ALERT_STOPPED_EMAIL.format(**asdict(notification))
            )
        else:
            notification.email2_sent = None

    def notify_SMS(self, notification):
        return self._gsm.sendSMS(self._options["gsm"]["phone_number"], notification)

    def notify_email(self, to_address, subject, content):
        self._logger.info("Sending email to %s ...", to_address)
        try:
            server = smtplib.SMTP(f"{self._options['email']['smtp_hostname']}:{self._options['email']['smtp_port']}")
            server.ehlo()
            server.starttls()
            server.login(
                self._options["email"]["smtp_username"], self._options["email"]["smtp_password"]
            )

            message = f"Subject: {subject}\n\n{content}".encode(encoding="utf_8", errors="strict")
            server.sendmail(
                from_addr="alert@arpi-security.info",
                to_addrs=to_address,
                msg=message,
            )
            server.quit()
        except SMTPException as error:
            self._logger.error("Can't send email! Error: %s ", error)
            return False

        self._logger.info("Sent email")
        return True
