import json
import logging
import socket
import ssl
from unicodedata import normalize

from enum import Enum

import paho.mqtt.client as mqtt

from utils.constants import ARM_AWAY, ARM_DISARM, ARM_STAY, LOG_MQTT
from monitor.config_helper import load_mqtt_connection_config, load_mqtt_internal_publish_config, load_mqtt_external_publish_config


def sanitize(name):
    """
    Convert name to [a-zA-Z0-9_-] for home assistant
    """
    name = normalize("NFKD", name)
    return "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in name).lower()


class SensorState(Enum):
    OFF = "OFF"
    ON = "ON"


SENSOR_DEVICE_MAPPING = {
    "Motion": "motion",
    "Tamper": "tamper",
    "Open": "opening",
    "Break": "glass_break",
}

ARPI_PREFIX = "arpi/"
SENSOR_TOPIC_PREFIX = f"{ARPI_PREFIX}binary_sensor/"
AREA_TOPIC_PREFIX = f"{ARPI_PREFIX}alarm_control_panel/"


class MQTTClient:
    """
    Class for publishing and subscribing to MQTT topics.
    """

    def __init__(self):
        self._logger = logging.getLogger(LOG_MQTT)
        self._client = None

    def connect(self, client_id=None):
        """
        Connect to MQTT broker.
        """

        mqtt_connection = load_mqtt_connection_config()
        if mqtt_connection is None or not mqtt_connection.enabled:
            self._logger.info("MQTT connection is not enabled")
            return

        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=client_id)
        if self._client is None:
            self._logger.error("Failed to create MQTT client")
            return

        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message


        mqtt_config = None
        if mqtt_connection.external:
            mqtt_config = load_mqtt_external_publish_config()
            self._logger.info("Using external MQTT connection configuration")
        else:
            mqtt_config = load_mqtt_internal_publish_config()
            self._logger.info("Using internal MQTT connection configuration")

        username = mqtt_config.username
        password = mqtt_config.password
        if username:
            self._logger.debug("Using password authentication user: %s password length = %s",
                               username,
                               len(password))
            try:
                # FIXME:theoretically self._client should never be None here
                # but we see errors in logs, so need to add a check
                self._client.username_pw_set(username, password)
            except AttributeError:
                self._logger.error("Failed to set MQTT username and password")
                self._client = None
                return

        if mqtt_config.tls_enabled:
            self._client.tls_set(cert_reqs=ssl.CERT_NONE)
            if mqtt_config.tls_insecure:
                self._client.tls_insecure_set(True)

        host = mqtt_config.hostname
        port = mqtt_config.port
        self._logger.info("Connecting to MQTT broker at %s:%s TLS: %s insecure:%s", host, port,
                          mqtt_config.tls_enabled,
                          mqtt_config.tls_insecure)
        try:
            self._client.connect(host, port, keepalive=60)
            self._logger.info("MQTT client (%s) connected! %s:%s", client_id, host, port)
            self._client.loop_start()
        except socket.gaierror:
            self._logger.error("Failed to resolve MQTT broker hostname %s", host)
            self._client.disconnect()
            self._client = None
        except ConnectionRefusedError:
            self._logger.error("Failed to connect to MQTT broker at %s:%s", host, port)
            self._client.disconnect()
            self._client = None
        except ssl.SSLCertVerificationError as error:
            self._logger.error("Failed to connect to MQTT broker with TLS! %s", error)
            self._client.disconnect()
            self._client = None
        except Exception as e:
            self._logger.exception("Failed to connect to MQTT broker: %s", e)

    def close(self):
        """
        Close connection to MQTT broker.
        """
        if self._client is not None:
            self._client.disconnect()
            self._client = None

    def _on_connect(self, client, userdata, flags, rc):
        """
        Callback when connected to MQTT broker.
        """
        self._logger.debug("Connected with result code: %s", rc)

    def _on_disconnect(self, client, userdata, rc):
        """
        Callback when disconnected from MQTT broker.
        """
        if rc != 0:
            self._logger.warn("Disconnected from MQTT broker with result code: %s, will auto-reconnect", rc)
            return

        self._logger.info("Disconnected from MQTT broker")
        if self._client is not None:
            self._client.disconnect()
            self._client = None

    def _on_message(self, client, userdata, msg):
        """
        Callback when message received from MQTT broker.
        """
        self._logger.debug("Received MQTT message on topic %s: %s", msg.topic, msg.payload)

    def _delete_object(self, topic_prefix):
        """
        Delete the MQTT object (config and state) with the given prefix.
        """
        self._logger.debug("Deleting MQTT prefix %s", topic_prefix)
        self._client.publish(f"{topic_prefix}/config", "", qos=1, retain=False)
        self._client.publish(f"{topic_prefix}/state", "", qos=1, retain=False)

    def publish_area_config(self, name="arpi"):
        """
        Publish the MQTT HomeAssistant config for the given area.
        """
        if self._client is None:
            return

        topic_prefix = AREA_TOPIC_PREFIX + sanitize(name)
        config = json.dumps(
            {
                "name": f"ArPI {name}",
                "supported_features": ["arm_home", "arm_away"],
                "state_topic": f"{topic_prefix}/state",
                "command_topic": f"{topic_prefix}/state/set"
            }
        )

        topic = f"{topic_prefix}/config"
        self._logger.debug("Publishing MQTT config %s=%s", topic, config)
        self._client.publish(topic, config, qos=1, retain=True)

    def delete_area(self, name):
        """
        Delete the MQTT HomeAssistant config/state for the given area.
        """
        if self._client is None:
            return

        self._delete_object(f"{AREA_TOPIC_PREFIX}{sanitize(name)}")

    def publish_area_state(self, name, state):
        """
        Publish the MQTT HomeAssistant state for the given area.
        """
        if self._client is None:
            return

        topic = f"{AREA_TOPIC_PREFIX}{sanitize(name)}/state"
        if state == ARM_AWAY:
            payload = "armed_away"
        elif state == ARM_STAY:
            payload = "armed_home"
        elif state == ARM_DISARM:
            payload = "disarmed"
        else:
            self._logger.error("Unknown state %s", state)
            return

        self._logger.debug("Publishing MQTT state %s=%s", topic, payload)
        self._client.publish(topic, payload, qos=1, retain=True)

    def publish_sensor_config(self, id, type, name):
        """
        Publish the MQTT HomeAssistant config for the given sensor.
        """
        if self._client is None:
            return

        topic_prefix = SENSOR_TOPIC_PREFIX + sanitize(name)
        config = json.dumps(
            {
                "name": None,
                "device_class": SENSOR_DEVICE_MAPPING[type],
                "state_topic": f"{topic_prefix}/state",
                "unique_id": f"sensor{id}",
                "device": {"identifiers": [id], "name": name},
            }
        )

        topic = f"{topic_prefix}/config"
        self._logger.debug("Publishing MQTT config %s=%s", topic, config)
        self._client.publish(topic, config, qos=1, retain=True)

    def delete_sensor(self, name):
        """
        Delete the MQTT HomeAssistant config/state for the given sensor.
        """
        if self._client is None:
            return

        self._delete_object(f"{SENSOR_TOPIC_PREFIX}{sanitize(name)}")

    def publish_sensor_state(self, name, state: bool):
        """
        Publish the MQTT HomeAssistant state for the given sensor.
        """
        if self._client is None:
            return

        topic = f"{SENSOR_TOPIC_PREFIX}{sanitize(name)}/state"
        payload = SensorState.ON.value if state else SensorState.OFF.value
        self._logger.debug("Publishing MQTT state %s=%s", topic, payload)
        self._client.publish(topic, payload, qos=1, retain=True)
