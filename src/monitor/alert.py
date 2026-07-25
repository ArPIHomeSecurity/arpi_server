import logging
from datetime import datetime
from threading import Event, Thread

from monitor.actions import (
    MonitoringAlertCommand,
    MonitoringAlertDelayCommand,
    MonitoringSabotageCommand,
)
from monitor.broadcast import Broadcaster
from monitor.config.models import AlertSensitivityConfig, SyrenConfig
from monitor.database import get_database_session
from monitor.notifications.notifier import Notifier
from monitor.socket_io import send_alert_state, send_syren_state
from monitor.storage import State, States
from monitor.syren import Syren
from utils.constants import (
    ALERT_SABOTAGE,
    LOG_ALERT,
    MONITORING_ALERT,
    MONITORING_ALERT_DELAY,
    MONITORING_SABOTAGE,
    THREAD_ALERT,
)
from utils.models import Alert, AlertSensor, Arm, Disarm, Sensor

logger = logging.getLogger(LOG_ALERT)


def resolve_silent(system_silent: bool | None, sensor_silent: bool | None) -> bool:
    if system_silent is False:
        return False
    if system_silent is True:
        return sensor_silent if sensor_silent is not None else True
    return sensor_silent if sensor_silent is not None else False


class SensorAlert(Thread):
    """
    Handling of alerts from sensors and trigger syren.
    """

    _stop_event = Event()

    @classmethod
    def start_alert(
        cls,
        sensor_id,
        delay,
        alert_type,
        sensitivity: AlertSensitivityConfig,
        broadcaster: Broadcaster,
    ):
        cls._stop_event.clear()
        SensorAlert(sensor_id, delay, alert_type, sensitivity, broadcaster).start()

    @classmethod
    def stop_alerts(cls, disarm_id: int):
        cls._stop_event.set()
        send_alert_state(None)

        if disarm_id is not None:
            db_session = get_database_session()
            alert = db_session.query(Alert).filter_by(end_time=None).first()
            disarm = db_session.query(Disarm).get(disarm_id)
            if alert:
                alert.end_time = datetime.now()
                alert.disarm = disarm
                db_session.commit()
                Notifier.notify_alert_stopped(alert.id, alert.end_time)

        send_alert_state(None)
        send_syren_state(None)
        logger.info("Alerts stopped")

    def __init__(
        self,
        sensor_id,
        delay,
        alert_type,
        sensitivity: AlertSensitivityConfig,
        broadcaster: Broadcaster,
    ):
        """
        Constructor
        """
        super().__init__(name=THREAD_ALERT)
        self._sensor_id = sensor_id
        self._delay = delay
        self._alert_type = alert_type
        self._sensitivity = sensitivity
        self._broadcaster = broadcaster

    def run(self):

        start_time = datetime.now()
        logger.debug("Alert prepared in arm state: %s", self._alert_type)
        logger.info(
            "Alert prepared on sensor (id:%s) with %s seconds delay",
            self._sensor_id,
            self._delay,
        )

        if self._delay > 0:
            States.set(State.MONITORING, MONITORING_ALERT_DELAY)
            self._broadcaster.send_message(MonitoringAlertDelayCommand())

        if self._stop_event.wait(self._delay):
            logger.info(
                "Sensor (%s) alert stopped before %s seconds delay",
                self._sensor_id,
                self._delay,
            )
            return

        logger.info(
            "Alert started sensor (id:%s) after %s seconds delay",
            self._sensor_id,
            self._delay,
        )

        new_alert = False
        session = get_database_session()
        alert = session.query(Alert).filter_by(end_time=None).first()
        if alert is None:
            alert = self.create_alert(session)
            new_alert = True

        syren_config = SyrenConfig.load_config()
        if syren_config is None:
            logger.info("Missing syren settings, using defaults")
            syren_config = SyrenConfig(
                silent=Syren.SILENT, delay=Syren.DELAY, duration=Syren.DURATION
            )

        self.add_sensor_to_alert(
            session=session,
            alert=alert,
            start_time=start_time,
            delay=self._delay,
            syren_config=syren_config,
        )

        # send notification only on the first sensor alert
        if new_alert:
            sensor_descriptions = [
                f"{item.sensor.description}(id:{item.sensor.id}/CH{(item.sensor.channel + 1):02d})"
                for item in alert.sensors
            ]
            Notifier.notify_alert_started(alert.id, sensor_descriptions, alert.start_time)

        session.close()

        Syren.start_syren(
            silent=alert.silent,
            delay=syren_config.delay,
            duration=syren_config.duration,
        )
        if self._alert_type == ALERT_SABOTAGE:
            States.set(State.MONITORING, MONITORING_SABOTAGE)
            self._broadcaster.send_message(MonitoringSabotageCommand())
        else:
            States.set(State.MONITORING, MONITORING_ALERT)
            self._broadcaster.send_message(MonitoringAlertCommand())

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

    def add_sensor_to_alert(
        self, session, alert: Alert, start_time, delay, syren_config: SyrenConfig
    ):
        """
        Adds a sensor to the given alert with the specified start time and delay.
        If the sensor is already added to the alert, it will not be added again.
        """
        sensor = session.query(Sensor).get(self._sensor_id)
        already_added = any(alert_sensor.sensor.id == sensor.id for alert_sensor in alert.sensors)

        # we can't add a sensor twice to the same alert, check database AlertSensor schema
        if already_added:
            logger.debug("Sensor by id: %s already added", self._sensor_id)
            return

        alert_sensor = AlertSensor(
            channel=sensor.channel,
            type_id=sensor.type_id,
            name=sensor.name,
            description=sensor.description,
            start_time=start_time,
            delay=delay,
            silent=resolve_silent(syren_config.silent, sensor.silent_alert),
            monitor_period=self._sensitivity.monitor_period,
            monitor_threshold=self._sensitivity.monitor_threshold,
        )
        alert_sensor.sensor = sensor
        alert.sensors.append(alert_sensor)
        alert.silent = all(item.silent for item in alert.sensors)
        session.commit()
        logger.debug("Added sensor by id: %s", self._sensor_id)

        send_alert_state(alert.serialized)
