import contextlib
from datetime import datetime as dt, timedelta
import logging

from os import environ
from queue import Empty, Queue
from threading import Thread, Timer
from time import sleep

from models import Alert, Arm, Disarm, Sensor, AlertSensor, Area, ArmSensor, ArmStates
from monitor.alert import SensorAlert

from monitor.storage import States
from monitor.adapters.power import PowerAdapter
from monitor.adapters.sensor import SensorAdapter
from monitor.broadcast import Broadcaster
from monitor.notifications.notifier import Notifier
from monitor.syren import Syren
from constants import (
    ALERT_AWAY,
    ALERT_SABOTAGE,
    ALERT_STAY,
    ARM_MIXED,
    ARM_AWAY,
    ARM_DISARM,
    ARM_STAY,
    LOG_MONITOR,
    MONITOR_ARM_AWAY,
    MONITOR_ARM_STAY,
    MONITOR_DISARM,
    MONITOR_STOP,
    MONITOR_UPDATE_CONFIG,
    MONITORING_ALERT,
    MONITORING_ALERT_DELAY,
    MONITORING_ARM_DELAY,
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
from monitor.database import Session
from monitor.socket_io import (
    send_alert_state,
    send_area_state,
    send_power_state,
    send_sensors_state,
    send_syren_state
)
from tools.queries import get_arm_delay


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
        self._alerting_sensors = set()
        self._actions = Queue()
        self._delay_timer = None

        States.set(States.MONITORING_STATE, MONITORING_STARTUP)
        States.set(States.ARM_STATE, ARM_DISARM)
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
        States.set(States.ARM_STATE, ARM_DISARM)

        self.load_sensors()

        while True:
            with contextlib.suppress(Empty):
                message = self._actions.get(True, 1 / int(environ["SAMPLE_RATE"]))
                self._logger.debug(f"Action: {message}")
                if message["action"] == MONITOR_STOP:
                    break
                elif message["action"] == MONITOR_ARM_AWAY:
                    self.arm_monitoring(
                        ARM_AWAY,
                        message.get("user_id", None),
                        message.get("keypad_id", None),
                        message.get("delay", True),
                        message.get("area_id", None)
                    )
                elif message["action"] == MONITOR_ARM_STAY:
                    self.arm_monitoring(
                        ARM_STAY,
                        message.get("user_id", None),
                        message.get("keypad_id", None),
                        message.get("delay", True),
                        message.get("area_id", None)
                    )
                elif message["action"] in (MONITORING_ALERT, MONITORING_ALERT_DELAY):
                    if self._delay_timer:
                        self._delay_timer.cancel()
                        self._delay_timer = None
                elif message["action"] == MONITOR_DISARM:
                    self.disarm_monitoring(
                        message.get("user_id", None),
                        message.get("keypad_id", None),
                        message.get("area_id", None)
                    )
                    continue
                elif message["action"] == MONITOR_UPDATE_CONFIG:
                    self.load_sensors()

            self.check_power()
            self.scan_sensors()
            self.handle_alerts()

        self.stop_alert(None)
        self._db_session.close()
        self._logger.info("Monitoring stopped")

    def are_areas_mixed_state(self):
        count = self._db_session.query(Area).filter(Area.arm_state!=ARM_DISARM).distinct(Area.arm_state).count() > 1
        self._logger.debug("Are areas mixed state %s", count > 1) 
        return count
    
    def get_areas_state(self):
        if self.are_areas_mixed_state():
            self._logger.debug("Areas state %s", ARM_MIXED)
            return ARM_MIXED
        
        state = self._db_session.query(Area).distinct(Area.arm_state).first().arm_state
        self._logger.debug("Areas state %s", state)
        return state

    def arm_monitoring(self, arm_type, user_id, keypad_id, delay, area_id):
        self._logger.info("Arming to %s", arm_type)

        if area_id is None:
            # arm the system and all the areas
            self.arm_areas(arm_type)
            self.arm_system(arm_type, user_id, keypad_id, delay)
        else:
            self.arm_area(arm_type, area_id)
            if States.get(States.ARM_STATE) == ARM_DISARM:
                self.arm_system(self.get_areas_state(), user_id=user_id, delay=False, keypad_id=None)
            else:
                areas_state = self.get_areas_state()
                # send always notification
                States.set(States.ARM_STATE, areas_state)

        self.update_arm(arm_type=arm_type, user_id=user_id, keypad_id=keypad_id)

    def update_arm(self, arm_type, user_id, keypad_id):
        # arm the system
        now = dt.now()
        arm = self._db_session.query(Arm).filter_by(disarm=None).first()
        if arm is None:
            arm = Arm(
                    arm_type=arm_type,
                    time=now,
                    user_id=user_id,
                    keypad_id=keypad_id
                )
            self._db_session.add(arm)
        else:
            self._logger.info("Arm state: %s", arm.type)
            arm.type = ArmStates.merge(arm.type, arm_type)

        for sensor in self._sensors:
            delay = Monitor.get_sensor_delay(sensor, States.get(States.MONITORING_STATE))
            self._logger.debug("Sensor (id=%s) delay: %s", sensor.id, delay)
            sensor_state = ArmSensor.from_sensor(
                arm=arm,
                sensor=sensor,
                timestamp=now,
                delay=delay
            )
            self._db_session.add(sensor_state)

        self._db_session.commit()

    def arm_system(self, arm_type, user_id, keypad_id, delay):
        self._logger.info("Arming system to %s", arm_type)

        # get max delay of arm
        arm_delay = get_arm_delay(self._db_session, arm_type) if delay else None

        def stop_arm_delay():
            self._logger.debug("End arm delay => armed!!!")
            States.set(States.MONITORING_STATE, MONITORING_ARMED)

        States.set(States.ARM_STATE, arm_type)
        self._logger.debug("Arm with delay: %s / %s", arm_delay, arm_type)
        if arm_delay is not None:
            States.set(States.MONITORING_STATE, MONITORING_ARM_DELAY)
            self._delay_timer = Timer(arm_delay, stop_arm_delay)
            self._delay_timer.start()
        else:
            States.set(States.MONITORING_STATE, MONITORING_ARMED)

    def arm_areas(self, arm_type):
        self._logger.info("Arming areas to %s", arm_type)
        self._db_session.query(Area).update({"arm_state": arm_type})
        self._db_session.commit()

    def arm_area(self, arm_type, area_id=None):
        self._logger.info("Arming area: %s to %s", area_id, arm_type)
        area = self._db_session.query(Area).get(area_id)
        area.arm_state = arm_type
        send_area_state(area.serialized)
        self._db_session.commit()

    def disarm_monitoring(self, user_id, keypad_id, area_id):
        self._logger.info("Disarming")

        if area_id is not None:
            # arm the system and the area
            self.arm_area(ARM_DISARM, area_id)
            if self.get_areas_state() == ARM_DISARM:
                self.disarm_system(user_id, keypad_id)
            else:
                areas_state = self.get_areas_state()
                if areas_state != States.get(States.ARM_STATE):
                    States.set(States.ARM_STATE, areas_state)

                self.update_arm(arm_type=ARM_DISARM, user_id=user_id, keypad_id=keypad_id)
        else:
            # disarm system and all the areas
            self.arm_areas(ARM_DISARM)
            self.disarm_system(user_id, keypad_id)

    def disarm_system(self, user_id, keypad_id):
        self._logger.info("Disarming system")
        if self._delay_timer:
            self._delay_timer.cancel()
            self._delay_timer = None

        arm = self._db_session.query(Arm).filter_by(disarm=None).first()
        disarm = Disarm(arm_id=arm.id if arm else None, time=dt.now(), user_id=user_id, keypad_id=keypad_id)
        self._db_session.add(disarm)
        self._db_session.commit()

        current_state = States.get(States.MONITORING_STATE)
        current_arm = States.get(States.ARM_STATE)
        if (
            current_state in (
                            MONITORING_ARM_DELAY,
                            MONITORING_ARMED,
                            MONITORING_ALERT_DELAY,
                            MONITORING_ALERT)
            and current_arm in (ARM_AWAY, ARM_STAY, ARM_MIXED)
            or current_state == MONITORING_SABOTAGE
        ):
            States.set(States.ARM_STATE, ARM_DISARM)
            States.set(States.MONITORING_STATE, MONITORING_READY)

        self.stop_alert(disarm)

    def check_power(self):
        # load the value once from the adapter
        new_power_source = self._powerAdapter.source_type
        if new_power_source == PowerAdapter.SOURCE_BATTERY:
            States.set(States.POWER_STATE, POWER_SOURCE_BATTERY)
            self._logger.debug("System works from battery")
        elif new_power_source == PowerAdapter.SOURCE_NETWORK:
            States.set(States.POWER_STATE, POWER_SOURCE_NETWORK)
            self._logger.debug("System works from network")

        if new_power_source == PowerAdapter.SOURCE_BATTERY and self._power_source == PowerAdapter.SOURCE_NETWORK:
            send_power_state(POWER_SOURCE_BATTERY)
            Notifier.notify_power_outage_started(dt.now())
            self._logger.info("Power outage started!")
        elif new_power_source == PowerAdapter.SOURCE_NETWORK and self._power_source == PowerAdapter.SOURCE_BATTERY:
            send_power_state(POWER_SOURCE_NETWORK)
            Notifier.notify_power_outage_stopped(dt.now())
            self._logger.info("Power outage ended!")

        self._power_source = new_power_source

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

    def load_sensors(self):
        """Load the sensors from the db in the thread to avoid session problems"""
        States.set(States.MONITORING_STATE, MONITORING_UPDATING_CONFIG)
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

    def calibrate_sensors(self):
        self._logger.info("Initialize sensor references...")
        new_references = self.measure_sensor_references()
        if len(new_references) == self._sensorAdapter.channel_count:
            self._logger.info("New references: %s", new_references)
            self.save_sensor_references(new_references)
        else:
            self._logger.error("Error measure values! %s", new_references)

    def has_uninitialized_sensor(self):
        return any(sensor.reference_value is None for sensor in self._sensors)

    def cleanup_database(self):
        changed = False
        for area in self._db_session.query(Area).filter(Area.arm_state != ARM_DISARM).all():
            area.arm_state = ARM_DISARM
            changed = True

        for sensor in self._db_session.query(Sensor).all():
            if sensor.alert:
                sensor.alert = False
                changed = True
                self._logger.debug("Cleared sensor (id=%s)", sensor.id)

        for alert_sensor in self._db_session.query(AlertSensor).filter_by(end_time=None).all():
            alert_sensor.end_time = dt.fromtimestamp(DEFAULT_DATETIME)
            self._logger.debug(
                "Cleared sensor alert (alert id=%s, sensor_id=%s)", alert_sensor.alert_id, alert_sensor.sensor_id)
            changed = True

        for alert in self._db_session.query(Alert).filter_by(end_time=None).all():
            alert.end_time = dt.fromtimestamp(DEFAULT_DATETIME)
            self._logger.debug("Cleared alert (id=%s)", alert.id)
            changed = True

        for arm in self._db_session.query(Arm).filter_by(disarm=None).all():
            disarm = Disarm(arm_id=arm.id, time=dt.now())
            self._db_session.add(disarm)
            self._logger.debug("Cleared arm (id=%s)", arm.id)
            changed = True

        if changed:
            self._logger.debug("Saved to database")
            self._db_session.commit()
        else:
            self._logger.debug("Cleared nothing")

    def save_sensor_references(self, references):
        for sensor in self._sensors:
            # skip sensors without a channel
            if sensor.channel == -1:
                continue

            sensor.reference_value = references[sensor.channel]
            self._db_session.commit()

    def measure_sensor_references(self):
        """
        Retrieves a list of vales messuared on the all the channels.
        """
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
        """
        Checking for alerting sensors if armed
        TODO: merge with handle_alerts?
        """
        changes = False
        found_alert = False
        for sensor in self._sensors:
            # skip sensor without a channel
            if sensor.channel == -1:
                continue

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

    @staticmethod
    def get_sensor_delay(sensor, monitoring_state):
        # sabotage has higher priority
        delay = None
        if monitoring_state == MONITORING_READY:
            if sensor.zone.disarmed_delay is not None:
                delay = sensor.zone.disarmed_delay
        elif monitoring_state in (MONITORING_ARMED, MONITORING_ALERT):
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
            logging.error("Unknown monitoring state: %s", monitoring_state)

        logging.info("Sensor (id=%s) delay: %s", sensor.id, delay)
        return delay
    
    @staticmethod
    def get_alert_type(sensor, monitoring_state):
        # sabotage has higher priority
        if monitoring_state == MONITORING_READY:
            if sensor.zone.disarmed_delay is not None:
                return ALERT_SABOTAGE
        elif monitoring_state in (MONITORING_ARMED, MONITORING_ALERT):
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
            logging.error("Unknown monitoring state")

    def handle_alerts(self):
        """
        Checking for alerting sensors if armed
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

        for sensor in self._sensors:
            # add new alert, enabled sensors to the alert
            if sensor.alert and sensor.id not in self._alerting_sensors and sensor.enabled:
                alert_type = Monitor.get_alert_type(sensor, current_monitoring)
                delay = Monitor.get_sensor_delay(sensor, current_monitoring)

                # do not start alert if in delay
                if (current_monitoring != MONITORING_ALERT_DELAY and
                        delay is not None and
                        (arm is not None and arm.time.replace(tzinfo=None) + timedelta(seconds=delay) > now)):
                    self._logger.debug("Ignore alert on sensor(%s): %s + %s < %s",
                                       sensor.id,
                                       arm.time.replace(tzinfo=None),
                                       timedelta(seconds=delay),
                                       now)
                    # ignore alert
                    continue

                # start the alert
                self._logger.debug("Found alerting sensor id: %s delay: %s, alert type: %s",
                                   sensor.id, delay, alert_type)
                if alert_type is not None and delay is not None:
                    self._alerting_sensors.add(sensor.id)
                    SensorAlert.start_alert(sensor.id, delay, alert_type, self._broadcaster)
                else:
                    self._logger.debug("Can't start alert")

            # stop alert of sensor
            elif not sensor.alert and sensor.id in self._alerting_sensors:
                self._logger.debug("Stop alerting sensor id: %s", sensor.id)
                alert_sensor = self._db_session.query(AlertSensor).filter_by(sensor_id=sensor.id, end_time=None).first()
                if alert_sensor is not None:
                    alert_sensor.end_time = dt.now()
                    self._logger.debug(
                        "Cleared sensor alert: alert id=%s, sensor id=%s",
                        alert_sensor.alert_id, alert_sensor.sensor_id
                    )
                    self._db_session.commit()
                    self._alerting_sensors.remove(sensor.id)
                else:
                    self._logger.debug("Cleared sensor alert: sensor id=%s (already closed in alert)", sensor.id)

    def stop_alert(self, disarm: Disarm):
        self._alerting_sensors.clear()
        SensorAlert.stop_alerts(disarm)
        Syren.stop_syren()
