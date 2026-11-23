"""
Sensor monitoring and alerting.
"""

import logging
from datetime import datetime as dt
from datetime import timedelta
from os import environ
from time import sleep

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from monitor.adapters.sensor import get_sensor_adapter
from monitor.alert import SensorAlert
from monitor.communication.mqtt import MQTTClient
from monitor.config.helper import load_config
from monitor.config.models import AlertSensitivityConfig
from monitor.database import create_database_session, get_database_session
from monitor.sensor.detector import detect_alert, detect_error, detect_tamper
from monitor.sensor.history import SensorsHistory
from monitor.socket_io import send_sensors_error, send_sensors_state, send_sensors_tamper
from monitor.storage import State, States
from monitor.zigbee_handler import ZigbeeDeviceStore
from utils.constants import (
    ALERT_AWAY,
    ALERT_SABOTAGE,
    ALERT_STAY,
    ARM_AWAY,
    ARM_STAY,
    LOG_SENSORS,
    MONITORING_ALERT,
    MONITORING_ALERT_DELAY,
    MONITORING_ARM_DELAY,
    MONITORING_ARMED,
    MONITORING_INVALID_CONFIG,
    MONITORING_READY,
    MONITORING_SABOTAGE,
    MONITORING_STARTUP,
    MONITORING_UPDATING_CONFIG,
)
from utils.models import AlertSensor, Arm, Sensor

logger = logging.getLogger(LOG_SENSORS)


MEASUREMENT_CYCLES = 2
MEASUREMENT_TIME = 3


# alert time window length in seconds
ALERT_WINDOW = int(environ.get("ALERT_TIME_WINDOW", "1"))
# threshold in the percent of high values in the time window (0-100)
ALERT_THRESHOLD = int(environ.get("ALERT_THRESHOLD", "100"))
# board version
BOARD_VERSION = int(environ["BOARD_VERSION"])


