from dataclasses import dataclass
from typing import Optional, List

from monitor.notifications.templates import (
    ALERT_STARTED_EMAIL,
    ALERT_STARTED_SMS,
    ALERT_STOPPED_EMAIL,
    ALERT_STOPPED_SMS,
    POWER_OUTAGE_STARTED_EMAIL,
    POWER_OUTAGE_STARTED_SMS,
    POWER_OUTAGE_STOPPED_EMAIL,
    POWER_OUTAGE_STOPPED_SMS,
)


class NotificationType:
    ALERT_STARTED = "alert_started"
    ALERT_STOPPED = "alert_stopped"
    POWER_OUTAGE_STARTED = "power_outage_started"
    POWER_OUTAGE_STOPPED = "power_outage_stopped"


@dataclass
class Notification:
    type: NotificationType
    id: int
    sensors: List[str]
    time: str
    retry: int = 0
    last_try: float = 0.0

    # True = sent, False = sending failed, None = no need to send (not subscribed)
    sms_sent1: Optional[bool] = False
    sms_sent2: Optional[bool] = False
    email1_sent: Optional[bool] = False
    email2_sent: Optional[bool] = False

    def get_sms_template(self):
        mapping = {
            NotificationType.ALERT_STARTED: ALERT_STARTED_SMS,
            NotificationType.ALERT_STOPPED: ALERT_STOPPED_SMS,
            NotificationType.POWER_OUTAGE_STARTED: POWER_OUTAGE_STARTED_SMS,
            NotificationType.POWER_OUTAGE_STOPPED: POWER_OUTAGE_STOPPED_SMS,
        }

        try:
            return mapping[self.type]
        except KeyError:
            self._logger.error("Unknown notification type!")

    def get_email_template(self):
        mapping = {
            NotificationType.ALERT_STARTED: ALERT_STARTED_EMAIL,
            NotificationType.ALERT_STOPPED: ALERT_STOPPED_EMAIL,
            NotificationType.POWER_OUTAGE_STARTED: POWER_OUTAGE_STARTED_EMAIL,
            NotificationType.POWER_OUTAGE_STOPPED: POWER_OUTAGE_STOPPED_EMAIL,
        }

        return mapping[self.type]

    def get_email_subject(self):
        mapping = {
            NotificationType.ALERT_STARTED: "Alert started",
            NotificationType.ALERT_STOPPED: "Alert stopped",
            NotificationType.POWER_OUTAGE_STARTED: "Power outage started",
            NotificationType.POWER_OUTAGE_STOPPED: "Power outage stopped",
        }

        return mapping[self.type]

    @property
    def processed(self):
        return (
            (self.sms_sent1 is None or self.sms_sent1) and
            (self.sms_sent2 is None or self.sms_sent2) and
            (self.email1_sent is None or self.email1_sent) and
            (self.email2_sent is None or self.email2_sent)
        )
