"""
This module defines the configuration dataclasses for the monitor.
"""

import os
import re
from dataclasses import dataclass, field, is_dataclass

from monitor.config.registry import register_config_option


@dataclass
class Subscription:
    alert_started: bool = False
    alert_stopped: bool = False
    power_outage_started: bool = False
    power_outage_stopped: bool = False
    local_network_issue_started: bool = False
    local_network_issue_stopped: bool = False
    internet_issue_started: bool = False
    internet_issue_stopped: bool = False

    @classmethod
    def from_dict(cls, value):
        raise NotImplementedError(f"{cls.__name__} conversion not implemented")


@dataclass
class SubscriptionsConfig:
    OPTION_NAME = "notifications"
    SECTION_NAME = "subscriptions"

    call1: Subscription | dict = None
    call2: Subscription | dict = None
    sms1: Subscription | dict = None
    sms2: Subscription | dict = None
    email1: Subscription | dict = None
    email2: Subscription | dict = None

    def __post_init__(self):
        try:
            # try to create Subscription from dict if possible
            self.call1 = (
                Subscription(**self.call1) if isinstance(self.call1, dict) else Subscription()
            )
        except TypeError:
            # fallback to from_dict if TypeError occurs
            self.call1 = Subscription.from_dict(self.call1)

        try:
            self.call2 = (
                Subscription(**self.call2) if isinstance(self.call2, dict) else Subscription()
            )
        except TypeError:
            self.call2 = Subscription.from_dict(self.call2)

        try:
            self.sms1 = Subscription(**self.sms1) if isinstance(self.sms1, dict) else Subscription()
        except TypeError:
            self.sms1 = Subscription.from_dict(self.sms1)

        try:
            self.sms2 = Subscription(**self.sms2) if isinstance(self.sms2, dict) else Subscription()
        except TypeError:
            self.sms2 = Subscription.from_dict(self.sms2)

        try:
            self.email1 = (
                Subscription(**self.email1) if isinstance(self.email1, dict) else Subscription()
            )
        except TypeError:
            self.email1 = Subscription.from_dict(self.email1)

        try:
            self.email2 = (
                Subscription(**self.email2) if isinstance(self.email2, dict) else Subscription()
            )
        except TypeError:
            self.email2 = Subscription.from_dict(self.email2)

    @classmethod
    def from_dict(cls, value):
        raise NotImplementedError(f"{cls.__name__} conversion not implemented")


@dataclass
class LocationConfig:
    """
    Configuration for the location information, the source of the notifications.
    """

    OPTION_NAME = "system"
    SECTION_NAME = "location"

    @classmethod
    def from_dict(cls, value):
        raise NotImplementedError(f"{cls.__name__} conversion not implemented")

    name: str = None
    description: str = None
    latitude: float = None
    longitude: float = None
    country: str = None
    city: str = None
    state: str = None
    zip_code: str = None
    address: str = None
    contact_name: str = None
    contact_phone: str = None
    contact_email: str = None


@dataclass
class SMTPConfig:
    OPTION_NAME = "notifications"
    SECTION_NAME = "smtp"

    @classmethod
    def from_dict(cls, value):
        raise NotImplementedError(f"{cls.__name__} conversion not implemented")

    enabled: bool = False
    smtp_hostname: str = None
    smtp_port: int = None
    smtp_username: str = None
    smtp_password: str = None
    email_address_1: str = None
    email_address_2: str = None


@dataclass
class GSMConfig:
    OPTION_NAME = "notifications"
    SECTION_NAME = "gsm"

    @classmethod
    def from_dict(cls, value):
        raise NotImplementedError(f"{cls.__name__} conversion not implemented")

    enabled: bool = False
    pin_code: str = None
    phone_number_1: str = None
    phone_number_2: str = None


@dataclass
class SMSActionConfig:
    OPTION_NAME = "notifications"
    SECTION_NAME = "sms_action"

    @classmethod
    def from_dict(cls, value):
        raise NotImplementedError(f"{cls.__name__} conversion not implemented")

    enabled: bool = False
    check_phone_number: bool = True
    access_code_required: bool = True


