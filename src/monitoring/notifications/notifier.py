import contextlib
import json
import logging
import os
import smtplib
from queue import Empty, Queue
from smtplib import SMTPException
from threading import Thread
from time import sleep

from models import Option
from monitoring.broadcast import Broadcaster
from constants import LOG_NOTIFIER, MONITOR_STOP, MONITOR_UPDATE_CONFIG, THREAD_NOTIFIER
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
Messages

{
    "type": "alert_started" / "alert_stopped",
    "id": "alert id",
    "sensors": ["Sensor name"],
    "time": "start time",
}


"""

ALERT_STARTED = "alert_started"
ALERT_STOPPED = "alert_stopped"

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
        cls._notifications.put({
                "type": ALERT_STARTED,
                "id": alert_id,
                "sensors": sensors,
                "time": time,
                "retry": 0
        })

    @classmethod
    def notify_alert_stopped(cls, alert_id, time):
        logging.getLogger(LOG_NOTIFIER).debug("Message adding (stop): %s", alert_id)
        cls._notifications.put({
            "type": ALERT_STOPPED,
            "id": alert_id,
            "time": time,
            "retry": 0
        })

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
                message = self._actions.get(timeout=Notifier.RETRY_WAIT)

            if message is not None:
                # handle monitoring and notification actions
                if message["action"] == MONITOR_STOP:
                    break
                elif message["action"] == MONITOR_UPDATE_CONFIG:
                    self._options = self.get_options()
                    self._gsm.destroy()
                    self._gsm = GSM()
                    self._gsm.setup()

            if len(self._notifications.queue) > 0:
                notification = self._notifications.queue[0]
                if self.send_message(notification):
                    # send succeeded
                    self._notifications.queue.popleft()
                else:
                    # send failed
                    notification["retry"] += 1
                    if notification["retry"] >= Notifier.MAX_RETRY:
                        self._logger.debug(
                            "Deleted message after max retry (%s): %s", Notifier.MAX_RETRY, self._notifications.pop(0)
                        )

        self._db_session.close()
        self._logger.info("Notifier stopped")

    def get_options(self):
        options = {}
        for section_name in ("email", "gsm", "subscriptions"):
            section = self._db_session.query(Option).filter_by(name="notifications", section=section_name).first()
            options[section_name] = json.loads(section.value) if section else ""
        self._logger.debug(f"Notifier loaded subscriptions: {options}")
        return options

    def send_message(self, message):
        self._logger.info("Sending message: %s", message)
        success = False
        has_subscription = False
        try:
            if self._options["subscriptions"]["sms"][message["type"]]:
                if message["type"] == ALERT_STARTED:
                    has_subscription = True
                    success |= self.notify_alert_started_SMS(message)
                elif message["type"] == ALERT_STOPPED:
                    has_subscription = True
                    success |= self.notify_alert_stopped_SMS(message)

            if self._options["subscriptions"]["email"][message["type"]]:
                if message["type"] == ALERT_STARTED:
                    has_subscription = True
                    success |= self.notify_alert_started_email(message)
                elif message["type"] == ALERT_STOPPED:
                    has_subscription = True
                    success |= self.notify_alert_stopped_email(message)
        except (KeyError, TypeError) as error:
            self._logger.info("Failed to send message: '%s'! (%s)", message, error)
        except Exception:
            self._logger.exception("Sending message failed!")

        return success or not has_subscription

    def notify_alert_started_SMS(self, message):
        return self.notify_SMS(ALERT_STARTED_SMS.format(**message))

    def notify_alert_stopped_SMS(self, message):
        return self.notify_SMS(ALERT_STOPPED_SMS.format(**message))

    def notify_alert_started_email(self, message):
        return self.notify_email("Alert started", ALERT_STARTED_EMAIL.format(**message))

    def notify_alert_stopped_email(self, message):
        return self.notify_email("Alert stopped", ALERT_STOPPED_EMAIL.format(**message))

    def notify_SMS(self, message):
        return self._gsm.sendSMS(self._options["gsm"]["phone_number"], message)

    def notify_email(self, subject, content):
        self._logger.info("Sending email ...")
        try:
            server = smtplib.SMTP("smtp.gmail.com:587")
            server.ehlo()
            server.starttls()
            server.login(self._options["email"]["smtp_username"], self._options["email"]["smtp_password"])

            message = "Subject: {}\n\n{}".format(subject, content).encode(encoding="utf_8", errors="strict")
            server.sendmail(from_addr="info@argus", to_addrs=self._options["email"]["email_address"], msg=message)
            server.quit()
        except SMTPException as error:
            self._logger.error("Can't send email %s ", error)
            return False

        self._logger.info("Sent email")
        return True