class SensorHandler:
    """
    Handles the sensors monitoring and alerting.
    """

    MQTT_CLIENT_ID = "arpi_sensors"

    def __init__(self, broadcaster):
        self._db_session = None
        self._broadcaster = broadcaster
        self._sensor_adapter = None
        self._alerting_sensors = set()
        self._tampering_sensors = set()
        self._sensors_history = None
        self._sensors = None
        self._mqtt_client: MQTTClient | None = None
        self._published_topics: set[tuple[int | None, str]] = set()

    def initialize(self):
        self._mqtt_client = MQTTClient(topic_validator=self.is_sensorname_valid)
        self._mqtt_client.connect(client_id=self.MQTT_CLIENT_ID)
        self._mqtt_client.subscribe_sensors()
        self._db_session = get_database_session()
        self._sensor_adapter = get_sensor_adapter()

    def update_mqtt_config(self):
        """
        Update the MQTT configuration.
        """
        if self._mqtt_client is not None:
            self._mqtt_client.close()
            self._mqtt_client.connect(client_id=self.MQTT_CLIENT_ID)

    def is_sensorname_valid(self, item_id: int | None, item_name: str):
        """Return whether a retained MQTT name belongs to a current sensor."""
        with create_database_session() as session:
            for sensor in session.scalars(select(Sensor).where(Sensor.deleted == False)):
                if sensor.id == item_id:
                    return True

        logger.warning("MQTT topic '%s(%s)' does not match any current sensor", item_name, item_id)
        return False

    def has_active_sensor(self, area_id: int | None = None) -> bool:
        """
        Check if there is any active sensor.
        Returns True if any sensor is active, False otherwise.
        """

        # check active sensors without sensitivity
        if area_id is None:
            return any(sensor.alert for sensor in self._sensors)

        return any(sensor.alert and sensor.area_id == area_id for sensor in self._sensors)

    def calibrate_sensors(self):
        """
        Calibrate the sensors: update the reference value of the sensors.
        """
        logger.info("Initialize sensor references...")
        new_references = self.measure_sensor_references()
        if len(new_references) == self._sensor_adapter.channel_count:
            logger.info("New references: %s", [float(f"{x:.3f}") for x in new_references])
            self.save_sensor_references(new_references)
        else:
            logger.error("Error measure values! %s", [float(f"{x:.3f}") for x in new_references])

    def has_uncalibrated_sensor(self):
        """
        Check if there is any wired sensor without reference value.
        """
        for sensor in self._sensors:
            if sensor.is_zigbee:
                continue
            if sensor.reference_value is None and sensor.channel != -1:
                logger.info("Found uncalibrated sensor: %s(%s)", sensor.name, sensor.id)
                return True

        logger.info("No uncalibrated sensors found")
        return False

    def load_sensors(self):
        """
        Load the sensors from the db in the thread to avoid session problems.
        """

        monitoring_state = States.get(State.MONITORING)
        if monitoring_state == MONITORING_STARTUP:
            monitoring_state = MONITORING_READY

        States.set(State.MONITORING, MONITORING_UPDATING_CONFIG)
        send_sensors_state(None)

        # force reload the sensors from the database
        self._db_session.expire_all()
        self._sensors = self._db_session.scalars(
            select(Sensor).where(Sensor.deleted == False).options(joinedload(Sensor.zigbee_device))
        ).all()
        logger.debug("Sensors reloaded!")

        alert_sensitivity = load_config(AlertSensitivityConfig)

        # initialize the sensors history for the alert sensitivity
        sample_rate = int(environ["SAMPLE_RATE"])
        if alert_sensitivity.monitor_period is None:
            # no custom sensitivity, use instant alerts
            self._sensors_history = SensorsHistory(
                len(self._sensors),
                size=1,
                threshold=100,
            )
        else:
            # general sensitivity of the sensors
            self._sensors_history = SensorsHistory(
                len(self._sensors),
                size=int(sample_rate * alert_sensitivity.monitor_period),
                threshold=alert_sensitivity.monitor_threshold,
            )

        # set the sensitivity of the sensors
        for idx, sensor in enumerate(self._sensors):
            if sensor.monitor_threshold is not None:
                if sensor.monitor_period is None and sensor.monitor_threshold is None:
                    # keep system defaults
                    continue
                elif sensor.monitor_period is None and sensor.monitor_threshold == 100:
                    # force instant alert
                    self._sensors_history.set_sensitivity(idx, 1, 100)
                else:
                    self._sensors_history.set_sensitivity(
                        idx,
                        int(sample_rate * sensor.monitor_period),
                        sensor.monitor_threshold,
                    )

        # keep config update state
        sleep(2)

        wired_sensor_count = sum(1 for sensor in self._sensors if not sensor.is_zigbee)

        # verify the sensor configuration
        if wired_sensor_count > self._sensor_adapter.channel_count:
            logger.info(
                "Invalid number of wired sensors to monitor (Found=%s > Max=%s)",
                wired_sensor_count,
                self._sensor_adapter.channel_count,
            )
            self._sensors = []
            States.set(State.MONITORING, MONITORING_INVALID_CONFIG)
        elif not self.validate_sensor_config():
            logger.info("Invalid channel configuration")
            self._sensors = []
            States.set(State.MONITORING, MONITORING_INVALID_CONFIG)
        elif self.has_uncalibrated_sensor():
            logger.info("Found sensor(s) without reference value")
            self.calibrate_sensors()
            States.set(State.MONITORING, monitoring_state)
        else:
            States.set(State.MONITORING, monitoring_state)

        send_sensors_state(False)

    def publish_sensors(self):
        """
        Publish the sensor configuration to the MQTT.

        Based on the previously published topics, remove the state and configs of the sensors
        that were renamed or deleted.
        """
        previously_published_topics = self._published_topics
        self._published_topics = set()
        self._sensors = (
            self._db_session.execute(
                select(Sensor)
                .filter(Sensor.deleted == False)
                .options(joinedload(Sensor.zigbee_device))
            )
            .scalars()
            .all()
        )
        for sensor in self._sensors:
            self._mqtt_client.publish_sensor_config(sensor.id, sensor.type.name, sensor.name)
            self._mqtt_client.publish_sensor_state(sensor.id, sensor.name, False)
            self._published_topics.add((sensor.id, sensor.name))

        orphaned_topics = previously_published_topics - self._published_topics
        for sensor_id, sensor_name in orphaned_topics:
            self._mqtt_client.delete_sensor(sensor_id, sensor_name)

    def validate_sensor_config(self):
        """
        Validate the sensor configuration.
        Wired sensors must remain unique by channel; Zigbee sensors are mapped to ZHA entities.
        """
        logger.debug("Validating sensor configuration...")
        channels = set()
        for sensor in self._sensors:
            if sensor.is_zigbee:
                continue
            if sensor.channel is None:
                continue
            if sensor.channel in channels and BOARD_VERSION == 2:
                logger.debug("Channel already in use: %s", sensor.channel)
                return False
            channels.add(sensor.channel)
            logger.debug("Channel added: %s", sensor.channel)

        logger.debug("Channels: %s", channels)
        return True

    def measure_sensor_references(self):
        """
        Retrieves a list of vales measured on the all the channels.
        """
        measurements = []
        for _ in range(MEASUREMENT_CYCLES):
            measurements.append(self._sensor_adapter.get_values())
            sleep(MEASUREMENT_TIME)

        logger.debug("Measured values: %s", measurements)

        references = {}
        for channel in range(self._sensor_adapter.channel_count):
            value_sum = sum(measurements[cycle][channel] for cycle in range(MEASUREMENT_CYCLES))
            references[channel] = value_sum / MEASUREMENT_CYCLES

        return list(references.values())

    def save_sensor_references(self, references):
        """
        Save the reference values to the database.
        """
        for sensor in self._sensors:
            if sensor.is_zigbee:
                continue
            # skip sensors without a channel or already calibrated
            if sensor.channel == -1 or sensor.reference_value is not None:
                continue

            sensor.reference_value = references[sensor.channel]
            self._db_session.commit()

    def scan_sensors(self):
        """
        Checking for alerting sensors if armed and
        update the sensor states in the database.
        """
        changes = False
        for sensor in self._sensors:
            is_tamper = None
            if sensor.is_zigbee:
                entity_data = None
                device = getattr(sensor, "zigbee_device", None)
                if device is not None:
                    entity_data = ZigbeeDeviceStore.get_entity_state(
                        device.ieee_address, sensor.zigbee_entity_id
                    )
                is_alert = (
                    bool(entity_data.value)
                    if entity_data is not None
                    and entity_data.value is not None
                    and entity_data.device_class not in ("tamper", "problem")
                    else False
                )
                attributes = entity_data.attributes if entity_data is not None else {}
                if sensor.supports_tamper(BOARD_VERSION):
                    is_tamper = (
                        bool(attributes.get("tamper", False))
                        or (
                            entity_data is not None
                            and entity_data.device_class == "tamper"
                            and bool(entity_data.value)
                        )
                        or (
                            device is not None
                            and ZigbeeDeviceStore.has_entity_status(device.ieee_address, "tamper")
                        )
                    )
                is_error = (
                    entity_data is None
                    or entity_data.value is None
                    or entity_data.available is False
                    or bool(attributes.get("trouble", False))
                    or (entity_data.device_class == "problem" and bool(entity_data.value))
                    or (
                        device is not None
                        and ZigbeeDeviceStore.has_entity_status(device.ieee_address, "problem")
                    )
                )
                if is_error and not sensor.error:
                    logger.error(
                        "Sensor %s(%s) (zigbee/%s) encountered an error: %s",
                        sensor.name,
                        sensor.id,
                        sensor.zigbee_entity_id,
                        entity_data,
                    )
                logger.trace(
                    "Sensor %s(%s) (zigbee/%s) value: %s => alert: %s, error: %s, tamper: %s",
                    sensor.name,
                    sensor.id,
                    sensor.zigbee_entity_id,
                    getattr(entity_data, "value", None),
                    is_alert,
                    is_error,
                    is_tamper,
                )
            else:
                # skip sensor without a channel
                if sensor.channel == -1:
                    is_alert = False
                    is_error = False
                else:
                    value = self._sensor_adapter.get_value(sensor.channel)

                    is_alert = detect_alert(sensor, value)
                    if sensor.supports_tamper(BOARD_VERSION):
                        is_tamper = detect_tamper(sensor, value)

                    is_error = detect_error(sensor, value)

                    logger.trace(
                        "Sensor %s(%s) (CH%02d) value: %s => alert: %s, error: %s, tamper: %s",
                        sensor.name,
                        sensor.id,
                        sensor.channel + 1,
                        float(f"{value:.3f}"),
                        is_alert,
                        is_error,
                        is_tamper,
                    )

                    if is_alert:
                        logger.warning(
                            "Sensor %s(%s) (CH%02d) value: %.3f triggered an alert",
                            sensor.name,
                            sensor.id,
                            sensor.channel + 1,
                            value,
                        )

                    if is_error:
                        logger.error(
                            "Sensor %s(%s) (CH%02d) value: %.3f encountered an error",
                            sensor.name,
                            sensor.id,
                            sensor.channel + 1,
                            value,
                        )

                    if is_tamper:
                        logger.warning(
                            "Sensor %s(%s) (CH%02d) value: %.3f tamper detected",
                            sensor.name,
                            sensor.id,
                            sensor.channel + 1,
                            value,
                        )

            if is_alert != sensor.alert:
                sensor.alert = is_alert
                self._mqtt_client.publish_sensor_state(sensor.id, sensor.name, sensor.alert)
                if sensor.enabled:
                    send_sensors_state(sensor.alert)
                changes = True

            if is_error != sensor.error:
                sensor.error = is_error
                if sensor.enabled:
                    send_sensors_error(sensor.error)
                changes = True

            if is_tamper != sensor.tamper:
                sensor.tamper = is_tamper
                if sensor.enabled:
                    send_sensors_tamper(sensor.tamper)
                changes = True

        self._sensors_history.add_states([sensor.alert for sensor in self._sensors])

        if changes:
            self._db_session.commit()

    def handle_alerts(self):
        """
        Checking for alerting sensors if armed
        and start the alert if needed.
        """

        # save current state to avoid concurrency
        current_monitoring = States.get(State.MONITORING)
        now = dt.now().astimezone()
        logger.trace("Checking sensors in %s", current_monitoring)

        arm: Arm = None
        if current_monitoring == MONITORING_ARM_DELAY:
            # wait 5 seconds for the arm created in the database
            # synchronizing the two threads
            retries = 0
            while not arm and retries < 50:
                arm = self._db_session.scalar(select(Arm).where(~Arm.disarm.has()))
                retries += 1
                if not arm:
                    sleep(0.1)

            if not arm:
                raise RuntimeError("No arm found in the database while in ARM_DELAY state")

            logger.debug("Arm: %s", arm)

        for idx, sensor in enumerate(self._sensors):
            if sensor.tamper and sensor.enabled:
                if sensor.id not in self._tampering_sensors:
                    self._tampering_sensors.add(sensor.id)
                    self._alerting_sensors.add(sensor.id)
                    SensorAlert.start_alert(
                        sensor.id, sensor.name, 0, ALERT_SABOTAGE, None, self._broadcaster
                    )
                continue

            self._tampering_sensors.discard(sensor.id)
            alert_type = SensorHandler.get_alert_type(sensor, current_monitoring)
            delay = SensorHandler.get_sensor_delay(sensor, current_monitoring)
            sensitivity = self._sensors_history.get_sensitivity(idx)

            # alert under threshold
            if (
                not self._sensors_history.is_sensor_alerting(idx)
                and self._sensors_history.has_sensor_any_alert(idx)
                and sensor.id not in self._alerting_sensors
                and current_monitoring == MONITORING_ARMED
                and sensor.enabled
                and alert_type is not None
                and delay is not None
            ):
                logger.warning(
                    "Sensor %s(%s) (CH%02d) has suppressed alert! %ss%s | (%r)",
                    sensor.name,
                    sensor.id,
                    sensor.channel,
                    sensitivity.monitor_period,
                    sensitivity.monitor_threshold,
                    self._sensors_history.get_states(idx),
                )
                continue

            # add new alert, enabled sensors to the alert
            if (
                self._sensors_history.is_sensor_alerting(idx)
                and sensor.id not in self._alerting_sensors
                and sensor.enabled
            ):
                # do not start alert if in delay
                if (
                    current_monitoring != MONITORING_ALERT_DELAY
                    and delay is not None
                    and (arm is not None and arm.time + timedelta(seconds=delay) > now)
                ):
                    logger.debug(
                        "Ignore alert on sensor %s(%s): %s + %s < %s",
                        sensor.name,
                        sensor.id,
                        arm.time,
                        timedelta(seconds=delay),
                        now,
                    )
                    # ignore alert
                    continue

                # start the alert
                logger.debug(
                    "Found alerting sensor %s(%s), states: %s, delay: %s, alert type: %s",
                    sensor.name,
                    sensor.id,
                    self._sensors_history.get_states(idx),
                    delay,
                    alert_type,
                )
                if alert_type is not None and delay is not None:
                    logger.debug(
                        "Start alerting on sensor %s(%s) with history: %s",
                        sensor.name,
                        sensor.id,
                        self._sensors_history.get_states(idx),
                    )
                    self._alerting_sensors.add(sensor.id)
                    SensorAlert.start_alert(
                        sensor.id, sensor.name, delay, alert_type, sensitivity, self._broadcaster
                    )
                else:
                    logger.debug(
                        "Do not start alert on sensor %s(%s) (%s, %s)",
                        sensor.name,
                        sensor.id,
                        "missing alert type" if alert_type is None else f"{alert_type}",
                        "missing delay" if delay is None else f"{delay}",
                    )

            # stop alert of sensor
            elif (
                not self._sensors_history.is_sensor_alerting(idx)
                and sensor.id in self._alerting_sensors
            ):
                logger.debug("Stop alerting sensor %s(%s)", sensor.name, sensor.id)
                alert_sensor = self._db_session.scalar(
                    select(AlertSensor).where(
                        AlertSensor.sensor_id == sensor.id,
                        AlertSensor.end_time.is_(None),
                    )
                )
                if alert_sensor is not None:
                    alert_sensor.end_time = dt.now().astimezone()
                    logger.debug(
                        "Cleared sensor alert: alert id=%s, sensor %s(%s)",
                        alert_sensor.alert_id,
                        alert_sensor.name,
                        alert_sensor.sensor_id,
                    )
                    self._db_session.commit()
                    self._alerting_sensors.remove(sensor.id)
                else:
                    logger.debug(
                        "Cleared sensor alert: sensor %s(%s) (already closed in alert)",
                        sensor.name,
                        sensor.id,
                    )

    def on_alert_stopped(self):
        """
        Callback for the alert stopped event.
        """
        # clear all alerting sensors if disarmed
        self._alerting_sensors.clear()
        self._tampering_sensors.clear()

    def close(self):
        """
        Close the sensor handler.
        """
        logger.debug("Closing sensor handler...")
        self._alerting_sensors.clear()
        self._tampering_sensors.clear()
        if self._mqtt_client is not None:
            self._mqtt_client.close()
        if self._db_session is not None:
            self._db_session.close()
        if self._sensor_adapter is not None:
            self._sensor_adapter.close()

    @staticmethod
    def get_alert_type(sensor, monitoring_state):
        """
        Identify the alert type based on the sensor and the monitoring state.
        """
        # sabotage has higher priority
        if monitoring_state == MONITORING_READY:
            if sensor.zone.disarmed_delay is not None:
                return ALERT_SABOTAGE
        elif monitoring_state in (MONITORING_ARMED, MONITORING_ALERT, MONITORING_SABOTAGE):
            if sensor.zone.disarmed_delay is not None:
                return ALERT_SABOTAGE
            elif sensor.area.arm_state == ARM_AWAY and sensor.zone.away_alert_delay is not None:
                return ALERT_AWAY
            elif sensor.area.arm_state == ARM_STAY and sensor.zone.stay_alert_delay is not None:
                return ALERT_STAY
        elif monitoring_state in (MONITORING_ARM_DELAY, MONITORING_ALERT_DELAY):
            if sensor.zone.disarmed_delay is not None:
                return ALERT_SABOTAGE
            elif sensor.area.arm_state == ARM_AWAY and sensor.zone.away_arm_delay is not None:
                return ALERT_AWAY
            elif sensor.area.arm_state == ARM_STAY and sensor.zone.stay_arm_delay is not None:
                return ALERT_STAY
        else:
            logging.getLogger(LOG_SENSORS).error("Unknown monitoring state")

    @staticmethod
    def get_sensor_delay(sensor: Sensor, monitoring_state):
        """
        Identify the delay based on the sensor and the monitoring state.
        """
        # sabotage has higher priority
        logger = logging.getLogger(LOG_SENSORS)
        delay = None
        if monitoring_state == MONITORING_READY:
            if sensor.zone.disarmed_delay is not None:
                delay = sensor.zone.disarmed_delay
        elif monitoring_state in (MONITORING_ARMED, MONITORING_ALERT, MONITORING_SABOTAGE):
            if sensor.zone.disarmed_delay is not None:
                delay = sensor.zone.disarmed_delay
            elif sensor.area.arm_state == ARM_AWAY and sensor.zone.away_alert_delay is not None:
                delay = sensor.zone.away_alert_delay
            elif sensor.area.arm_state == ARM_STAY and sensor.zone.stay_alert_delay is not None:
                delay = sensor.zone.stay_alert_delay
        elif monitoring_state in (MONITORING_ARM_DELAY, MONITORING_ALERT_DELAY):
            if sensor.zone.disarmed_delay is not None:
                delay = sensor.zone.disarmed_delay
            elif sensor.area.arm_state == ARM_AWAY and sensor.zone.away_arm_delay is not None:
                delay = sensor.zone.away_arm_delay
            elif sensor.area.arm_state == ARM_STAY and sensor.zone.stay_arm_delay is not None:
                delay = sensor.zone.stay_arm_delay
        else:
            logger.error("Unknown monitoring state: %s", monitoring_state)

        logger.debug("Sensor %s(%s) delay: %s", sensor.name, sensor.id, delay)
        return delay
