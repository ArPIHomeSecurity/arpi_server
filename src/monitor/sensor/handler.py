"""
Sensor monitoring and alerting.
"""

import logging
from datetime import datetime as dt, timedelta
from os import environ
from time import sleep

from monitor.adapters.sensor import get_sensor_adapter
from sqlalchemy import select

from constants import (
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
from models import AlertSensor, Arm, Sensor
from monitor.alert import SensorAlert
from monitor.communication.mqtt import MQTTClient
from monitor.config_helper import AlertSensitivityConfig, load_alert_sensitivity_config
from monitor.database import get_database_session
from monitor.sensor.detector import detect_alert, detect_error, wiring_config
from monitor.sensor.history import SensorsHistory
from monitor.socket_io import send_sensors_error, send_sensors_state
from monitor.storage import State, States


MEASUREMENT_CYCLES = 2
MEASUREMENT_TIME = 3


# alert time window length in seconds
ALERT_WINDOW = int(environ.get("ALERT_TIME_WINDOW", 1))
# threshold in the percent of high values in the time window (0-100)
ALERT_THRESHOLD = int(environ.get("ALERT_THRESHOLD", 100))
# board version
BOARD_VERSION = int(environ["BOARD_VERSION"])


class SensorHandler:
    """
    Handles the sensors monitoring and alerting.
    """

    def __init__(self, broadcaster):
        self._logger = logging.getLogger(LOG_SENSORS)
        self._db_session = None
        self._broadcaster = broadcaster
        self._sensor_adapter = None
        self._alerting_sensors = set()
        self._sensors_history = None
        self._sensors = None
        self._mqtt_client = None


    def initialize(self):
        self._mqtt_client = MQTTClient()
        self._mqtt_client.connect(client_id="arpi_sensors")
        self._db_session = get_database_session()
        self._sensor_adapter = get_sensor_adapter()

    def update_mqtt_config(self):
        """
        Update the MQTT configuration.
        """
        if self._mqtt_client is not None:
            self._mqtt_client.close()
            self._mqtt_client.connect(client_id="arpi_sensors")

    def calibrate_sensors(self):
        """
        Calibrate the sensors: update the reference value of the sensors.
        """
        self._logger.info("Initialize sensor references...")
        new_references = self.measure_sensor_references()
        if len(new_references) == self._sensor_adapter.channel_count:
            self._logger.info("New references: %s", [float(f"{x:.3f}") for x in new_references])
            self.save_sensor_references(new_references)
        else:
            self._logger.error("Error measure values! %s", [float(f"{x:.3f}") for x in new_references])

    def has_uncalibrated_sensor(self):
        """
        Check if there is any sensor without reference value.
        """
        for sensor in self._sensors:
            if sensor.reference_value is None and sensor.channel != -1:
                self._logger.info(
                    "Found uncalibrated sensor: %s => %s", sensor.id, sensor.description
                )
                return True

        self._logger.info("No uncalibrated sensors found")
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
        self._sensors = self._db_session.query(Sensor).filter_by(deleted=False).all()
        self._logger.debug("Sensors reloaded!")

        alert_sensitivity = load_alert_sensitivity_config(session=self._db_session)
        if alert_sensitivity is None:
            self._logger.info("Alert sensitivity config not found!")
            alert_sensitivity = AlertSensitivityConfig(None, None)

        # initialize the sensors history
        sample_rate = int(environ["SAMPLE_RATE"])
        if alert_sensitivity.monitor_period is None:
            # instant alerts
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
                if sensor.monitor_period is None:
                    # instant alert
                    self._sensors_history.set_sensitivity(
                        idx, 1, 100
                    )
                else:
                    self._sensors_history.set_sensitivity(
                        idx,
                        int(sample_rate * sensor.monitor_period),
                        sensor.monitor_threshold,
                    )

        # keep config update state
        sleep(2)

        # verify the sensor configuration
        if len(self._sensors) > self._sensor_adapter.channel_count:
            self._logger.info(
                "Invalid number of sensors to monitor (Found=%s > Max=%s)",
                len(self._sensors),
                self._sensor_adapter.channel_count,
            )
            self._sensors = []
            States.set(State.MONITORING, MONITORING_INVALID_CONFIG)
        elif not self.validate_sensor_config():
            self._logger.info("Invalid channel configuration")
            self._sensors = []
            States.set(State.MONITORING, MONITORING_INVALID_CONFIG)
        elif self.has_uncalibrated_sensor():
            self._logger.info("Found sensor(s) without reference value")
            self.calibrate_sensors()
            States.set(State.MONITORING, monitoring_state)
        else:
            States.set(State.MONITORING, monitoring_state)

        send_sensors_state(False)

    def publish_sensors(self):
        """
        Publish the sensor configuration to the MQTT.
        """
        sensors = self._db_session.execute(select(Sensor)).scalars().all()
        for sensor in sensors:
            if not sensor.deleted:
                self._mqtt_client.publish_sensor_config(
                    sensor.id, sensor.type.name, sensor.name
                )
                self._mqtt_client.publish_sensor_state(sensor.name, False)
            else:
                self._mqtt_client.delete_sensor(sensor.name)

    def validate_sensor_config(self):
        """
        Validate the sensor configuration.
        * check if there is any sensor with the same channel
        """
        self._logger.debug("Validating sensor configuration...")
        channels = set()
        for sensor in self._sensors:
            if sensor.channel in channels and BOARD_VERSION == 2:
                self._logger.debug("Channel already in use: %s", sensor.channel)
                return False
            else:
                channels.add(sensor.channel)
                self._logger.debug("Channel added: %s", sensor.channel)

        self._logger.debug("Channels: %s", channels)
        return True

    def measure_sensor_references(self):
        """
        Retrieves a list of vales measured on the all the channels.
        """
        measurements = []
        for _ in range(MEASUREMENT_CYCLES):
            measurements.append(self._sensor_adapter.get_values())
            sleep(MEASUREMENT_TIME)

        self._logger.debug("Measured values: %s", measurements)

        references = {}
        for channel in range(self._sensor_adapter.channel_count):
            value_sum = sum(
                measurements[cycle][channel] for cycle in range(MEASUREMENT_CYCLES)
            )
            references[channel] = value_sum / MEASUREMENT_CYCLES

        return list(references.values())

    def save_sensor_references(self, references):
        """
        Save the reference values to the database.
        """
        for sensor in self._sensors:
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
        found_alert = False
        found_error = False
        for sensor in self._sensors:
            # skip sensor without a channel
            if sensor.channel == -1:
                continue

            value = self._sensor_adapter.get_value(sensor.channel)

            is_alert = detect_alert(sensor, value)
            self._logger.trace(
                "Sensor %s (CH%02d) value: %s, ref: %s => alert: %s",
                sensor.description,
                sensor.channel,
                float(f"{value:.3f}"),
                float(f"{sensor.reference_value:.3f}"),
                is_alert,
            )
            if is_alert != sensor.alert:
                sensor.alert = is_alert
                self._mqtt_client.publish_sensor_state(sensor.name, sensor.alert)
                changes = True

            is_error = detect_error(sensor, value)
            self._logger.trace(
                "Sensor %s (CH%02d) value: %s, ref: %s => error: %s",
                sensor.description,
                sensor.channel,
                float(f"{value:.3f}"),
                float(f"{sensor.reference_value:.3f}"),
                is_error,
            )
            if is_error != sensor.error:
                sensor.error = is_error
                # self._mqtt_client.publish_sensor_state(sensor.name, sensor.error)
                changes = True

            if sensor.alert and sensor.enabled:
                found_alert = True

            if sensor.error and sensor.enabled:
                found_error = True

        self._sensors_history.add_states([sensor.alert for sensor in self._sensors])

        if changes:
            self._db_session.commit()
            send_sensors_state(found_alert)
            send_sensors_error(found_error)


    def handle_alerts(self):
        """
        Checking for alerting sensors if armed
        and start the alert if needed.
        """

        # save current state to avoid concurrency
        current_monitoring = States.get(State.MONITORING)
        now = dt.now()
        self._logger.trace("Checking sensors in %s", current_monitoring)

        arm: Arm = None
        if current_monitoring == MONITORING_ARM_DELAY:
            # wait 5 seconds for the arm created in the database
            # synchronizing the two threads
            retries = 0
            while not arm and retries < 50:
                arm = self._db_session.query(Arm).filter_by(disarm=None).first()
                retries += 1
                if not arm:
                    sleep(0.1)

            if not arm:
                raise RuntimeError("No arm found in the database while in ARM_DELAY state")

            self._logger.debug("Arm: %s", arm)

        for idx, sensor in enumerate(self._sensors):
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
                self._logger.warning(
                    "Sensor %s (CH%02d) has suppressed alert! %ss%s%| (%r)",
                    sensor.description,
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
                    and (
                        arm is not None
                        and arm.time.replace(tzinfo=None) + timedelta(seconds=delay)
                        > now
                    )
                ):
                    self._logger.debug(
                        "Ignore alert on sensor(%s): %s + %s < %s",
                        sensor.id,
                        arm.time.replace(tzinfo=None),
                        timedelta(seconds=delay),
                        now,
                    )
                    # ignore alert
                    continue

                # start the alert
                self._logger.debug(
                    "Found alerting sensor id: %s, states: %s, delay: %s, alert type: %s",
                    sensor.id,
                    self._sensors_history.get_states(idx),
                    delay,
                    alert_type,
                )
                if alert_type is not None and delay is not None:
                    self._logger.debug(
                        "Start alerting on sensor with history: %s => %s",
                        sensor,
                        self._sensors_history.get_states(idx),
                    )
                    self._alerting_sensors.add(sensor.id)
                    SensorAlert.start_alert(
                        sensor.id, delay, alert_type, sensitivity, self._broadcaster
                    )

                if alert_type is None:
                    self._logger.debug("Do not start alert on sensor: %s (no alert type)", sensor.id)
                if delay is None:
                    self._logger.debug("Do not start alert on sensor: %s (no delay)", sensor.id)

            # stop alert of sensor
            elif (
                not self._sensors_history.is_sensor_alerting(idx)
                and sensor.id in self._alerting_sensors
            ):
                self._logger.debug("Stop alerting sensor id: %s", sensor.id)
                alert_sensor = (
                    self._db_session.query(AlertSensor)
                    .filter_by(sensor_id=sensor.id, end_time=None)
                    .first()
                )
                if alert_sensor is not None:
                    alert_sensor.end_time = dt.now()
                    self._logger.debug(
                        "Cleared sensor alert: alert id=%s, sensor id=%s",
                        alert_sensor.alert_id,
                        alert_sensor.sensor_id,
                    )
                    self._db_session.commit()
                    self._alerting_sensors.remove(sensor.id)
                else:
                    self._logger.debug(
                        "Cleared sensor alert: sensor id=%s (already closed in alert)",
                        sensor.id,
                    )

    def on_alert_stopped(self):
        """
        Callback for the alert stopped event.
        """
        # clear all alerting sensors if disarmed
        self._alerting_sensors.clear()

    def close(self):
        """
        Close the sensor handler.
        """
        self._logger.debug("Closing sensor handler...")
        self._alerting_sensors.clear()
        self._mqtt_client.close()

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
            elif (
                sensor.area.arm_state == ARM_AWAY
                and sensor.zone.away_alert_delay is not None
            ):
                return ALERT_AWAY
            elif (
                sensor.area.arm_state == ARM_STAY
                and sensor.zone.stay_alert_delay is not None
            ):
                return ALERT_STAY
        elif monitoring_state in (MONITORING_ARM_DELAY, MONITORING_ALERT_DELAY):
            if sensor.zone.disarmed_delay is not None:
                return ALERT_SABOTAGE
            elif (
                sensor.area.arm_state == ARM_AWAY
                and sensor.zone.away_arm_delay is not None
            ):
                return ALERT_AWAY
            elif (
                sensor.area.arm_state == ARM_STAY
                and sensor.zone.stay_arm_delay is not None
            ):
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
        elif monitoring_state in (MONITORING_ARMED, MONITORING_ALERT):
            if sensor.zone.disarmed_delay is not None:
                delay = sensor.zone.disarmed_delay
            elif (
                sensor.area.arm_state == ARM_AWAY
                and sensor.zone.away_alert_delay is not None
            ):
                delay = sensor.zone.away_alert_delay
            elif (
                sensor.area.arm_state == ARM_STAY
                and sensor.zone.stay_alert_delay is not None
            ):
                delay = sensor.zone.stay_alert_delay
        elif monitoring_state in (MONITORING_ARM_DELAY, MONITORING_ALERT_DELAY):
            if sensor.zone.disarmed_delay is not None:
                delay = sensor.zone.disarmed_delay
            elif (
                sensor.area.arm_state == ARM_AWAY
                and sensor.zone.away_arm_delay is not None
            ):
                delay = sensor.zone.away_arm_delay
            elif (
                sensor.area.arm_state == ARM_STAY
                and sensor.zone.stay_arm_delay is not None
            ):
                delay = sensor.zone.stay_arm_delay
        else:
            logger.error("Unknown monitoring state: %s", monitoring_state)

        logger.debug("Sensor (id=%s) delay: %s", sensor.id, delay)
        return delay
