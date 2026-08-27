import logging
import os
from dataclasses import dataclass
from datetime import datetime
from time import sleep, time

import paho.mqtt.client as mqtt
import requests
import socketio
from deepdiff import DeepDiff

from utils.constants import MONITORING_READY

logger = logging.getLogger(__name__)


def _get_time_string():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


@dataclass
class MonitorEvent:
    name: str
    payload: dict = None
    diffOptions: dict = None


class MonitorEventsClient:
    def __init__(self, device_token: str):
        self.sio = socketio.Client()
        self._received = []
        self._register_handlers()
        self._connect(device_token)

    def _register_handlers(self):
        def on_any_event(event, *args):
            payload = args[0] if args else None
            self._received.append(MonitorEvent(name=event, payload=payload))
            logger.debug(f"Socket.IO event received: {event} -> {payload}")

        self.sio.on("*", handler=on_any_event)

    def _connect(self, device_token: str):
        try:
            self.sio.connect(
                f"http://{os.environ['MONITOR_HOST']}:{os.environ['MONITOR_PORT']}/?token={device_token}",
                headers={"Referer": "http://localhost:8100"},
            )
            logger.debug("Socket.IO client connected to monitor")
        except Exception as e:
            logger.error(f"Failed to connect Socket.IO client: {e}")
            raise

    def disconnect(self):
        self.sio.disconnect()

    def wait_for_any_event(self, timeout=10):
        end = time() + timeout
        while time() < end:
            if self._received:
                return self._received[0]
            sleep(0.1)
        raise AssertionError(f"No Socket.IO event received within {timeout} seconds")

    def clear_events(self):
        self._received.clear()

    def _find_event(self, event: MonitorEvent) -> bool:
        """
        Check if a specific Socket.IO event has been received.
        If payload is provided, also check that the event payload matches.
        """
        for received_event in self._received:
            if received_event.name == event.name:
                difference = DeepDiff(
                    event.payload,
                    received_event.payload,
                    **(event.diffOptions or {}),
                )
                if event.payload is None and received_event.payload is None or difference == {}:
                    logger.debug(
                        "Socket.IO event '%s' received with payload: %s at %s",
                        event.name,
                        received_event.payload,
                        _get_time_string(),
                    )
                    return True
                else:
                    logger.debug(
                        "Socket.IO event '%s' received but payload does not match. Received: %s, Expected: %s at %s. Difference: %s",
                        event.name,
                        received_event.payload,
                        event.payload,
                        _get_time_string(),
                        difference,
                    )

        return False

    def assert_not_received(self, event: MonitorEvent):
        """
        Assert that a specific Socket.IO event has not been received so far.
        """
        assert not self._find_event(event), (
            f"Socket.IO event '{event.name}' unexpectedly received at {_get_time_string()}"
        )

    def wait_for_event(self, event: MonitorEvent, delay=0, timeout=10):
        """
        Wait for a specific Socket.IO event to arrive within timeout.
        If payload is provided, also check that the event payload matches.
        """
        logger.debug(
            "Waiting for Socket.IO event: %s from %s",
            event.name,
            _get_time_string(),
        )

        start = datetime.now()
        while (datetime.now() - start).total_seconds() < delay:
            assert not self._find_event(event), (
                f"Socket.IO event '{event.name}' received before delay period at {_get_time_string()}"
            )
            sleep(0.1)

        start = datetime.now()
        while (datetime.now() - start).total_seconds() < timeout:
            if self._find_event(event):
                return

            sleep(0.1)

        assert False, (
            f"Socket.IO event '{event.name}' not received within {timeout} seconds at {_get_time_string()}"
        )

    def wait_for_events(self, events: list[MonitorEvent], delay=0, timeout=10):
        """
        Wait for all specified Socket.IO events to arrive within timeout.
        If payload is provided for an event, also check that the event payload matches.

        Raises:
            AssertionError: If any of the specified events are not received within the timeout.

        Args:
            events (list[MonitorEvent]): List of MonitorEvent objects to wait for.
            delay (float): Time in seconds to wait before checking for events.
            timeout (float): Time in seconds to wait for all events to arrive.
        """
        logger.debug(
            "Waiting for Socket.IO events: %s from %s",
            [event.name for event in events],
            _get_time_string(),
        )

        start = datetime.now()
        while (datetime.now() - start).total_seconds() < delay:
            for event in events:
                assert not self._find_event(event), (
                    f"Socket.IO event '{event.name}' received before delay period ({delay} seconds) at {_get_time_string()}"
                )
            sleep(0.1)

        start = datetime.now()
        matched_events = []
        while (datetime.now() - start).total_seconds() < timeout:
            for event in events:
                if event not in matched_events and self._find_event(event):
                    matched_events.append(event)
                    break

            if len(matched_events) == len(events):
                logger.debug(
                    "All Socket.IO events received: %s at %s",
                    [event.name for event in events],
                    _get_time_string(),
                )
                return

            sleep(0.1)

        unexpected_events = [event.name for event in self._received if event not in events]
        if unexpected_events:
            raise AssertionError(
                f"Unexpected Socket.IO events received within {timeout} seconds at {_get_time_string()}: {unexpected_events}"
            )

        missing_events = [event.name for event in events if event not in matched_events]

        raise AssertionError(
            f"Socket.IO events not received within {timeout} seconds at {_get_time_string()}: {missing_events}"
        )


