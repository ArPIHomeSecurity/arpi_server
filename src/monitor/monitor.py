"""
Monitoring the sensors and manage alerting.
"""

import contextlib
from datetime import datetime as dt
import logging

from os import environ
from queue import Empty, Queue
from threading import Thread, Timer
from time import sleep

from constants import (
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
    MONITORING_READY,
    MONITORING_SABOTAGE,
    MONITORING_STARTUP,
    MONITORING_STOPPED,
    POWER_SOURCE_BATTERY,
    POWER_SOURCE_NETWORK,
    THREAD_MONITOR,
)
from models import Alert, Arm, Disarm, Sensor, ArmSensor, ArmStates
from monitor.alert import SensorAlert
from monitor.area_handler import AreaHandler
from monitor.config_helper import (
    load_alert_sensitivity_config,
    load_dyndns_config,
    load_ssh_config,
    load_syren_config,
)
from monitor.sensor.handler import SensorHandler
from monitor.storage import States, State
from monitor.adapters.power import PowerAdapter
from monitor.broadcast import Broadcaster
from monitor.notifications.notifier import Notifier
from monitor.syren import Syren
from monitor.database import get_database_session
from monitor.output.handler import OutputHandler
from monitor.socket_io import send_alert_state, send_power_state, send_syren_state
from tools.queries import get_arm_delay


# 2000.01.01 00:00:00
DEFAULT_DATETIME = 946684800


