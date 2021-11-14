from datetime import datetime
import logging

from os import environ
from queue import Empty, Queue
from threading import Thread, Event
from time import sleep

from models import Alert, Arm, Sensor
from monitoring.alert import SensorAlert

from monitoring import storage
from monitoring.adapters.power import PowerAdapter
from monitoring.adapters.sensor import SensorAdapter
from monitoring.broadcast import Broadcaster
from monitoring.constants import (
    ALERT_AWAY,
    ALERT_SABOTAGE,
    ALERT_STAY,
    ARM_AWAY,
    ARM_DISARM,
    ARM_STAY,
    LOG_MONITOR,
    MONITOR_ARM_AWAY,
    MONITOR_ARM_STAY,
    MONITOR_DISARM,
    MONITOR_STOP,
    MONITOR_UPDATE_CONFIG,
    MONITORING_ARMED,
    MONITORING_INVALID_CONFIG,
    MONITORING_READY,
    MONITORING_SABOTAGE,
    MONITORING_STARTUP,
    MONITORING_UPDATING_CONFIG,
    POWER_SOURCE_BATTERY,
    POWER_SOURCE_NETWORK,
    THREAD_MONITOR,
)
from monitoring.database import Session
from monitoring.socket_io import (
    send_alert_state,
    send_power_state,
    send_sensors_state,
    send_syren_state,
)


MEASUREMENT_CYCLES = 2
MEASUREMENT_TIME = 3
TOLERANCE = float(environ["TOLERANCE"])

# 2000.01.01 00:00:00
DEFAULT_DATETIME = 946684800


def is_close(a, b, tolerance=0.0):
    return abs(a - b) < tolerance