@dataclass
class SMSCommandConfig:
    OPTION_NAME = "notifications"
    SECTION_NAME = "sms_command"

    @classmethod
    def from_dict(cls, value):
        raise NotImplementedError(f"{cls.__name__} conversion not implemented")

    case_sensitive: bool = False
    arm_away_command: str = "away"
    arm_stay_command: str = "stay"
    disarm_command: str = "disarm"


@dataclass
class DyndnsConfig:
    OPTION_NAME = "network"
    SECTION_NAME = "dyndns"

    @classmethod
    def from_dict(cls, value):
        raise NotImplementedError(f"{cls.__name__} conversion not implemented")

    username: str = None
    password: str = None
    hostname: str = None
    provider: str = None
    restrict_host: str = False
    certbot_email: str = None


@dataclass
class SyrenConfig:
    OPTION_NAME = "syren"
    SECTION_NAME = "timing"

    @classmethod
    def from_dict(cls, value):
        raise NotImplementedError(f"{cls.__name__} conversion not implemented")

    silent: bool | None = False
    delay: int = 0
    duration: int = 0


@dataclass
class SSHConfig:
    OPTION_NAME = "network"
    SECTION_NAME = "access"

    @classmethod
    def from_dict(cls, value):
        raise NotImplementedError(f"{cls.__name__} conversion not implemented")

    service_enabled: bool = True
    restrict_local_network: bool = False
    password_authentication_enabled: bool = True


@dataclass
class AlertSensitivityConfig:
    """
    Configuration for the alert sensitivity settings of the monitor.

    If period is set to None, the monitoring will alert immediately when the sensor is active.
    Can be overridden by the sensor's configuration.

    We measure the sensor's state for a period of time in a rolling window.
    If the sensor's state is active for more than the threshold value in the period,
    an alert will be triggered.

    threshold = (active_time / period) * 100
    """

    OPTION_NAME = "alert"
    SECTION_NAME = "sensitivity"

    @classmethod
    def from_dict(cls, value):
        raise NotImplementedError(f"{cls.__name__} conversion not implemented")

    monitor_period: int | None = None
    """
    The period in seconds for monitoring the sensor's state.
    """
    monitor_threshold: int | None = 100
    """
    The filling threshold for the sensor's state in percent.
    If the sensor's state is above this threshold, an alert will be triggered.
    """


# CA certificate used to verify the internal broker, installed next to the other
# configuration of the server. Overridable for setups with a differently placed CA.
DEFAULT_MQTT_CA_CERT = os.environ.get(
    "ARGUS_MQTT_CA_CERT", os.path.expanduser("~/.local/etc/arpi-server/certs/arpi_ca.crt")
)


@dataclass
class MQTTConnection:
    OPTION_NAME = "mqtt"
    SECTION_NAME = "connection"

    @classmethod
    def from_dict(cls, value):
        raise NotImplementedError(f"{cls.__name__} conversion not implemented")

    enabled: bool = True
    external: bool = False


@dataclass
class MQTTConfigInternalRead:
    """
    Access configuration to the internal MQTT broker for reading by other services.
    """

    OPTION_NAME = "mqtt"
    SECTION_NAME = "internal_read"

    @classmethod
    def from_dict(cls, value):
        raise NotImplementedError(f"{cls.__name__} conversion not implemented")

    hostname: str = os.environ.get("ARGUS_MQTT_HOSTNAME", "arpi.local")
    port: int = int(os.environ.get("ARGUS_MQTT_PORT", "8883"))
    username: str = "argus_reader"
    password: str = field(default_factory=lambda: os.environ.get("ARGUS_READER_MQTT_PASSWORD"))
    tls_enabled: bool = bool(os.environ.get("ARGUS_TLS_ENABLED", "true") == "true")
    # only turns off the hostname check, the certificate chain is still verified
    tls_insecure: bool = bool(os.environ.get("ARGUS_TLS_INSECURE", "true") == "true")
    ca_certs: str | None = DEFAULT_MQTT_CA_CERT


