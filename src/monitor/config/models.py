"""
This module defines the configuration dataclasses for the monitor.
"""

import os
from dataclasses import dataclass, field

from monitor.config.base import BaseConfig


@dataclass
class Subscription:
    alert_started: bool = False
    alert_stopped: bool = False
    power_outage_started: bool = False
    power_outage_stopped: bool = False


@dataclass
class SubscriptionsConfig(BaseConfig):
    OPTION_NAME = "notifications"
    SECTION_NAME = "subscriptions"

    call1: Subscription = None
    call2: Subscription = None
    sms1: Subscription = None
    sms2: Subscription = None
    email1: Subscription = None
    email2: Subscription = None

    def __post_init__(self):
        self.call1 = (
            Subscription(**self.call1)
            if isinstance(self.call1, dict)
            else (self.call1 or Subscription())
        )
        self.call2 = (
            Subscription(**self.call2)
            if isinstance(self.call2, dict)
            else (self.call2 or Subscription())
        )
        self.sms1 = (
            Subscription(**self.sms1)
            if isinstance(self.sms1, dict)
            else (self.sms1 or Subscription())
        )
        self.sms2 = (
            Subscription(**self.sms2)
            if isinstance(self.sms2, dict)
            else (self.sms2 or Subscription())
        )
        self.email1 = (
            Subscription(**self.email1)
            if isinstance(self.email1, dict)
            else (self.email1 or Subscription())
        )
        self.email2 = (
            Subscription(**self.email2)
            if isinstance(self.email2, dict)
            else (self.email2 or Subscription())
        )


@dataclass
class LocationConfig(BaseConfig):
    """
    Configuration for the location information, the source of the notifications.
    """

    OPTION_NAME = "system"
    SECTION_NAME = "location"

    name: str = None
    latitude: float = None
    longitude: float = None
    country: str = None
    city: str = None
    state: str = None
    zip_code: str = None
    address: str = None
    description: str = None
    contact_name: str = None
    contact_phone: str = None
    contact_email: str = None


@dataclass
class SMTPConfig(BaseConfig):
    OPTION_NAME = "notifications"
    SECTION_NAME = "smtp"

    enabled: bool = False
    smtp_hostname: str = None
    smtp_port: int = None
    smtp_username: str = None
    smtp_password: str = None
    email_address_1: str = None
    email_address_2: str = None


@dataclass
class GSMConfig(BaseConfig):
    OPTION_NAME = "notifications"
    SECTION_NAME = "gsm"

    enabled: bool = False
    pin_code: str = None
    phone_number_1: str = None
    phone_number_2: str = None


@dataclass
class DyndnsConfig(BaseConfig):
    OPTION_NAME = "network"
    SECTION_NAME = "dyndns"

    username: str = None
    password: str = None
    hostname: str = None
    provider: str = None
    restrict_host: str = False
    certbot_email: str = None


@dataclass
class SyrenConfig(BaseConfig):
    OPTION_NAME = "syren"
    SECTION_NAME = "timing"

    silent: bool | None = False
    delay: int = 0
    duration: int = 0


@dataclass
class SSHConfig(BaseConfig):
    OPTION_NAME = "network"
    SECTION_NAME = "access"

    service_enabled: bool = True
    restrict_local_network: bool = False
    password_authentication_enabled: bool = True


@dataclass
class AlertSensitivityConfig(BaseConfig):
    OPTION_NAME = "alert"
    SECTION_NAME = "sensitivity"

    monitor_period: int | None = None
    monitor_threshold: int | None = None


@dataclass
class MQTTConnection(BaseConfig):
    OPTION_NAME = "mqtt"
    SECTION_NAME = "connection"

    enabled: bool = True
    external: bool = False


@dataclass
class MQTTConfigInternalRead(BaseConfig):
    """
    Access configuration to the internal MQTT broker for reading by other services.
    """

    OPTION_NAME = "mqtt"
    SECTION_NAME = "internal_read"

    hostname: str = "arpi.local"
    port: int = 8883
    username: str = "argus_reader"
    password: str = field(default_factory=lambda: os.environ.get("ARGUS_READER_MQTT_PASSWORD"))
    tls_enabled: bool = True
    tls_insecure: bool = True


@dataclass
class MQTTConfigInternalPublish(BaseConfig):
    """
    Access configuration to the internal MQTT broker for publishing by the monitor.
    """

    OPTION_NAME = "mqtt"
    SECTION_NAME = "internal_publish"

    hostname: str = "localhost"
    port: int = 8883
    username: str = "argus"
    password: str = field(default_factory=lambda: os.environ.get("ARGUS_MQTT_PASSWORD"))
    tls_enabled: bool = True
    tls_insecure: bool = True


@dataclass
class MQTTConfigExternalPublish(BaseConfig):
    """
    Access configuration to the external MQTT broker for publishing.
    """

    OPTION_NAME = "mqtt"
    SECTION_NAME = "external_publish"

    hostname: str = None
    port: int = 8883
    username: str = None
    password: str = field(default_factory=lambda: os.environ.get("ARGUS_MQTT_PASSWORD"))
    tls_enabled: bool = True
    tls_insecure: bool = True
