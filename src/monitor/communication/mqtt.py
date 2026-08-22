import json
import logging
import os
import socket
import ssl
from collections.abc import Callable
from enum import Enum
from unicodedata import normalize

import paho.mqtt.client as mqtt

from monitor.config.models import (
    MQTTConfigExternalPublish,
    MQTTConfigInternalPublish,
    MQTTConnection,
)
from utils.constants import ARM_AWAY, ARM_DISARM, ARM_MIXED, ARM_STAY, LOG_MQTT

logger = logging.getLogger(LOG_MQTT)


def sanitize(name):
    """
    Convert name to [a-zA-Z0-9_-] for home assistant
    """
    name = normalize("NFKD", name)
    return "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in name).lower()


class SensorState(Enum):
    OFF = "OFF"
    ON = "ON"


# Mapping of sensor types to Home Assistant device classes
# See: SensorType values in data.py
SENSOR_DEVICE_MAPPING = {
    "Motion": "motion",
    "Tamper": "tamper",
    "Open": "opening",
    "Break": "glass_break",
}

ARPI_PREFIX = "arpi/"
SENSOR_TOPIC_PREFIX = f"{ARPI_PREFIX}binary_sensor/"
AREA_TOPIC_PREFIX = f"{ARPI_PREFIX}alarm_control_panel/"

SYSTEM_TOPIC_NAME = "system"
COMMAND_SUFFIX = "state/set"
COMMAND_TOPIC_FILTER = f"{AREA_TOPIC_PREFIX}+/{COMMAND_SUFFIX}"

# command payload template for home assistant: it fills in the action and the code
COMMAND_TEMPLATE = '{"action": "{{ action }}", "code": "{{ code }}"}'

# home assistant state of a panel while its exit delay is running
ARMING_PAYLOAD = "arming"

HA_ACTION_MAPPING = {
    "ARM_AWAY": ARM_AWAY,
    "ARM_HOME": ARM_STAY,
    "DISARM": ARM_DISARM,
}

# on_command action handler type
OnCommandHandler = Callable[[str, str, str | None], None]
# topic_validator type
TopicValidator = Callable[[int | None, str], bool]


def parse_command_topic(topic) -> tuple[str | None, str | None]:
    """
    Return the (panel name, panel id) of a command topic, or (None, None) if it is not a command topic.

    arpi/alarm_control_panel/system/state/set -> name: system; id: none
    arpi/alarm_control_panel/house_1/state/set -> name: house; id:1
    """
    suffix = f"/{COMMAND_SUFFIX}"
    if not topic.startswith(AREA_TOPIC_PREFIX) or not topic.endswith(suffix):
        return None, None

    panel = topic[len(AREA_TOPIC_PREFIX) : -len(suffix)] or None
    if panel is None:
        return None, None

    # area panel
    if "_" in panel:
        name, id_ = panel.rsplit("_", 1)
        return name, id_

    # system panel
    return panel, None


def parse_command_payload(payload: bytes) -> tuple[str | None, str | None]:
    """
    Return the (action, code) of a command payload.

    The payload contains the access code, so it must never be logged.
    """
    message = payload.decode("utf-8", errors="replace").strip()

    try:
        data = json.loads(message)
    except json.JSONDecodeError:
        # commands without a code are sent as a plain action
        return message, None

    if not isinstance(data, dict):
        return None, None

    return data.get("action"), data.get("code") or None