def call_api(method: str, path: str, payload: dict, token: str):
    host = os.environ["SERVER_HOST"]
    port = os.environ["SERVER_PORT"]
    response = requests.request(
        method,
        f"http://{host}:{port}{path}",
        json=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Origin": "http://localhost:8100",
        },
    )

    return response


def check_api_response(response: requests.Response, expected_status: int | list[int] = 200):
    if isinstance(expected_status, int):
        expected_status = [expected_status]

    if response.status_code not in expected_status:
        logger.error(f"API call failed: {response.status_code} {response.text}")

    assert response.status_code in expected_status, (
        f"API call failed! Code: {response.status_code} Response: {response.text}"
    )


def wait_for_monitoring_ready(device_token: str, timeout=15):
    wait_for_monitoring_state(MONITORING_READY, device_token, timeout)


def wait_for_monitoring_state(state: str, device_token: str, timeout=15):
    start_time = time()
    while time() - start_time < timeout:
        response = call_api("GET", "/api/monitoring/state", {}, device_token)
        check_api_response(response)
        if response.json()["state"] == state:
            logger.debug(
                "Monitoring is in state '%s' at %s",
                state,
                datetime.now().strftime("%H:%M:%S"),
            )
            break
        else:
            logger.debug(
                "Monitoring state is '%s', waiting for '%s' at %s",
                response.json()["state"],
                state,
                datetime.now().strftime("%H:%M:%S"),
            )

        sleep(0.5)
    else:
        raise RuntimeError(
            "Monitoring did not reach state '%s' within %s seconds" % (state, timeout)
        )


class MqttStateRecorder:
    """
    Context manager recording every payload published to an MQTT topic.

    The retained message delivered on subscribe is dropped, so the recorded
    payloads only contain what was published while the recorder was active.
    """

    def __init__(self, topic: str, host: str = "localhost", port: int = 2883):
        self.payloads = []
        self._topic = topic
        self._host = host
        self._port = port
        # recorders with the same client id would kick each other off the broker
        client_id = "test_state_recorder_" + "".join(c if c.isalnum() else "_" for c in topic)
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        self._client.on_message = self._on_message

    def _on_message(self, _client, _userdata, msg):
        payload = msg.payload.decode()
        logger.debug("Recorded MQTT state %s=%s at %s", msg.topic, payload, _get_time_string())
        self.payloads.append(payload)

    def __enter__(self):
        self._client.connect(self._host, self._port, keepalive=10)
        self._client.subscribe(self._topic, qos=1)
        self._client.loop_start()
        # let the retained message arrive, it is not part of the recording
        sleep(0.5)
        self.payloads.clear()
        return self

    def __exit__(self, *args):
        self._client.loop_stop()
        self._client.disconnect()

    def wait_for(self, payload: str, after_index: int = 0, timeout: float = 10.0) -> int:
        """
        Wait until the payload appears at or after the given index and return its index.
        """
        end = time() + timeout
        while time() < end:
            try:
                return self.payloads.index(payload, after_index)
            except ValueError:
                sleep(0.1)

        raise AssertionError(
            f"MQTT state '{payload}' not received within {timeout}s, got {self.payloads}"
        )


def collect_retained_messages(topic_filter: str, host="localhost", port=2883, duration=1.0):
    """
    Return the retained MQTT messages matching the topic filter as topic => payload.
    """
    messages = {}
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="test_retained_observer")
    client.on_message = lambda _client, _userdata, msg: messages.update({msg.topic: msg.payload})
    client.connect(host, port, keepalive=10)
    client.subscribe(topic_filter, qos=1)
    client.loop_start()
    sleep(duration)
    client.loop_stop()
    client.disconnect()
    return messages
