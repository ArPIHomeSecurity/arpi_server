import contextlib
import logging
import os
from datetime import datetime
from queue import Empty, Queue
from threading import Thread
from time import sleep, time

from monitor.actions import (
    MonitorDisarmCommand,
    MonitorStopCommand,
    MonitorUpdateConfigCommand,
)
from monitor.adapters.gsm import CallResult, CallType
from monitor.adapters.smtp import SMTPSender
from monitor.broadcast import Broadcaster
from monitor.config.models import GSMConfig, LocationConfig, SMTPConfig, SubscriptionsConfig
from monitor.database import create_database_session
from monitor.notifications.notification import Notification, NotificationType
from utils.constants import (
    LOG_NOTIFIER,
    THREAD_NOTIFIER,
)
from utils.queries import get_user_with_access_code

logger = logging.getLogger(LOG_NOTIFIER)

# check if running with simulator
if os.environ.get("USE_SIMULATOR", "false").lower() == "false":
    from monitor.adapters.gsm import GSM
else:
    from monitor.adapters.mock.gsm import GSM


class Notifier(Thread):
    DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"

    MAX_RETRY = 5
    RETRY_WAIT = 10

    _notifications = Queue()

    # TODO: consider instead of calling these methods to be notified with actions
    # and retrieve information from the database
    @classmethod
    def notify_alert_started(cls, alert_id, sensors, start_time: datetime):
        logger.debug("Message adding alert start id: %s", alert_id)
        cls._notifications.put(
            Notification(
                type=NotificationType.ALERT_STARTED,
                id=alert_id,
                sensors=sensors,
                time=start_time.strftime(Notifier.DATETIME_FORMAT),
            )
        )

    @classmethod
    def notify_alert_stopped(cls, alert_id, stop_time):
        logger.debug("Message adding alert stop id: %s", alert_id)
        cls._notifications.put(
            Notification(
                type=NotificationType.ALERT_STOPPED,
                id=alert_id,
                sensors=None,
                time=stop_time.strftime(Notifier.DATETIME_FORMAT),
            )
        )

    @classmethod
    def notify_power_outage_started(cls, start_time):
        logger.debug("Message adding power outage start")
        cls._notifications.put(
            Notification(
                type=NotificationType.POWER_OUTAGE_STARTED,
                id=None,
                sensors=None,
                time=start_time.strftime(Notifier.DATETIME_FORMAT),
            )
        )

    @classmethod
    def notify_power_outage_stopped(cls, stop_time):
        logger.debug("Message adding power outage end")
        cls._notifications.put(
            Notification(
                type=NotificationType.POWER_OUTAGE_STOPPED,
                id=None,
                sensors=None,
                time=stop_time.strftime(Notifier.DATETIME_FORMAT),
            )
        )

    @classmethod
    def notify_local_network_issue_started(cls, start_time):
        logger.debug("Message adding local network issue start")
        cls._notifications.put(
            Notification(
                type=NotificationType.LOCAL_NETWORK_ISSUE_STARTED,
                id=None,
                sensors=None,
                time=start_time.strftime(Notifier.DATETIME_FORMAT),
            )
        )

    @classmethod
    def notify_local_network_issue_stopped(cls, stop_time):
        logger.debug("Message adding local network issue end")
        cls._notifications.put(
            Notification(
                type=NotificationType.LOCAL_NETWORK_ISSUE_STOPPED,
                id=None,
                sensors=None,
                time=stop_time.strftime(Notifier.DATETIME_FORMAT),
            )
        )

    @classmethod
    def notify_internet_issue_started(cls, start_time):
        logger.debug("Message adding internet issue start")
        cls._notifications.put(
            Notification(
                type=NotificationType.INTERNET_ISSUE_STARTED,
                id=None,
                sensors=None,
                time=start_time.strftime(Notifier.DATETIME_FORMAT),
            )
        )

    @classmethod
    def notify_internet_issue_stopped(cls, stop_time):
        logger.debug("Message adding internet issue end")
        cls._notifications.put(
            Notification(
                type=NotificationType.INTERNET_ISSUE_STOPPED,
                id=None,
                sensors=None,
                time=stop_time.strftime(Notifier.DATETIME_FORMAT),
            )
        )

    @staticmethod
    def send_test_email():
        logger.debug("Sending test email")
        smtp_config = SMTPConfig.load_config()
        smtp = SMTPSender(
            hostname=smtp_config.smtp_hostname,
            port=smtp_config.smtp_port,
            username=smtp_config.smtp_username,
            password=smtp_config.smtp_password,
        )

        messages = {}
        if not smtp.setup():
            messages["connection"] = False
            return False, messages

        location = LocationConfig.load_config().name
        notification = Notification(
            type=NotificationType.TEST_NOTIFICATION,
            id=None,
            location=location,
            time=datetime.now().strftime(Notifier.DATETIME_FORMAT),
        )
        if smtp_config.email_address_1:
            messages["email1"] = smtp.send_email(
                to_address=smtp_config.email_address_1,
                subject=notification.get_email_subject(),
                content=notification.get_email_content(),
            )

        if smtp_config.email_address_2:
            messages["email2"] = smtp.send_email(
                to_address=smtp_config.email_address_2,
                subject=notification.get_email_subject(),
                content=notification.get_email_content(),
            )

        smtp.destroy()
        return True, messages

    @staticmethod
    def send_test_sms():
        logger.debug("Sending test SMS")
        gsm_config = GSMConfig.load_config()
        gsm = GSM(
            pin_code=gsm_config.pin_code,
            port=os.environ["GSM_PORT"],
            baud=os.environ["GSM_PORT_BAUD"],
        )

        messages = {}
        if not gsm.setup():
            messages["connection"] = False
            return False, messages

        notification = Notification(
            type=NotificationType.TEST_NOTIFICATION,
            id=None,
            sensors=None,
            time=datetime.now().strftime(Notifier.DATETIME_FORMAT),
        )
        if gsm_config.phone_number_1:
            messages["phone1"] = gsm.send_SMS(
                gsm_config.phone_number_1, notification.get_sms_content()
            )

        if gsm_config.phone_number_2:
            messages["phone2"] = gsm.send_SMS(
                gsm_config.phone_number_2, notification.get_sms_content()
            )

        gsm.destroy()
        return True, messages

    @staticmethod
    def get_sms_messages():
        logger.debug("Getting SMS messages")
        gsm_config = GSMConfig.load_config()
        gsm = GSM(
            pin_code=gsm_config.pin_code,
            port=os.environ["GSM_PORT"],
            baud=os.environ["GSM_PORT_BAUD"],
        )

        if not gsm.setup():
            return False, []

        messages = []
        for sms in gsm.get_sms_messages() or []:
            messages.append(
                {
                    "idx": sms.index,
                    "number": sms.number,
                    "time": sms.time.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                    "text": sms.text,
                }
            )

        gsm.destroy()
        return True, messages

    @staticmethod
    def delete_sms_message(message_id):
        logger.debug("Deleting SMS messages")
        gsm_config = GSMConfig.load_config()
        gsm = GSM(
            pin_code=gsm_config.pin_code,
            port=os.environ["GSM_PORT"],
            baud=os.environ["GSM_PORT_BAUD"],
        )

        if not gsm.setup():
            return False

        result = gsm.delete_sms_message(message_id)

        gsm.destroy()
        return result

    @staticmethod
    def make_test_call():
        logger.debug("Doing test call")
        gsm_config = GSMConfig.load_config()
        gsm = GSM(
            pin_code=gsm_config.pin_code,
            port=os.environ["GSM_PORT"],
            baud=os.environ["GSM_PORT_BAUD"],
        )

        messages = {}
        if not gsm.setup():
            messages["connection"] = False
            return False, messages

        if gsm_config.phone_number_1:
            call_result = gsm.call(gsm_config.phone_number_1, CallType.TEST)
            logger.info("Test call to phone 1 result: %s", call_result)
            messages["phone1"] = call_result == CallResult.ANSWERED

        if gsm_config.phone_number_2:
            call_result = gsm.call(gsm_config.phone_number_2, CallType.TEST)
            logger.info("Test call to phone 2 result: %s", call_result)
            messages["phone2"] = call_result == CallResult.ANSWERED

        gsm.destroy()
        return True, messages

    def __init__(self, broadcaster: Broadcaster):
        super().__init__(name=THREAD_NOTIFIER)
        self._actions = Queue()
        self._gsm = None
        self._smtp = None
        self._gsm_config: GSMConfig = None
        self._smtp_config: SMTPConfig = None
        self._subscriptions: SubscriptionsConfig = None

        self._broadcaster = broadcaster
        self._broadcaster.register_queue(id(self), self._actions)
        logger.info("Notifier created")

    def run(self):
        logger.info("Notifier started...")

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
                match message:
                    case MonitorStopCommand():
                        break
                    case MonitorUpdateConfigCommand():
                        self.setup_connections()

            if not self._notifications.empty():
                self.process_notifications()

        logger.info("Notifier stopped")

    def setup_connections(self):
        self._gsm_config = GSMConfig.load_config()
        self._smtp_config = SMTPConfig.load_config()
        self._subscriptions = SubscriptionsConfig.load_config()

        self.destroy_gsm()
        if self._gsm_config.enabled:
            logger.debug("GSM enabled")
            self._gsm = GSM(
                pin_code=self._gsm_config.pin_code,
                port=os.environ["GSM_PORT"],
                baud=os.environ["GSM_PORT_BAUD"],
            )
        else:
            logger.debug("GSM disabled")
            self.destroy_gsm()

        # we will try to connect to verify the connection
        # but after a long time the connection is not available
        # so we need to re-connect
        self.destroy_smtp()
        if self._smtp_config.enabled:
            logger.debug("SMTP enabled")
            self._smtp = SMTPSender(
                hostname=self._smtp_config.smtp_hostname,
                port=self._smtp_config.smtp_port,
                username=self._smtp_config.smtp_username,
                password=self._smtp_config.smtp_password,
            )
        else:
            logger.debug("SMTP disabled")
            self.destroy_smtp()

    def destroy_gsm(self):
        if self._gsm:
            self._gsm.destroy()
            self._gsm = None

    def destroy_smtp(self):
        if self._smtp:
            self._smtp.destroy()
            self._smtp = None

    def process_notifications(self):
        notification: Notification = self._notifications.get(block=False)

        # check elapsed time since last try
        if notification.last_try + Notifier.RETRY_WAIT < time():
            self.execute_notification(notification)
            notification.last_try = time()
            notification.retry += 1

        if notification.processed:
            logger.debug("Processed notification: %s", notification)
            return

        # send failed
        if notification.retry >= Notifier.MAX_RETRY:
            # stop retrying
            logger.debug("Deleted message after retry(%s): %s", Notifier.MAX_RETRY, notification)
        else:
            # sending message failed put back to message queue
            self._notifications.put(notification)

    def handle_call_feedback(self, feedback: str) -> bool:
        with create_database_session() as db_session:
            user = get_user_with_access_code(db_session, feedback)
            if user:
                logger.info("Disarming based on dmtf code of user %s", user.name)
                self._broadcaster.send_message(message=MonitorDisarmCommand(user_id=user.id))
                return True
            else:
                logger.debug("No user found for feedback...")

            user = get_user_with_access_code(db_session, feedback)
            if user:
                logger.info("Disarming based on dmtf code of user %s", user.name)
                self._broadcaster.send_message(message=MonitorDisarmCommand(user_id=user.id))
                return True
            else:
                logger.debug("No user found for feedback...")

            return False

    def execute_notification(self, notification: Notification):
        logger.info("Sending message: %s", notification)

        # execute all actions in priority order
        # TODO: consider moving it to the database to allow dynamic configuration
        alert_chain = [
            Notifier.send_email_1,
            Notifier.send_email_2,
            Notifier.send_SMS_1,
            Notifier.send_SMS_2,
            Notifier.call_1,
            Notifier.call_2,
        ]
        for action in alert_chain:
            try:
                action(self, notification)
            except (KeyError, TypeError) as error:
                logger.exception("Failed to send message: '%s'! (%s)", notification, error)
            except Exception:
                logger.exception("Sending message failed!")

    def send_email_1(self, notification: Notification):
        if self._smtp and getattr(self._subscriptions.email1, notification.type, False):
            if notification.email1_sent is False:
                notification.email1_sent = self._smtp.send_email(
                    to_address=self._smtp_config.email_address_1,
                    subject=notification.get_email_subject(),
                    content=notification.get_email_content(),
                )
        else:
            notification.email1_sent = None

    def send_email_2(self, notification: Notification):
        if self._smtp and getattr(self._subscriptions.email2, notification.type, False):
            if notification.email2_sent is False:
                notification.email2_sent = self._smtp.send_email(
                    to_address=self._smtp_config.email_address_2,
                    subject=notification.get_email_subject(),
                    content=notification.get_email_content(),
                )
        else:
            notification.email2_sent = None

    def send_SMS_1(self, notification: Notification):
        if self._gsm and getattr(self._subscriptions.sms1, notification.type, False):
            if notification.sms_sent1 is False:
                notification.sms_sent1 = self._gsm.send_SMS(
                    self._gsm_config.phone_number_1, notification.get_sms_content()
                )
        else:
            notification.sms_sent1 = None

    def send_SMS_2(self, notification: Notification):
        if self._gsm and getattr(self._subscriptions.sms2, notification.type, False):
            if notification.sms_sent2 is False:
                notification.sms_sent2 = self._gsm.send_SMS(
                    self._gsm_config.phone_number_2, notification.get_sms_content()
                )
        else:
            notification.sms_sent2 = None

    def call_1(self, notification: Notification):
        if not self._gsm:
            notification.call1_sent = None
            return

        # check if the call is enabled for this notification type
        if not getattr(self._subscriptions.call1, notification.type, False):
            # we don't need to call the first number
            notification.call1_sent = None
            return

        # check if the call was already sent
        if notification.call1_sent is False:
            call_status, _ = self._gsm.call(self._gsm_config.phone_number_1, CallType.ALERT)
            # if the user acknowledged the call then we don't need to call the second number
            if call_status == CallResult.ACKNOWLEDGED:
                logger.info("Phone 1 acknowledged the alert")
                # call to first number was successful
                notification.call1_sent = True
                # we don't need to call the second number
                notification.call2_sent = (
                    None if notification.call2_sent is False else notification.call2_sent
                )

    def call_2(self, notification: Notification):
        if not self._gsm:
            notification.call2_sent = None
            return

        # check if the call is enabled for this notification type
        if not getattr(self._subscriptions.call2, notification.type, False):
            # we don't need to call the second number
            notification.call2_sent = None
            return

        if notification.call2_sent is False:
            call_status, _ = self._gsm.call(self._gsm_config.phone_number_2, CallType.ALERT)

            # if the user acknowledged the call then we don't need to call the first number
            if call_status == CallResult.ACKNOWLEDGED:
                logger.info("Phone 2 acknowledged the alert")
                # call to second number was successful
                notification.call2_sent = True
                # we don't need to call the first number
                notification.call1_sent = (
                    None if notification.call1_sent is False else notification.call1_sent
                )