class MQTTClient:
    """
    Class for publishing and subscribing to MQTT topics.
    """

    def __init__(
        self,
        on_command: OnCommandHandler | None = None,
        topic_validator: TopicValidator | None = None,
    ):
        """
        :param on_command: called as on_command(panel_name, action, code) for every
            arm/disarm command received from the broker. Subscribing to the command
            topics only happens when it is set.
        :param topic_validator: called as topic_validator(item_id, item_name) for every
            area or sensor topic received from the broker. If it returns False, the
            topic is considered orphaned and can be deleted.
        """
        self._client = None
        self._on_command = on_command
        self._topic_validator = topic_validator
        self._subscriptions: set[str] = set()

    def connect(self, client_id=None):
        """
        Connect to MQTT broker.
        """

        mqtt_connection = MQTTConnection.load_config()
        if mqtt_connection is None or not mqtt_connection.enabled:
            logger.info("MQTT connection is not enabled")
            return

        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        if self._client is None:
            logger.error("Failed to create MQTT client")
            return

        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

        mqtt_config = None
        if mqtt_connection.external:
            mqtt_config = MQTTConfigExternalPublish.load_config()
            logger.info("Using external MQTT connection configuration")
        else:
            mqtt_config = MQTTConfigInternalPublish.load_config()
            logger.info("Using internal MQTT connection configuration")

        username = mqtt_config.username
        password = mqtt_config.password
        if username:
            logger.debug(
                "Using password authentication user: %s password length = %s",
                username,
                len(password),
            )
            try:
                # FIXME:theoretically self._client should never be None here
                # but we see errors in logs, so need to add a check
                self._client.username_pw_set(username, password)
            except AttributeError as error:
                logger.error(
                    "Failed to set MQTT username=%s and password=%s: %s", username, password, error
                )
                self._client = None
                return

        if mqtt_config.tls_enabled:
            self._setup_tls(mqtt_config)

        host = mqtt_config.hostname
        port = mqtt_config.port
        logger.info(
            "Connecting to MQTT broker at %s:%s TLS: %s insecure:%s",
            host,
            port,
            mqtt_config.tls_enabled,
            mqtt_config.tls_insecure,
        )
        try:
            self._client.connect(host, port, keepalive=60)
            self._client.loop_start()
            logger.info("MQTT client (%s) connected! %s:%s", client_id, host, port)
        except socket.gaierror:
            logger.error("Failed to resolve MQTT broker hostname %s", host)
            self._client.disconnect()
            self._client = None
        except ConnectionRefusedError:
            logger.error("Failed to connect to MQTT broker at %s:%s", host, port)
            self._client.disconnect()
            self._client = None
        except ssl.SSLCertVerificationError as error:
            logger.error("Failed to connect to MQTT broker with TLS! %s", error)
            self._client.disconnect()
            self._client = None
        except Exception:
            logger.exception("Failed to connect to MQTT broker")

    def _setup_tls(self, mqtt_config: MQTTConfigExternalPublish | MQTTConfigInternalPublish):
        """
        Configure TLS for the client.

        The command topics carry the access code of the user, so the broker must be
        authenticated: an unverified connection can be terminated by a man in the middle
        who then reads the code and injects arm/disarm commands.

        tls_insecure only turns off the *hostname* check, the certificate chain is still
        verified. The internal connections need this, because they connect to localhost
        while the self signed certificate is issued for arpi.local.
        """
        logger.info(
            "MQTT TLS configured, CA: %s hostname check: %s",
            mqtt_config.ca_certs or "system store",
            not mqtt_config.tls_insecure,
        )
        if mqtt_config.ca_certs and os.path.exists(mqtt_config.ca_certs):
            # the CA is explicitly set, so it is used instead of the system certificate store
            self._client.tls_set(ca_certs=mqtt_config.ca_certs, cert_reqs=ssl.CERT_REQUIRED)
            self._client.tls_insecure_set(mqtt_config.tls_insecure)
        elif mqtt_config.ca_certs and not os.path.exists(mqtt_config.ca_certs):
            logger.error(
                "MQTT TLS CA file %s does not exist. No TLS will be established.",
                mqtt_config.ca_certs,
            )
        elif not mqtt_config.ca_certs:
            # no explicit CA means the system certificate store is used, which is expected
            self._client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
            self._client.tls_insecure_set(mqtt_config.tls_insecure)
            return

    def subscribe_areas(self):
        """
        Receive the retained configs of the area panels, they are the only way to find
        the topics of areas that were deleted or renamed while the monitor was down.
        """
        self._subscribe(f"{AREA_TOPIC_PREFIX}+/config")

    def subscribe_sensors(self):
        """
        Receive the retained configs of the sensors, they are the only way to find the
        topics of sensors that were deleted or renamed while the monitor was down.
        """
        self._subscribe(f"{SENSOR_TOPIC_PREFIX}+/config")

    def _subscribe(self, topic_filter):
        """
        Subscribe now if connected, and remember the filter for the next reconnect.
        """
        self._subscriptions.add(topic_filter)
        if self._client is not None:
            self._client.subscribe(topic_filter, qos=1)
            logger.info("Subscribed to MQTT topics %s", topic_filter)

    def close(self):
        """
        Close connection to MQTT broker.
        """
        if self._client is not None:
            self._client.disconnect()
            self._client = None

    def _on_connect(self, client, userdata, connect_flags, reason_code, properties):
        """
        Callback when connected to MQTT broker.
        """
        logger.debug("Connected with reason code: %s", reason_code)

        # subscriptions are not restored automatically after a reconnect
        if self._on_command is not None:
            client.subscribe(COMMAND_TOPIC_FILTER, qos=1)
            logger.info("Subscribed to MQTT command topics %s", COMMAND_TOPIC_FILTER)

        for topic_filter in self._subscriptions:
            client.subscribe(topic_filter, qos=1)
            logger.info("Subscribed to MQTT topics %s", topic_filter)

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        """
        Callback when disconnected from MQTT broker.
        """
        if reason_code != 0:
            logger.warning(
                "Disconnected from MQTT broker with reason code: %s, will auto-reconnect",
                reason_code,
            )
            return

        logger.info("Disconnected from MQTT broker")
        if self._client is not None:
            self._client.disconnect()
            self._client = None

    def _on_message(self, client, userdata, msg: mqtt.MQTTMessage):
        """
        Callback when message received from MQTT broker.

        The payload can contain the access code of the user, so it is logged only in debug mode.
        """
        logger.debug(
            "Received MQTT message on topic %s(qos: %s, retain: %s): %s",
            msg.topic,
            msg.qos,
            msg.retain,
            msg.payload,
        )

        # if it is not a command topic, check for orphaned topics that must be deleted
        if not msg.topic.endswith(COMMAND_SUFFIX):
            # an empty payload is the deletion we published ourselves, handling it
            # again would delete the topic in an endless loop
            if msg.payload:
                self._delete_orphan(msg.topic)
            return

        # if it is a command topic, skip if no callback is set
        if self._on_command is None:
            return

        if msg.retain and msg.topic.endswith(COMMAND_SUFFIX):
            # A retained command is redelivered on every reconnect, so a retained disarm
            # with a valid code would disarm the system again after every restart. Drop it
            # and clear the topic, otherwise it comes back with the next subscription.
            # commands are normally not retained
            logger.warning("Ignoring retained MQTT command on topic %s", msg.topic)
            client.publish(msg.topic, b"", qos=1, retain=True)
            return

        # we can't do anything with an empty payload
        if not msg.payload:
            return

        panel_name, panel_id = parse_command_topic(msg.topic)
        if panel_name is None:
            logger.error("Received MQTT message on unexpected topic %s", msg.topic)
            return

        action, code = parse_command_payload(msg.payload)
        arm_type = HA_ACTION_MAPPING.get(action, None)
        if arm_type is None:
            logger.error('Received unknown action "%s" on topic %s', action, msg.topic)
            return

        try:
            self._on_command(panel_id, panel_name, arm_type, code)
        except Exception:  # pylint: disable=broad-except
            logger.exception("Failed to handle MQTT command from topic %s", msg.topic)

    def _delete_orphan(self, topic):
        """
        Delete the MQTT object (config and state) if it is not a valid area or sensor.
        """
        # skip the non ArPI topics, they are not managed by us
        if not topic.startswith(ARPI_PREFIX):
            return

        # skip the ArPI topics that are valid areas or sensors, they are managed by us
        _, _, item, _ = topic.split("/")
        item_name, item_id = item.rsplit("_", 1) if "_" in item else (item, None)
        item_id = int(item_id) if item_id and item_id.isdigit() else None
        if self._topic_validator is None or self._topic_validator(item_id, item_name):
            return

        self._delete_object(topic.rsplit("/", 1)[0])

    def _delete_object(self, topic_prefix):
        """
        Delete the MQTT object (config and state) with the given prefix.
        """
        logger.debug("Deleting MQTT prefix %s", topic_prefix)
        # config and state are published retained, so the empty message must be
        # retained as well to remove them from the broker - otherwise the deleted
        # object comes back with the next home assistant reconnect
        self._client.publish(f"{topic_prefix}/config", "", qos=1, retain=True)
        self._client.publish(f"{topic_prefix}/state", "", qos=1, retain=True)

    def _publish_panel_config(self, topic_prefix, unique_id, name):
        """
        Publish the MQTT HomeAssistant config of an alarm control panel.
        """
        config = json.dumps(
            {
                "name": name,
                "unique_id": unique_id,
                "device": {"identifiers": [unique_id], "name": name},
                "supported_features": ["arm_home", "arm_away"],
                "state_topic": f"{topic_prefix}/state",
                "command_topic": f"{topic_prefix}/{COMMAND_SUFFIX}",
                # the access code identifies the user, so it is required for every command
                "code": "REMOTE_CODE",
                "code_arm_required": True,
                "code_disarm_required": True,
                "command_template": COMMAND_TEMPLATE,
            }
        )

        topic = f"{topic_prefix}/config"
        logger.debug("Publishing MQTT config %s=%s", topic, config)
        self._client.publish(topic, config, qos=1, retain=True)

    def _publish_panel_state(self, topic_prefix, state):
        """
        Publish the MQTT HomeAssistant state of an alarm control panel.
        """
        if state == ARM_AWAY:
            payload = "armed_away"
        elif state == ARM_STAY:
            payload = "armed_home"
        elif state == ARM_DISARM:
            payload = "disarmed"
        elif state == ARM_MIXED:
            # home assistant has no mixed state, report the armed areas as armed away
            logger.info("Publishing mixed arm state as armed_away")
            payload = "armed_away"
        else:
            logger.error("Unknown state %s", state)
            return

        self._publish_state_payload(topic_prefix, payload)

    def _publish_state_payload(self, topic_prefix, payload):
        """
        Publish a raw home assistant state payload of an alarm control panel.
        """
        topic = f"{topic_prefix}/state"
        logger.debug("Publishing MQTT state %s=%s", topic, payload)
        self._client.publish(topic, payload, qos=1, retain=True)

    def publish_area_config(self, area_id, name):
        """
        Publish the MQTT HomeAssistant config for the given area.
        """
        if self._client is None:
            return

        self._publish_panel_config(
            topic_prefix=f"{AREA_TOPIC_PREFIX}{sanitize(name)}_{area_id}",
            unique_id=f"{area_id}",
            name=f"ArPI {name}",
        )

    def delete_area(self, area_id, name):
        """
        Delete the MQTT HomeAssistant config/state for the given area.
        """
        if self._client is None:
            return

        self._delete_object(f"{AREA_TOPIC_PREFIX}{sanitize(name)}_{area_id}")

    def publish_area_state(self, area_id, name, state):
        """
        Publish the MQTT HomeAssistant state for the given area.
        """
        if self._client is None:
            return

        self._publish_panel_state(f"{AREA_TOPIC_PREFIX}{sanitize(name)}_{area_id}", state)

    def publish_area_arming(self, area_id, name):
        """
        Show the area panel as arming in Home Assistant while the exit delay runs.
        """
        if self._client is None:
            return

        self._publish_state_payload(
            f"{AREA_TOPIC_PREFIX}{sanitize(name)}_{area_id}", ARMING_PAYLOAD
        )

    def publish_system_config(self):
        """
        Publish the MQTT HomeAssistant config of the panel controlling the whole system.
        """
        if self._client is None:
            return

        self._publish_panel_config(
            topic_prefix=AREA_TOPIC_PREFIX + SYSTEM_TOPIC_NAME,
            unique_id=SYSTEM_TOPIC_NAME,
            name="ArPI System",
        )

    def publish_system_state(self, state):
        """
        Publish the MQTT HomeAssistant state of the panel controlling the whole system.
        """
        if self._client is None:
            return

        self._publish_panel_state(AREA_TOPIC_PREFIX + SYSTEM_TOPIC_NAME, state)

    def publish_system_arming(self):
        """
        Show the system panel as arming in Home Assistant while the exit delay runs.
        """
        if self._client is None:
            return

        self._publish_state_payload(AREA_TOPIC_PREFIX + SYSTEM_TOPIC_NAME, ARMING_PAYLOAD)

    def publish_sensor_config(self, sensor_id, type, name):
        """
        Publish the MQTT HomeAssistant config for the given sensor.
        """
        if self._client is None:
            return

        topic_prefix = f"{SENSOR_TOPIC_PREFIX}{sanitize(name)}_{sensor_id}"
        config = json.dumps(
            {
                "name": name,
                "device_class": SENSOR_DEVICE_MAPPING[type],
                "state_topic": f"{topic_prefix}/state",
                "unique_id": f"sensor{sensor_id}",
                "device": {"identifiers": [sensor_id], "name": name},
            }
        )

        topic = f"{topic_prefix}/config"
        logger.debug("Publishing MQTT config %s=%s", topic, config)
        self._client.publish(topic, config, qos=1, retain=True)

    def delete_sensor(self, sensor_id, name):
        """
        Delete the MQTT HomeAssistant config/state for the given sensor.
        """
        if self._client is None:
            return

        self._delete_object(f"{SENSOR_TOPIC_PREFIX}{sanitize(name)}_{sensor_id}")

    def publish_sensor_state(self, sensor_id: int, name: str, state: bool):
        """
        Publish the MQTT HomeAssistant state for the given sensor.
        """
        if self._client is None:
            return

        topic = f"{SENSOR_TOPIC_PREFIX}{sanitize(name)}_{sensor_id}/state"
        payload = SensorState.ON.value if state else SensorState.OFF.value
        logger.debug("Publishing MQTT state %s=%s", topic, payload)
        self._client.publish(topic, payload, qos=1, retain=True)
