import logging

from datetime import datetime
from threading import Thread, Event

from models import Alert, AlertSensor, Arm, Disarm, Sensor
from monitor.storage import States
from monitor.broadcast import Broadcaster
from monitor.database import Session
from monitor.notifications.notifier import Notifier
from monitor.socket_io import send_syren_state, send_alert_state
from monitor.syren import Syren
from constants import (
    ALERT_SABOTAGE,
    MONITORING_ALERT,
    MONITORING_ALERT_DELAY,
    MONITORING_SABOTAGE,
    LOG_ALERT,
    THREAD_ALERT
)


class SensorAlert(Thread):
    """
    Handling of alerts from sensors and trigger syren.
    """

    _stop_event = Event()

    @classmethod
    def start_alert(cls, sensor_id, delay, alert_type, broadcaster: Broadcaster):
        cls._stop_event.clear()
        SensorAlert(sensor_id, delay, alert_type, broadcaster).start()

    @classmethod
    def stop_alerts(cls, disarm: Disarm):
        cls._stop_event.set()
        send_alert_state(None)

        db_session = Session()
        alert = db_session.query(Alert).filter_by(end_time=None).first()
        if alert:
            alert.end_time = datetime.now()
            alert.disarm = disarm
            db_session.commit()

            send_alert_state(None)
            send_syren_state(None)
            Notifier.notify_alert_stopped(alert.id, alert.end_time)
            logging.getLogger(LOG_ALERT).info("Alerts stopped")

    def __init__(self, sensor_id, delay, alert_type, broadcaster: Broadcaster):
        """
        Constructor
        """
        super(SensorAlert, self).__init__(name=THREAD_ALERT)
        self._logger = logging.getLogger(LOG_ALERT)
        self._sensor_id = sensor_id
        self._delay = delay
        self._alert_type = alert_type
        self._broadcaster = broadcaster

    def run(self):

        start_time = datetime.now()
        self._logger.debug("Alert prepared in arm state: %s", self._alert_type)
        self._logger.info(
            "Alert prepared on sensor (id:%s) with %s seconds delay",
            self._sensor_id,
            self._delay,
        )

        if self._delay > 0:
            States.set(States.MONITORING_STATE, MONITORING_ALERT_DELAY)
            self._broadcaster.send_message({"action": MONITORING_ALERT_DELAY})

        if self._stop_event.wait(self._delay):
            self._logger.info("Sensor (%s) alert stopped before %s seconds delay",
                              self._sensor_id,
                              self._delay)
            return

        self._logger.info("Alert started sensor (id:%s) after %s seconds delay",
                          self._sensor_id,
                          self._delay)

        new_alert = False
        session = Session()
        alert = session.query(Alert).filter_by(end_time=None).first()
        if alert is None:
            alert = self.create_alert(session)
            new_alert = True

        self.add_sensor_to_alert(session=session, alert=alert, start_time=start_time, delay=self._delay)

        # send notification only on the first sensor alert
        if new_alert:
            sensor_descriptions = [
                f"{item.sensor.description}(id:{item.sensor.id}/CH{(item.sensor.channel+1):02d})"
                for item in alert.sensors
            ]
            Notifier.notify_alert_started(alert.id, sensor_descriptions, alert.start_time)

        session.close()

        Syren.start_syren()
        if self._alert_type == ALERT_SABOTAGE:
            States.set(States.MONITORING_STATE, MONITORING_SABOTAGE)
            self._broadcaster.send_message({"action": MONITORING_SABOTAGE})
        else:
            States.set(States.MONITORING_STATE, MONITORING_ALERT)
            self._broadcaster.send_message({"action": MONITORING_ALERT})

    def create_alert(self, session) -> Alert:
        """
        Creates an alert by querying the database for an active arm,
        setting the start time to the current time, and initializing an empty list of sensors.
        The alert is then added to the database and returned.
        """
        arm = session.query(Arm).filter_by(disarm=None).first()
        start_time = datetime.now()
        alert = Alert(arm=arm, start_time=start_time, sensors=[])
        session.add(alert)
        session.commit()
        return alert

    def add_sensor_to_alert(self, session, alert: Alert, start_time, delay):
        """
        Adds a sensor to the given alert with the specified start time and delay.
        If the sensor is already added to the alert, it will not be added again.
        """
        sensor = session.query(Sensor).get(self._sensor_id)
        already_added = any(
            alert_sensor.sensor.id == sensor.id
            for alert_sensor in alert.sensors
        )

        # we can't add a sensor twice to the same alert, check database AlertSensor schema
        if already_added:
            self._logger.debug("Sensor by id: %s already added", self._sensor_id)
            return

        alert_sensor = AlertSensor(
            channel=sensor.channel,
            type_id=sensor.type_id,
            name=sensor.name,
            description=sensor.description,
            start_time=start_time,
            delay=delay,
            silent=sensor.silent_alarm,
            suppression=f"{sensor.monitor_size}/{sensor.monitor_threshold}"
        )
        alert_sensor.sensor = sensor
        alert.sensors.append(alert_sensor)
        alert.silent = all([item.silent for item in alert.sensors])
        send_syren_state(not alert.silent)
        session.commit()
        self._logger.debug("Added sensor by id: %s", self._sensor_id)

        send_alert_state(alert.serialized)
