import logging
from datetime import datetime as dt, timedelta
from os import environ
from time import sleep

from constants import (
    ALERT_AWAY,
    ALERT_SABOTAGE,
    ALERT_STAY,
    ARM_AWAY,
    ARM_STAY,
    LOG_MONITOR,
    MONITORING_ALERT,
    MONITORING_ALERT_DELAY,
    MONITORING_ARM_DELAY,
    MONITORING_ARMED,
    MONITORING_INVALID_CONFIG,
    MONITORING_READY,
    MONITORING_UPDATING_CONFIG,
)
from models import AlertSensor, Arm, Sensor
from monitor.adapters.sensor import SensorAdapter
from monitor.alert import SensorAlert
from monitor.communication.mqtt import MQTTClient
from monitor.database import Session
from monitor.history import SensorsHistory
from monitor.socket_io import send_sensors_state
from monitor.storage import States

MEASUREMENT_CYCLES = 2
MEASUREMENT_TIME = 3
TOLERANCE = float(environ["TOLERANCE"])


def is_close(a, b, tolerance=0.0):
    return abs(a - b) < tolerance


class SensorHandler:
    """
    Handles the sensor monitoring and alerting.
    """

    def __init__(self, session, broadcaster):
        self._logger = logging.getLogger(LOG_MONITOR)
        self._db_session = session
        self._broadcaster = broadcaster
        self._sensor_adapter = SensorAdapter()
        self._alerting_sensors = set()
        self._sensors_history = None
        self._sensors = None

        self._mqtt_client = MQTTClient()
        self._mqtt_client.connect()

    def calibrate_sensors(self):
        self._logger.info("Initialize sensor references...")
        new_references = self.measure_sensor_references()
        if len(new_references) == self._sensor_adapter.channel_count:
            self._logger.info("New references: %s", new_references)
            self.save_sensor_references(new_references)
        else:
            self._logger.error("Error measure values! %s", new_references)

    def has_uninitialized_sensor(self):
        return any(sensor.reference_value is None for sensor in self._sensors)

    def load_sensors(self):
        """Load the sensors from the db in the thread to avoid session problems"""
        States.set(States.MONITORING_STATE, MONITORING_UPDATING_CONFIG)
        send_sensors_state(None)

        # TODO: wait a little bit to see status for debug
        sleep(3)

        for sensor in self._db_session.query(Sensor).all():
            if not sensor.deleted:
                self._mqtt_client.publish_sensor_config(sensor.id, sensor.type.name, sensor.description)
                self._mqtt_client.publish_sensor_state(sensor.description, False)
            else:
                self._mqtt_client.delete_sensor(sensor.description)

        self._sensors = []
        self._sensors = self._db_session.query(Sensor).filter_by(deleted=False).all()

        # TODO: move to config
        self._sensors_history = SensorsHistory(
            len(self._sensors), int(environ["SAMPLE_RATE"]) * 10, 70
        )
        self._logger.debug("Sensors reloaded!")

        if len(self._sensors) > self._sensor_adapter.channel_count:
            self._logger.info(
                "Invalid number of sensors to monitor (Found=%s > Max=%s)",
                len(self._sensors),
                self._sensor_adapter.channel_count,
            )
            self._sensors = []
            States.set(States.MONITORING_STATE, MONITORING_INVALID_CONFIG)
        elif not self.validate_sensor_config():
            self._logger.info("Invalid channel configuration")
            self._sensors = []
            States.set(States.MONITORING_STATE, MONITORING_INVALID_CONFIG)
        elif self.has_uninitialized_sensor():
            self._logger.info("Found sensor(s) without reference value")
            self.calibrate_sensors()
            States.set(States.MONITORING_STATE, MONITORING_READY)
        else:
            States.set(States.MONITORING_STATE, MONITORING_READY)

        send_sensors_state(False)

    def validate_sensor_config(self):
        self._logger.debug("Validating config...")
        channels = set()
        for sensor in self._sensors:
            if sensor.channel in channels:
                self._logger.debug(f"Channel already in use: {sensor.channel}")
                return False
            else:
                channels.add(sensor.channel)
                self._logger.debug(f"Channel added: {sensor.channel}")

        self._logger.debug("Channels: %s", channels)
        return True

    def measure_sensor_references(self):
        """
        Retrieves a list of vales messuared on the all the channels.
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
        for sensor in self._sensors:
            # skip sensors without a channel
            if sensor.channel == -1:
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
        for sensor in self._sensors:
            # skip sensor without a channel
            if sensor.channel == -1:
                continue

            value = self._sensor_adapter.get_value(sensor.channel)

            # self._logger.debug("Sensor({}): R:{} -> V:{}".format(sensor.channel, sensor.reference_value, value))
            if not is_close(value, sensor.reference_value, TOLERANCE):
                if not sensor.alert:
                    self._logger.debug(
                        "Alert on channel: %s, (changed %s -> %s)",
                        sensor.channel,
                        sensor.reference_value,
                        value,
                    )
                    sensor.alert = True
                    self._mqtt_client.publish_sensor_state(sensor.description, True)
                    changes = True
            elif sensor.alert:
                self._logger.debug("Cleared alert on channel: %s", sensor.channel)
                sensor.alert = False
                self._mqtt_client.publish_sensor_state(sensor.description, False)
                changes = True

            if sensor.alert and sensor.enabled:
                found_alert = True

        self._sensors_history.add_states([sensor.alert for sensor in self._sensors])

        if changes:
            self._db_session.commit()
            send_sensors_state(found_alert)

    def handle_alerts(self):
        """
        Checking for alerting sensors if armed
        and start the alert if needed.
        """

        # save current state to avoid concurrency
        current_monitoring = States.get(States.MONITORING_STATE)
        now = dt.now()
        self._logger.debug("Checking sensors in %s", current_monitoring)

        arm: Arm = None
        if current_monitoring == MONITORING_ARM_DELAY:
            # wait for the arm created in the database
            # synchronizing the two threads
            while not arm:
                arm = self._db_session.query(Arm).filter_by(disarm=None).first()
            self._logger.debug("Arm: %s", arm)

        for idx, sensor in enumerate(self._sensors):
            # add new alert, enabled sensors to the alert
            if (
                self._sensors_history.is_sensor_alerting(idx)
                and sensor.id not in self._alerting_sensors
                and sensor.enabled
            ):
                alert_type = SensorHandler.get_alert_type(sensor, current_monitoring)
                delay = SensorHandler.get_sensor_delay(sensor, current_monitoring)

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
                    "Found alerting sensor id: %s delay: %s, alert type: %s",
                    sensor.id,
                    delay,
                    alert_type,
                )
                if alert_type is not None and delay is not None:
                    self._alerting_sensors.add(sensor.id)
                    SensorAlert.start_alert(
                        sensor.id, delay, alert_type, self._broadcaster
                    )
                else:
                    self._logger.debug("Can't start alert")

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
        self._alerting_sensors.clear()

    def close(self):
        """
        Close the sensor handler.
        """
        self._logger.debug("Closing sensor handler...")
        self._alerting_sensors.clear()
        self._db_session.close()

    @staticmethod
    def get_alert_type(sensor, monitoring_state):
        """
        Identify the alert type based on the sensor and the monitoring state.
        """
        # sabotage has higher priority
        if monitoring_state == MONITORING_READY:
            if sensor.zone.disarmed_delay is not None:
                return ALERT_SABOTAGE
        elif monitoring_state in (MONITORING_ARMED, MONITORING_ALERT):
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
            logging.getLogger(LOG_MONITOR).error("Unknown monitoring state")

    @staticmethod
    def get_sensor_delay(sensor: Sensor, monitoring_state):
        """
        Identify the delay based on the sensor and the monitoring state.
        """
        # sabotage has higher priority
        logger = logging.getLogger(LOG_MONITOR)
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
