import logging
import json
from datetime import datetime
from multiprocessing import Queue
from threading import Thread, BoundedSemaphore
from time import time

from models import Alert, AlertSensor, Arm, Option, Sensor
from monitoring import storage
from monitoring.adapters.syren import SyrenAdapter
from monitoring.broadcast import Broadcaster
from monitoring.database import Session
from monitoring.notifications.notifier import Notifier
from monitoring.socket_io import send_syren_state, send_alert_state
from constants import (
    ALERT_SABOTAGE,
    MONITORING_ALERT,
    MONITORING_ALERT_DELAY,
    MONITORING_SABOTAGE,
    LOG_ALERT,
    THREAD_ALERT
)
from queue import Empty


class SensorAlert(Thread):
    """
    Handling of alerts from sensors and trigger syren alert.
    """

    _sensor_queue = Queue()

    def __init__(self, sensor_id, delay, alert_type, stop_event, broadcaster: Broadcaster):
        """
        Constructor
        """
        super(SensorAlert, self).__init__(name=THREAD_ALERT)
        self._logger = logging.getLogger(LOG_ALERT)
        self._sensor_id = sensor_id
        self._delay = delay
        self._alert_type = alert_type
        self._stop_event = stop_event
        self._broadcaster = broadcaster

    def run(self):
        self._logger.info(
            "Alert (%s) started on sensor (id:%s) waiting %s sec before starting syren",
            self._alert_type,
            self._sensor_id,
            self._delay,
        )

        if self._delay > 0:
            storage.set(storage.MONITORING_STATE, MONITORING_ALERT_DELAY)
            self._broadcaster.send_message({"action": MONITORING_ALERT_DELAY})

        if not self._stop_event.wait(self._delay):
            self._logger.info(
                "Start syren because not disarmed (%s) sensor (id:%s) in %s secs",
                self._alert_type,
                self._sensor_id,
                self._delay,
            )
            SyrenAlert.start_syren(self._alert_type, SensorAlert._sensor_queue, self._stop_event)
            SensorAlert._sensor_queue.put(self._sensor_id)
            if self._alert_type == ALERT_SABOTAGE:
                storage.set(storage.MONITORING_STATE, MONITORING_SABOTAGE)
                self._broadcaster.send_message({"action": MONITORING_SABOTAGE})
            else:
                storage.set(storage.MONITORING_STATE, MONITORING_ALERT)
                self._broadcaster.send_message({"action": MONITORING_ALERT})
        else:
            self._logger.info("Sensor alert stopped")


class SyrenAlert(Thread):
    """
    Handling of syren alerts.
    """

    # default timing
    ALERT_TIME = 10  # 10 minutes
    SUSPEND_TIME = 5  # 5 minutes

    _semaphore = BoundedSemaphore()
    _alert: Alert = None

    @classmethod
    def start_syren(cls, alert_type, sensor_queue, stop_event):
        with cls._semaphore:
            if not cls._alert:
                cls._alert = SyrenAlert(alert_type, sensor_queue, stop_event)
                cls._alert.start()
            return cls._alert

    @classmethod
    def get_sensor_queue(cls):
        return cls._sensor_queue

    def __init__(self, arm_type, sensor_queue, stop_event):
        super(SyrenAlert, self).__init__(name=THREAD_ALERT)
        self._alert_type = arm_type
        self._sensor_queue = sensor_queue
        self._stop_event = stop_event
        self._logger = logging.getLogger(LOG_ALERT)
        self._syren = SyrenAdapter()
        self._alert = None
        self._db_session = None

    def run(self):
        self._db_session = Session()

        self.load_syren_config()

        self.start_alert()
        start_time = time()
        syren_is_on = True
        while not self._stop_event.is_set() and not self._stop_event.wait(timeout=1):
            now = time()
            if (now - start_time > SyrenAlert.ALERT_TIME) and syren_is_on:
                start_time = time()
                syren_is_on = False
                self._syren.alert(syren_is_on)
                send_syren_state(syren_is_on)
                self._logger.info("Syren suspended")
            elif (now - start_time > SyrenAlert.SUSPEND_TIME) and not syren_is_on:
                start_time = time()
                syren_is_on = True
                self._syren.alert(syren_is_on)
                send_syren_state(syren_is_on)
                self._logger.info("Syren started")

            self.handle_sensors()

        self.stop_alert()
        self._db_session.close()

    def load_syren_config(self):
        syren_config = self._db_session.query(Option).filter_by(name="syren", section="timing").first()
        if syren_config:
            syren_config = json.loads(syren_config.value)
        else:
            self._logger.warn("Missing syren settings!")
            return

        SyrenAlert.ALERT_TIME = syren_config["alert_time"]
        SyrenAlert.SUSPEND_TIME = syren_config["suspend_time"]

    def start_alert(self):
        start_time = datetime.now()
        arm = self._db_session.query(Arm).filter_by(end_time=None).first()
        self._alert = Alert(arm=arm, start_time=start_time, sensors=[])
        self._db_session.add(self._alert)
        self._db_session.commit()
        self.handle_sensors()

        send_alert_state(self._alert.serialize)
        self._syren.alert(True)
        send_syren_state(True)

        self._logger.debug("Alerting sensors: %s", self._alert.sensors)
        sensor_descriptions = list(
            map(
                lambda item: f"{item.sensor.description}(id:{item.sensor.id}/CH{item.sensor.channel+1})",
                self._alert.sensors,
            )
        )
        Notifier.notify_alert_started(self._alert.id, sensor_descriptions, start_time)

        self._logger.info("Alert started")

    def stop_alert(self):
        with SyrenAlert._semaphore:
            SyrenAlert._alert = None
            self.handle_sensors()
            self._alert.end_time = datetime.now()
            self._db_session.commit()

            send_alert_state(None)
            self._syren.alert(False)
            send_syren_state(None)
            Notifier.notify_alert_stopped(self._alert.id, self._alert.end_time)

        self._logger.info("Alert stopped")

    def handle_sensors(self):
        sensor_added = False
        try:
            while True:
                sensor_id = self._sensor_queue.get(False)
                sensor = self._db_session.query(Sensor).get(sensor_id)

                already_added = any(
                    alert_sensor.sensor.id == sensor.id
                    for alert_sensor in self._alert.sensors
                )

                if not already_added:
                    alert_sensor = AlertSensor(
                        channel=sensor.channel, type_id=sensor.type_id, description=sensor.description
                    )
                    alert_sensor.sensor = sensor
                    self._alert.sensors.append(alert_sensor)
                    sensor_added = True
                    self._logger.debug("Added sensor by id: %s", sensor_id)
                else:
                    self._logger.debug("Sensor by id: %s already added", sensor_id)
        except Empty:
            pass

        if sensor_added:
            self._db_session.commit()
            send_alert_state(self._alert.serialize)

        return sensor_added