@dataclass
class MQTTConfigInternalControl:
    """
    Access configuration to the internal MQTT broker for external clients that also
    arm and disarm, in addition to reading the state.
    """

    OPTION_NAME = "mqtt"
    SECTION_NAME = "internal_control"

    @classmethod
    def from_dict(cls, value):
        raise NotImplementedError(f"{cls.__name__} conversion not implemented")

    hostname: str = field(default_factory=lambda: os.environ.get("ARGUS_MQTT_HOSTNAME", "arpi.local"))
    port: int = field(default_factory=lambda: int(os.environ.get("ARGUS_MQTT_PORT", "8883")))
    username: str = "argus_control"
    password: str = field(default_factory=lambda: os.environ.get("ARGUS_CONTROL_MQTT_PASSWORD"))
    tls_enabled: bool = field(default_factory=lambda: bool(os.environ.get("ARGUS_TLS_ENABLED", "true") == "true"))
    # only turns off the hostname check, the certificate chain is still verified
    tls_insecure: bool = field(default_factory=lambda: bool(os.environ.get("ARGUS_TLS_INSECURE", "true") == "true"))
    ca_certs: str | None = DEFAULT_MQTT_CA_CERT


@dataclass
class MQTTConfigInternalPublish:
    """
    Access configuration to the internal MQTT broker for publishing by the monitor.
    """

    OPTION_NAME = "mqtt"
    SECTION_NAME = "internal_publish"

    @classmethod
    def from_dict(cls, value):
        raise NotImplementedError(f"{cls.__name__} conversion not implemented")

    hostname: str = field(default_factory=lambda: os.environ.get("ARGUS_MQTT_HOSTNAME", "arpi.local"))
    port: int = field(default_factory=lambda: int(os.environ.get("ARGUS_MQTT_PORT", "8883")))
    username: str = "argus"
    password: str = field(default_factory=lambda: os.environ.get("ARGUS_MQTT_PASSWORD"))
    tls_enabled: bool = field(default_factory=lambda: bool(os.environ.get("ARGUS_TLS_ENABLED", "true") == "true"))
    # the internal broker is reached over a trusted network and is expected to have a
    # self signed certificate, so it is verified but the hostname check is turned off
    tls_insecure: bool = field(default_factory=lambda: bool(os.environ.get("ARGUS_TLS_INSECURE", "true") == "true"))
    ca_certs: str | None = DEFAULT_MQTT_CA_CERT


@dataclass
class MQTTConfigExternalPublish:
    """
    Access configuration to the external MQTT broker for publishing by the monitor.
    """

    OPTION_NAME = "mqtt"
    SECTION_NAME = "external_publish"

    @classmethod
    def from_dict(cls, value):
        raise NotImplementedError(f"{cls.__name__} conversion not implemented")

    hostname: str = field(default_factory=lambda: os.environ.get("ARGUS_MQTT_HOSTNAME", "arpi.local"))
    port: int = field(default_factory=lambda: int(os.environ.get("ARGUS_MQTT_PORT", "8883")))
    username: str = None
    password: str = field(default_factory=lambda: os.environ.get("ARGUS_MQTT_PASSWORD"))
    tls_enabled: bool = field(default_factory=lambda: bool(os.environ.get("ARGUS_TLS_ENABLED", "true") == "true"))
    tls_insecure: bool = field(default_factory=lambda: bool(os.environ.get("ARGUS_TLS_INSECURE", "true") == "true"))
    # no explicit CA means the system certificate store is used
    ca_certs: str | None = None


@dataclass
class ZigbeeCoordinatorConfig:
    """
    Configuration for the Zigbee coordinator.
    """

    OPTION_NAME = "zigbee"
    SECTION_NAME = "coordinator"

    @classmethod
    def from_dict(cls, value):
        raise NotImplementedError(f"{cls.__name__} conversion not implemented")

    enabled: bool = True
    serial_port: str | None = "/dev/ttyUSB0"
    baudrate: int = 115200


# automatically register all dataclass-based configuration options defined in this module
for config_option_class in list(globals().values()):
    if (
        isinstance(config_option_class, type)
        and config_option_class.__module__ == __name__
        and is_dataclass(config_option_class)
        and "OPTION_NAME" in config_option_class.__dict__
        and "SECTION_NAME" in config_option_class.__dict__
    ):
        register_config_option(config_option_class)