class Monitor(Thread):
    """
    classdocs
    """

    def __init__(self, broadcaster: Broadcaster):
        """
        Constructor
        """
        super(Monitor, self).__init__(name=THREAD_MONITOR)
        self._logger = logging.getLogger(LOG_MONITOR)
        self._sensorAdapter = SensorAdapter()
        self._powerAdapter = PowerAdapter()
        self._broadcaster = broadcaster
        self._sensors = None
        self._power_source = None
        self._db_session = None
        self._alerts = {}
        self._actions = Queue()
        self._stop_alert = Event()

        storage.set(storage.MONITORING_STATE, MONITORING_STARTUP)
        storage.set(storage.ARM_STATE, ARM_DISARM)
        self._broadcaster.register_queue(id(self), self._actions)
        self._logger.info("Monitoring created")

    def run(self):
        self._logger.info("Monitoring started")
        self._db_session = Session()

        # wait some seconds to build up socket IO connection before emit messages
        sleep(5)

        # remove invalid state items from db before startup
        self.cleanup_database()

        # initialize state
        send_alert_state(None)
        send_syren_state(None)
        storage.set(storage.ARM_STATE, ARM_DISARM)

        self.load_sensors()

        while True:
            try:
                message = self._actions.get(True, 1 / int(environ["SAMPLE_RATE"]))
                self._logger.debug("Action: %s" % message)
                if message["action"] == MONITOR_STOP:
                    break
                elif message["action"] == MONITOR_ARM_AWAY:
                    self.arm_monitoring(ARM_AWAY, message["user_id"])
                elif message["action"] == MONITOR_ARM_STAY:
                    self.arm_monitoring(ARM_STAY, message["user_id"])
                elif message["action"] == MONITOR_DISARM:
                    arm = self._db_session.query(Arm).filter_by(end_time=None).first()
                    if arm:
                        arm.end_time = datetime.now()
                        arm.end_user_id = message.get("user_id", None)
                        arm.end_keypad_id = message.get("keypad_id", None)
                        self._db_session.commit()

                    current_state = storage.get(storage.MONITORING_STATE)
                    current_arm = storage.get(storage.ARM_STATE)
                    if (
                        current_state == MONITORING_ARMED
                        and current_arm in (ARM_AWAY, ARM_STAY)
                        or current_state == MONITORING_SABOTAGE
                    ):
                        storage.set(storage.ARM_STATE, ARM_DISARM)
                        storage.set(storage.MONITORING_STATE, MONITORING_READY)
                    self._stop_alert.set()
                    continue
                elif message["action"] == MONITOR_UPDATE_CONFIG:
                    self.load_sensors()
            except Empty:
                pass

            self.check_power()
            self.scan_sensors()
            self.handle_alerts()

        self._stop_alert.set()
        self._db_session.close()
        self._logger.info("Monitoring stopped")

    def arm_monitoring(self, arm_type, user_id):
        self._db_session.add(
            Arm(
                arm_type=arm_type,
                start_time=datetime.now(),
                user_id=user_id,
            )
        )

        self._db_session.commit()
        storage.set(storage.ARM_STATE, arm_type)
        storage.set(storage.MONITORING_STATE, MONITORING_ARMED)
        self._stop_alert.clear()

    def check_power(self):
        # load the value once from the adapter
        new_power_source = self._powerAdapter.source_type
        if new_power_source == PowerAdapter.SOURCE_BATTERY:
            storage.set(storage.POWER_STATE, POWER_SOURCE_BATTERY)
            self._logger.debug("System works from battery")
        elif new_power_source == PowerAdapter.SOURCE_NETWORK:
            storage.set(storage.POWER_STATE, POWER_SOURCE_NETWORK)
            self._logger.debug("System works from network")

        if new_power_source == PowerAdapter.SOURCE_BATTERY and self._power_source == PowerAdapter.SOURCE_NETWORK:
            send_power_state(POWER_SOURCE_BATTERY)
            self._logger.info("Power outage started!")
        elif new_power_source == PowerAdapter.SOURCE_NETWORK and self._power_source == PowerAdapter.SOURCE_BATTERY:
            send_power_state(POWER_SOURCE_NETWORK)
            self._logger.info("Power outage ended!")

        self._power_source = new_power_source

    def validate_sensor_config(self):
        self._logger.debug("Validating config...")
        channels = set()
        for sensor in self._sensors:
            if sensor.channel in channels:
                self._logger.debug("Channels: %s", channels)
                return False
            else:
                channels.add(sensor.channel)

        self._logger.debug("Channels: %s", channels)
        return True

    def load_sensors(self):
        """Load the sensors from the db in the thread to avoid session problems"""
        storage.set(storage.MONITORING_STATE, MONITORING_UPDATING_CONFIG)
        send_sensors_state(None)

        # TODO: wait a little bit to see status for debug
        sleep(3)

        # !!! delete old sensors before load again
        self._sensors = []
        self._sensors = self._db_session.query(Sensor).filter_by(deleted=False).all()
        self._logger.debug("Sensors reloaded!")

        if len(self._sensors) > self._sensorAdapter.channel_count:
            self._logger.info(
                "Invalid number of sensors to monitor (Found=%s > Max=%s)",
                len(self._sensors),
                self._sensorAdapter.channel_count,
            )
            self._sensors = []
            storage.set(storage.MONITORING_STATE, MONITORING_INVALID_CONFIG)
        elif not self.validate_sensor_config():
            self._logger.info("Invalid channel configuration")
            self._sensors = []
            storage.set(storage.MONITORING_STATE, MONITORING_INVALID_CONFIG)
        elif self.has_uninitialized_sensor():
            self._logger.info("Found sensor(s) without reference value")
            self.calibrate_sensors()
            storage.set(storage.MONITORING_STATE, MONITORING_READY)
        else:
            storage.set(storage.MONITORING_STATE, MONITORING_READY)

        send_sensors_state(False)

    def calibrate_sensors(self):
        self._logger.info("Initialize sensor references...")
        new_references = self.measure_sensor_references()
        if len(new_references) == self._sensorAdapter.channel_count:
            self._logger.info("New references: %s", new_references)
            self.save_sensor_references(new_references)
        else:
            self._logger.error("Error measure values! %s", self._references)

    def has_uninitialized_sensor(self):
        return any(sensor.reference_value is None for sensor in self._sensors)

    def cleanup_database(self):
        changed = False
        for sensor in self._db_session.query(Sensor).all():
            if sensor.alert:
                sensor.alert = False
                changed = True
                self._logger.debug("Cleared sensor")

        for alert in self._db_session.query(Alert).filter_by(end_time=None).all():
            alert.end_time = datetime.fromtimestamp(DEFAULT_DATETIME)
            self._logger.debug("Cleared alert")
            changed = True

        for arm in self._db_session.query(Arm).filter_by(end_time=None).all():
            arm.end_time = datetime.fromtimestamp(DEFAULT_DATETIME)
            self._logger.debug("Cleared arm")
            changed = True

        if changed:
            self._logger.debug("Cleared db")
            self._db_session.commit()
        else:
            self._logger.debug("Cleared nothing")

    def save_sensor_references(self, references):
        for sensor in self._sensors:
            sensor.reference_value = references[sensor.channel]
            self._db_session.commit()

    def measure_sensor_references(self):
        measurements = []
        for _ in range(MEASUREMENT_CYCLES):
            measurements.append(self._sensorAdapter.get_values())
            sleep(MEASUREMENT_TIME)

        self._logger.debug("Measured values: %s", measurements)

        references = {}
        for channel in range(self._sensorAdapter.channel_count):
            value_sum = sum(measurements[cycle][channel] for cycle in range(MEASUREMENT_CYCLES))
            references[channel] = value_sum / MEASUREMENT_CYCLES

        return list(references.values())

    def scan_sensors(self):
        changes = False
        found_alert = False
        for sensor in self._sensors:
            value = self._sensorAdapter.get_value(sensor.channel)
            # self._logger.debug("Sensor({}): R:{} -> V:{}".format(sensor.channel, sensor.reference_value, value))
            if not is_close(value, sensor.reference_value, TOLERANCE):
                if not sensor.alert:
                    self._logger.debug(
                        "Alert on channel: %s, (changed %s -> %s)", sensor.channel, sensor.reference_value, value
                    )
                    sensor.alert = True
                    changes = True
            elif sensor.alert:
                self._logger.debug("Cleared alert on channel: %s", sensor.channel)
                sensor.alert = False
                changes = True

            if sensor.alert and sensor.enabled:
                found_alert = True

        if changes:
            self._db_session.commit()
            send_sensors_state(found_alert)

    def handle_alerts(self):
        """
        Checking for alerting sensors if armed
        """

        # save current state to avoid concurrency
        current_arm = storage.get(storage.ARM_STATE)

        changes = False
        for sensor in self._sensors:
            # add new alerting, enabled sensors to the alert
            if sensor.alert and sensor.id not in self._alerts and sensor.enabled:
                alert_type = None
                # sabotage has higher priority
                if sensor.zone.disarmed_delay is not None:
                    alert_type = ALERT_SABOTAGE
                    delay = sensor.zone.disarmed_delay
                elif current_arm == ARM_AWAY and sensor.zone.away_alert_delay is not None:
                    alert_type = ALERT_AWAY
                    delay = sensor.zone.away_alert_delay
                elif current_arm == ARM_STAY and sensor.zone.stay_alert_delay is not None:
                    alert_type = ALERT_STAY
                    delay = sensor.zone.stay_alert_delay

                if alert_type:
                    self._alerts[sensor.id] = {"alert": SensorAlert(sensor.id, delay, alert_type, self._stop_alert)}
                    self._alerts[sensor.id]["alert"].start()
                    self._stop_alert.clear()
                    changes = True
            # stop alert
            elif not sensor.alert and sensor.id in self._alerts:
                # TODO: if removing SensorAlert will block alerting
                del self._alerts[sensor.id]

        if changes:
            self._logger.debug("Save sensor changes")
            self._db_session.commit()
