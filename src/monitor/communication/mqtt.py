import json
import logging
import os
import socket
import ssl
import sys

from enum import Enum

import paho.mqtt.client as mqtt

from dotenv import load_dotenv
load_dotenv()
load_dotenv("secrets.env")
sys.path.insert(0, os.getenv("PYTHONPATH"))

from constants import ARM_AWAY, ARM_DISARM, ARM_STAY, LOG_MQTT


def sanitize(name):
    """
    Convert name to [a-zA-Z0-9_-] for home assistant
    """
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

HOME_ASSISTANT_PREFIX = "homeassistant"
SENSOR_CONFIG_TOPIC = HOME_ASSISTANT_PREFIX + "/binary_sensor/%s/config"
SENSOR_STATE_TOPIC = HOME_ASSISTANT_PREFIX + "/binary_sensor/%s/state"
AREA_CONFIG_TOPIC = HOME_ASSISTANT_PREFIX + "/alarm_control_panel/arpi_%s/config"
AREA_STATE_TOPIC = HOME_ASSISTANT_PREFIX + "/alarm_control_panel/arpi_%s/state"


class MQTTClient:
    """
    Class for publishing and subscribing to MQTT topics.
    """

    def __init__(self):
        self._logger = logging.getLogger(LOG_MQTT)
        self._client = None

    def connect(self):

        self._client = mqtt.Client()
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

        username = os.environ.get("ARGUS_MQTT_USERNAME", "")
        password = os.environ.get("ARGUS_MQTT_PASSWORD", "")
        if username:
            self._logger.debug("Using password authentication user: %s password length = %s",
                               username,
                               len(password))
            self._client.username_pw_set(username, password)

        if os.environ.get("ARGUS_MQTT_TLS_ENABLED", "false").lower() in ("true", "1"):
            self._logger.debug("Using TLS")
            self._client.tls_set(cert_reqs=ssl.CERT_NONE)

        if os.environ.get("ARGUS_MQTT_TLS_INSECURE", "false").lower() in ("true", "1"):
            self._logger.debug("Using TLS insecure")
            self._client.tls_insecure_set(True)

        host = os.environ["ARGUS_MQTT_HOST"]
        port = int(os.environ["ARGUS_MQTT_PORT"])
        self._logger.debug("Connecting to MQTT broker at %s:%s", host, port)
        try:
            self._client.connect(host, port, 60)
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

    def _on_connect(self, client, userdata, flags, rc):
        self._logger.debug("Connected with result code: %s", rc)

    def _on_disconnect(self, client, userdata, rc):
        self._logger.debug("Disconnected from MQTT broker with result code: %s", rc)
        self._client.disconnect()
        self._client = None

    def _on_message(self, client, userdata, msg):
        self._logger.debug("Received MQTT message on topic %s: %s", msg.topic, msg.payload)

    def publish_area_config(self, name="arpi"):
        if self._client is None:
            return

        topic_prefix = AREA_CONFIG_TOPIC % sanitize(name)
        config = json.dumps(
            {
                "name": f"ArPI {name}",
                "supported_features": ["arm_home", "arm_away"],
                "state_topic": AREA_STATE_TOPIC % sanitize(name),
                "command_topic": f"{topic_prefix}/state/set"
            }
        )

        topic = f"{topic_prefix}/config"
        self._logger.debug("Publishing MQTT config %s=%s", topic, config)
        self._client.publish(topic, config, qos=1, retain=True)

    def delete_area_config(self, name):
        if self._client is None:
            return

        topic = AREA_CONFIG_TOPIC % sanitize(name)
        self._logger.debug("Deleting MQTT config %s", topic)
        self._client.publish(topic, "", qos=1, retain=True)

    def publish_area_state(self, name, state):
        if self._client is None:
            return

        topic = AREA_STATE_TOPIC % sanitize(name)
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
        if self._client is None:
            return

        topic_prefix = SENSOR_CONFIG_TOPIC % sanitize(name)
        config = json.dumps(
            {
                "name": None,
                "device_class": SENSOR_DEVICE_MAPPING[type],
                "state_topic": SENSOR_STATE_TOPIC % sanitize(name),
                "unique_id": f"sensor{id}",
                "device": {"identifiers": [id], "name": name},
            }
        )

        topic = f"{topic_prefix}/config"
        self._logger.debug("Publishing MQTT config %s=%s", topic, config)
        self._client.publish(topic, config, qos=1, retain=True)

    def delete_sensor_config(self, name):
        if self._client is None:
            return

        topic = SENSOR_CONFIG_TOPIC % sanitize(name)
        self._logger.debug("Deleting MQTT config %s", topic)
        self._client.publish(topic, "", qos=1, retain=True)

    def publish_sensor_state(self, name, state: bool):
        if self._client is None:
            return

        topic = SENSOR_STATE_TOPIC % sanitize(name)
        payload = SensorState.ON.value if state else SensorState.OFF.value
        self._logger.debug("Publishing MQTT state %s=%s", topic, payload)
        self._client.publish(topic, payload, qos=1, retain=True)