class Monitor(Thread):
    """
    Class for implement monitoring of the sensors and manage alerting.
    """

    def __init__(self, broadcaster: Broadcaster):
        """
        Constructor
        """
        super(Monitor, self).__init__(name=THREAD_MONITOR)
        self._logger = logging.getLogger(LOG_MONITOR)
        self._broadcaster = broadcaster
        self._actions = Queue()
        self._power_adapter = PowerAdapter()
        self._power_source = None
        self._db_session = None
        self._delay_timer = None
        self._sensor_handler = None
        self._area_handler = None
        self._broadcaster.register_queue(id(self), self._actions)
        self._logger.info("Monitoring created")

    def run(self):
        self._logger.info("Monitoring started")

        # create the database session in the thread
        self._db_session = get_database_session()

        # cleanup the database
        self.cleanup_database()

        # setup the states
        States.open()
        if States.get(State.MONITORING) is None:
            States.set(State.MONITORING, MONITORING_STARTUP)
        elif States.get(State.MONITORING) != MONITORING_STOPPED:
            self._logger.error(
                "Monitor restarted without proper shutdown: %s", States.get(State.MONITORING)
            )
        else:
            States.set(State.MONITORING, MONITORING_STARTUP)

        if States.get(State.ARM) is None:
            States.set(State.ARM, ARM_DISARM)
        elif States.get(State.ARM) != ARM_DISARM:
            self._logger.error(
                "Monitor restarted without proper shutdown: %s", States.get(State.ARM)
            )
        else:
            States.set(State.ARM, ARM_DISARM)

        # keep in startup state
        sleep(3)

        # send initial states
        alert = self._db_session.query(Alert).filter_by(end_time=None).first()
        if alert:
            send_alert_state(alert)
            Syren.start_syren()
        else:
            send_alert_state(None)
            send_syren_state(None)

        self._area_handler = AreaHandler(session=self._db_session)
        self._area_handler.publish_areas()

        self._sensor_handler = SensorHandler(
            session=self._db_session, broadcaster=self._broadcaster
        )
        self._sensor_handler.load_sensors()

        message_wait_time = 1 / int(environ["SAMPLE_RATE"])
        while True:
            with contextlib.suppress(Empty):
                message = self._actions.get(True, message_wait_time)
                self._logger.debug("Action: %s", message)
                if message["action"] == MONITOR_STOP:
                    # stop the alert without disarm
                    self.stop_alert(None)
                    break
                elif message["action"] == MONITOR_ARM_AWAY:
                    self.arm_monitoring(
                        ARM_AWAY,
                        message.get("user_id", None),
                        message.get("keypad_id", None),
                        message.get("delay", True),
                        message.get("area_id", None),
                    )
                elif message["action"] == MONITOR_ARM_STAY:
                    self.arm_monitoring(
                        ARM_STAY,
                        message.get("user_id", None),
                        message.get("keypad_id", None),
                        message.get("use_delay", True),
                        message.get("area_id", None),
                    )
                elif message["action"] in (MONITORING_ALERT, MONITORING_ALERT_DELAY):
                    if self._delay_timer:
                        self._delay_timer.cancel()
                        self._delay_timer = None
                elif message["action"] == MONITOR_DISARM:
                    self.disarm_monitoring(
                        message.get("user_id", None),
                        message.get("keypad_id", None),
                        message.get("area_id", None),
                    )
                    continue
                elif message["action"] == MONITOR_UPDATE_CONFIG:
                    self._area_handler.publish_areas()
                    self._sensor_handler.load_sensors()

            self.check_power()
            self._sensor_handler.scan_sensors()
            self._sensor_handler.handle_alerts()

        self._sensor_handler.close()
        self._power_adapter.cleanup()
        self._db_session.close()
        States.set(State.MONITORING, MONITORING_STOPPED)
        States.set(State.ARM, ARM_DISARM)
        States.close()
        self._logger.info("Monitoring stopped")

    def arm_monitoring(self, arm_type, user_id, keypad_id, use_delay, area_id):
        """
        Arm the monitoring system to the given state (away, stay).
        """
        self._logger.info("Arming to %s", arm_type)

        if area_id is None:
            # arm the system and all the areas
            self._area_handler.change_areas_arm(arm_type)
            self.arm_system(arm_type, use_delay)
        else:
            self._area_handler.change_area_arm(arm_type, area_id)
            if States.get(State.ARM) == ARM_DISARM:
                self.arm_system(
                    self._area_handler.get_areas_state(),
                    use_delay=False
                )
            else:
                areas_state = self._area_handler.get_areas_state()
                # send always notification
                States.set(State.ARM, areas_state)

        self.update_arm(arm_type=arm_type, user_id=user_id, keypad_id=keypad_id)

    def arm_system(self, arm_type, use_delay):
        """
        Arm only the system.
        """
        self._logger.info("Arming system to %s", arm_type)

        # get max delay of arm
        arm_delay = get_arm_delay(self._db_session, arm_type) if use_delay else None

        def stop_arm_delay():
            self._logger.debug("End arm delay => armed!!!")
            States.set(State.MONITORING, MONITORING_ARMED)

        States.set(State.ARM, arm_type)
        self._logger.debug("Arm with delay: %s / %s", arm_delay, arm_type)
        if arm_delay is not None:
            States.set(State.MONITORING, MONITORING_ARM_DELAY)
            self._delay_timer = Timer(arm_delay, stop_arm_delay)
            self._delay_timer.start()
        else:
            States.set(State.MONITORING, MONITORING_ARMED)

            # update output channel
            OutputHandler.send_system_armed()

    def disarm_monitoring(self, user_id, keypad_id, area_id):
        """
        Disarm the monitoring system.
        """
        self._logger.info("Disarming user=%s, keypad=%s", user_id, keypad_id)

        # do not disarm if the system is already disarmed
        if (
            States.get(State.ARM) == ARM_DISARM and
            States.get(State.MONITORING) != MONITORING_SABOTAGE
        ):
            self._logger.info("System is already disarmed")
            return

        if area_id is not None:
            # arm the system and the area
            self._area_handler.change_area_arm(ARM_DISARM, area_id)
            if self._area_handler.get_areas_state() == ARM_DISARM:
                self.disarm_system(user_id, keypad_id)
            else:
                areas_state = self._area_handler.get_areas_state()
                if areas_state != States.get(State.ARM):
                    States.set(State.ARM, areas_state)

                self.update_arm(arm_type=ARM_DISARM, user_id=user_id, keypad_id=keypad_id)
        else:
            # disarm system and all the areas
            self._area_handler.change_areas_arm(ARM_DISARM)
            self.disarm_system(user_id, keypad_id)

    def disarm_system(self, user_id, keypad_id):
        """
        Disarm only the system.
        """
        self._logger.info("Disarming system")
        if self._delay_timer:
            self._delay_timer.cancel()
            self._delay_timer = None

        arm = self._db_session.query(Arm).filter_by(disarm=None).first()
        disarm = Disarm(
            arm_id=arm.id if arm else None, time=dt.now(), user_id=user_id, keypad_id=keypad_id
        )
        self._db_session.add(disarm)
        self._db_session.commit()

        current_state = States.get(State.MONITORING)
        current_arm = States.get(State.ARM)
        if (
            current_state
            in (MONITORING_ARM_DELAY, MONITORING_ARMED, MONITORING_ALERT_DELAY, MONITORING_ALERT)
            and current_arm in (ARM_AWAY, ARM_STAY, ARM_MIXED)
            or current_state == MONITORING_SABOTAGE
        ):
            States.set(State.ARM, ARM_DISARM)
            States.set(State.MONITORING, MONITORING_READY)

            # update output channel
            OutputHandler.send_system_disarmed()

        self.stop_alert(disarm.id)

    def update_arm(self, arm_type, user_id, keypad_id):
        """
        Update the arm in the database.
        """
        # arm the system
        now = dt.now()
        arm = self._db_session.query(Arm).filter_by(disarm=None).first()
        if arm is None:
            arm = Arm(arm_type=arm_type, time=now, user_id=user_id, keypad_id=keypad_id)
            self._db_session.add(arm)
        else:
            self._logger.info("Arm state to database: %s", arm.type)
            arm.type = ArmStates.merge(arm.type, arm_type)

        for sensor in self._db_session.query(Sensor).filter_by(deleted=False).all():
            delay = SensorHandler.get_sensor_delay(sensor, States.get(State.MONITORING))
            self._logger.debug("Sensor (id=%s) delay: %s", sensor.id, delay)
            sensor_state = ArmSensor.from_sensor(arm=arm, sensor=sensor, timestamp=now, delay=delay)
            self._db_session.add(sensor_state)

        self._db_session.commit()

    def check_power(self):
        """
        Check the power source and send the state if it changed
        """
        # load the value once from the adapter
        new_power_source = self._power_adapter.source_type
        if new_power_source == PowerAdapter.SOURCE_BATTERY:
            States.set(State.POWER, POWER_SOURCE_BATTERY)
            self._logger.debug("System works from battery")
        elif new_power_source == PowerAdapter.SOURCE_NETWORK:
            States.set(State.POWER, POWER_SOURCE_NETWORK)
            self._logger.trace("System works from network")

        if (
            new_power_source == PowerAdapter.SOURCE_BATTERY
            and self._power_source == PowerAdapter.SOURCE_NETWORK
        ):
            send_power_state(POWER_SOURCE_BATTERY)
            Notifier.notify_power_outage_started(dt.now())
            self._logger.info("Power outage started!")
        elif (
            new_power_source == PowerAdapter.SOURCE_NETWORK
            and self._power_source == PowerAdapter.SOURCE_BATTERY
        ):
            send_power_state(POWER_SOURCE_NETWORK)
            Notifier.notify_power_outage_stopped(dt.now())
            self._logger.info("Power outage ended!")

        self._power_source = new_power_source

    def cleanup_database(self):
        """
        Cleanup invalid values in the database.
        """
        # overwrite invalid values in the database with default values
        load_ssh_config(cleanup=True, session=self._db_session)
        load_syren_config(cleanup=True, session=self._db_session)
        load_alert_sensitivity_config(cleanup=True, session=self._db_session)
        load_dyndns_config(cleanup=True, session=self._db_session)
        self._db_session.commit()

    def stop_alert(self, disarm_id: int):
        """
        Stop the alerting.
        """
        self._sensor_handler.on_alert_stopped()
        SensorAlert.stop_alerts(disarm_id)
        Syren.stop_syren()
