from dataclasses import dataclass
import logging
from typing import Optional, List

from utils.constants import LOG_NOTIFIER
from monitor.notifications.templates import (
    ALERT_STARTED_EMAIL,
    ALERT_STARTED_SMS,
    ALERT_STOPPED_EMAIL,
    ALERT_STOPPED_SMS,
    POWER_OUTAGE_STARTED_EMAIL,
    POWER_OUTAGE_STARTED_SMS,
    POWER_OUTAGE_STOPPED_EMAIL,
    POWER_OUTAGE_STOPPED_SMS,
    TEST_EMAIL,
    TEST_SMS,
)


class NotificationType:
    """Defines the types of notifications that can be sent to the user."""

    TEST_NOTIFICATION = "test_notification"
    ALERT_STARTED = "alert_started"
    ALERT_STOPPED = "alert_stopped"
    POWER_OUTAGE_STARTED = "power_outage_started"
    POWER_OUTAGE_STOPPED = "power_outage_stopped"


SEVERITY_MAPPING = {
    NotificationType.TEST_NOTIFICATION: "Test",
    NotificationType.ALERT_STARTED: "Alert",
    NotificationType.ALERT_STOPPED: "Alert",
    NotificationType.POWER_OUTAGE_STARTED: "Alert",
    NotificationType.POWER_OUTAGE_STOPPED: "Alert",
}


def get_email_subject(notification_type: str) -> Optional[str]:
    """
    Returns the email subject based on the notification type.

    The subject has two tags for filtering in the email client:
    * the source of the email
    * the severity of the email
    """
    system = "ArPI"
    severity = SEVERITY_MAPPING.get(notification_type, "Alert")

    mapping = {
        NotificationType.TEST_NOTIFICATION: f"[{system}] [{severity}] ArPI Test Email",
        NotificationType.ALERT_STARTED: f"[{system}] [{severity}] Alert started",
        NotificationType.ALERT_STOPPED: f"[{system}] [{severity}] Alert stopped",
        NotificationType.POWER_OUTAGE_STARTED: f"[{system}] [{severity}] Power outage started",
        NotificationType.POWER_OUTAGE_STOPPED: f"[{system}] [{severity}] Power outage stopped",
    }

    try:
        return mapping[notification_type]
    except KeyError:
        logging.getLogger(LOG_NOTIFIER).error("Unknown notification type!")

    return None


def get_email_template(notification_type: str) -> Optional[str]:
    """
    Returns the email template based on the notification type.
    """
    mapping = {
        NotificationType.TEST_NOTIFICATION: TEST_EMAIL,
        NotificationType.ALERT_STARTED: ALERT_STARTED_EMAIL,
        NotificationType.ALERT_STOPPED: ALERT_STOPPED_EMAIL,
        NotificationType.POWER_OUTAGE_STARTED: POWER_OUTAGE_STARTED_EMAIL,
        NotificationType.POWER_OUTAGE_STOPPED: POWER_OUTAGE_STOPPED_EMAIL,
    }

    try:
        return mapping[notification_type]
    except KeyError:
        logging.getLogger(LOG_NOTIFIER).error("Unknown notification type!")

    return None


def get_sms_template(notification_type: str) -> Optional[str]:
    """
    Returns the SMS template based on the notification type.
    """
    mapping = {
        NotificationType.TEST_NOTIFICATION: TEST_SMS,
        NotificationType.ALERT_STARTED: ALERT_STARTED_SMS,
        NotificationType.ALERT_STOPPED: ALERT_STOPPED_SMS,
        NotificationType.POWER_OUTAGE_STARTED: POWER_OUTAGE_STARTED_SMS,
        NotificationType.POWER_OUTAGE_STOPPED: POWER_OUTAGE_STOPPED_SMS,
    }

    try:
        return mapping[notification_type]
    except KeyError:
        logging.getLogger(LOG_NOTIFIER).error("Unknown notification type!")

    return None


@dataclass
class Notification:
    """
    Represents a notification to be sent to the user.
    """

    type: NotificationType
    id: int
    sensors: List[str]
    time: str
    retry: int = 0
    last_try: float = 0.0

    # True = sent, False = not sent, None = no need to send (not subscribed)
    sms_sent1: Optional[bool] = False
    sms_sent2: Optional[bool] = False
    email1_sent: Optional[bool] = False
    email2_sent: Optional[bool] = False
    call1_sent: Optional[bool] = False
    call2_sent: Optional[bool] = False

    def get_sms_template(self) -> Optional[str]:
        """
        Returns the SMS template based on the notification type.
        """
        return get_sms_template(self.type)

    def get_email_template(self) -> Optional[str]:
        """
        Returns the email template based on the notification type.
        """
        return get_email_template(self.type)

    def get_email_subject(self) -> Optional[str]:
        """
        Returns the email subject based on the notification type.

        The subject has two tags for filtering in the email client:
        * the source of the email
        * the severity of the email
        """
        return get_email_subject(self.type)

    @property
    def processed(self) -> bool:
        """
        Returns True if all notifications have been processed (sent or not needed).
        """
        return (
            (self.sms_sent1 is None or self.sms_sent1)
            and (self.sms_sent2 is None or self.sms_sent2)
            and (self.email1_sent is None or self.email1_sent)
            and (self.email2_sent is None or self.email2_sent)
            and (self.call1_sent is None or self.call1_sent)
            and (self.call2_sent is None or self.call2_sent)
        )
