from dataclasses import dataclass


class NotificationType:
    ALERT_STARTED = "alert_started"
    ALERT_STOPPED = "alert_stopped"

@dataclass
class Notification:
    type: NotificationType
    id: int
    sensors: list[str]
    time: str
    retry: int = 0
    last_try: float = 0.0

    # True = sent, False = sending failed, None = no need to send (not subscribed)
    sms_sent: bool = False
    email1_sent: bool = False
    email2_sent: bool = False

    @property
    def processed(self):
        return (
            (self.sms_sent is None or self.sms_sent) and
            (self.email1_sent is None or self.email1_sent) and
            (self.email2_sent is None or self.email2_sent)
        )
