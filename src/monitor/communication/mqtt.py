import json
import logging
import os

from enum import Enum
import socket
import paho.mqtt.client as mqtt

from constants import LOG_MQTT


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


class MQTTClient:
    """
    Class for publishing and subscribing to MQTT topics.
    """

    HOME_ASSISTANT_PREFIX = "homeassistant"

    def __init__(self):
        self._logger = logging.getLogger(LOG_MQTT)
        self._client = None

    def connect(self):

        self._client = mqtt.Client()
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

        username = os.environ.get("MQTT_BROKER_USERNAME", "")
        password = os.environ.get("MQTT_BROKER_PASSWORD", "")
        if username:
            self._client.username_pw_set(username, password)

        if os.environ.get("MQTT_BROKER_TLS_ENABLED", "false").lower() in ("true", "1"):
            self._client.tls_set()

        host = os.environ["MQTT_BROKER_HOST"]
        port = int(os.environ["MQTT_BROKER_PORT"])
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

    def publish_sensor_config(self, id, type, name):
        if self._client is None:
            return

        config = json.dumps(
            {
                "name": None,
                "device_class": SENSOR_DEVICE_MAPPING[type],
                "state_topic": f"homeassistant/binary_sensor/{sanitize(name)}/state",
                "unique_id": f"sensor{id}",
                "device": {"identifiers": [id], "name": name},
            }
        )

        topic = f"{self.HOME_ASSISTANT_PREFIX}/binary_sensor/{sanitize(name)}/config"
        self._logger.debug("Publishing MQTT config %s=%s", topic, config)
        self._client.publish(topic, config, qos=1, retain=True)

    def publish_sensor_state(self, name, state: bool):
        if self._client is None:
            return

        topic = f"{self.HOME_ASSISTANT_PREFIX}/binary_sensor/{sanitize(name)}/state"
        payload = SensorState.ON.value if state else SensorState.OFF.value
        self._logger.debug("Publishing MQTT state %s=%s", topic, payload)
        self._client.publish(topic, payload, qos=1, retain=True)
