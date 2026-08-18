"""
Monitoring the sensors and manage alerting.
"""

import contextlib
import logging
from datetime import datetime as dt
from os import environ
from queue import Empty, Queue
from threading import Thread, Timer
from time import sleep

from sqlalchemy import select

from monitor.action_handler import ActionHandler, MonitorActionResult, handle_action
from monitor.actions import (
    MonitorArmAwayCommand,
    MonitorArmDelayExpiredCommand,
    MonitorArmStayCommand,
    MonitorDisarmCommand,
    MonitoringAlertCommand,
    MonitoringAlertDelayCommand,
    MonitorStopCommand,
    MonitorUpdateConfigCommand,
    UpdateSecureConnectionCommand,
)
from monitor.adapters.power import get_power_adapter
from monitor.adapters.power_base import SOURCE_BATTERY, SOURCE_NETWORK
from monitor.alert import SensorAlert
from monitor.area_handler import AreaHandler
from monitor.broadcast import Broadcaster
from monitor.config.models import AlertSensitivityConfig, DyndnsConfig, SSHConfig, SyrenConfig
from monitor.connection import SecureConnection
from monitor.database import get_database_session
from monitor.notifications.notifier import Notifier
from monitor.output.handler import OutputHandler
from monitor.sensor.handler import SensorHandler
from monitor.socket_io import send_alert_state, send_arm_state, send_power_state, send_syren_state
from monitor.storage import State, States
from monitor.syren import Syren
from tools.certbot import Certbot
from utils.constants import (
    ARM_AWAY,
    ARM_DISARM,
    ARM_STAY,
    LOG_MONITOR,
    MONITORING_ALERT,
    MONITORING_ALERT_DELAY,
    MONITORING_ARM_DELAY,
    MONITORING_ARMED,
    MONITORING_ERROR,
    MONITORING_INVALID_CONFIG,
    MONITORING_READY,
    MONITORING_SABOTAGE,
    MONITORING_STARTUP,
    MONITORING_STOPPED,
    MONITORING_UPDATING_CONFIG,
    POWER_SOURCE_BATTERY,
    POWER_SOURCE_NETWORK,
    THREAD_MONITOR,
)
from utils.models import Alert, Arm, ArmSensor, ArmStates, Disarm, Sensor, User
from utils.queries import get_arm_delay, get_arm_state

# 2000.01.01 00:00:00
DEFAULT_DATETIME = 946684800
logger = logging.getLogger(LOG_MONITOR)


class Monitor(Thread, ActionHandler):
    """
    Class for implement monitoring of the sensors and manage alerting.
    """

    def __init__(self, broadcaster: Broadcaster):
        """
        Constructor
        """
        Thread.__init__(self, name=THREAD_MONITOR)
        ActionHandler.__init__(self)
        self._actions = Queue()
        self._power_adapter = get_power_adapter()
        self._power_source = None
        self._db_session = None
        self._delay_timer = None
        self._delay_generation = 0
        self._sensor_handler = None
        self._area_handler = None
        self._secure_connection = None
        self._broadcaster = broadcaster
        self._broadcaster.register_queue(id(self), self._actions)
        self.register_action_handlers()
        logger.info("Monitoring created")

    def run(self):
        logger.info("Monitoring started")

        try:
            self.startup_monitoring()

            self.do_monitoring()

            self.teardown_monitoring()
        except Exception:  # pylint: disable=broad-except
            logger.exception("Monitoring thread crashed!")
            States.set(State.MONITORING, MONITORING_ERROR)
            return
        finally:
            if self._sensor_handler:
                self._sensor_handler.close()
            if self._area_handler:
                self._area_handler.close()
            if self._db_session:
                self._db_session.close()
            States.close()

        logger.info("Monitoring stopped")

    def startup_monitoring(self):
        """
        Startup the monitoring system.

        * Load the database session
        * Cleanup the database
        * Setup the states
        * Send initial states
        * Load the areas
        * Load the sensors
        """
        # create the database session in the thread
        self._db_session = get_database_session()

        Certbot().verify_configuration()

        # setup the states
        States.open()
        state = States.get(State.MONITORING)
        if state is None:
            States.set(State.MONITORING, MONITORING_STARTUP)
        elif state in (MONITORING_ERROR, MONITORING_INVALID_CONFIG):
            logger.warning("Monitor restarted after error: %s", state)
            States.set(State.MONITORING, MONITORING_STARTUP)
        elif state == MONITORING_STOPPED:
            # normal restart
            States.set(State.MONITORING, MONITORING_STARTUP)
        elif state == MONITORING_UPDATING_CONFIG:
            logger.warning(
                "Monitor restarted during configuration update, restoring state: %s",
                MONITORING_STARTUP,
            )
            States.set(State.MONITORING, MONITORING_STARTUP)
        elif state in (MONITORING_ARM_DELAY, MONITORING_ARMED):
            arm = self._db_session.scalar(select(Arm).where(Arm.disarm == None))
            arm_state = get_arm_state(self._db_session)

            if arm_state == ARM_DISARM:
                logger.warning(
                    "Monitor restarted during '%s', but no areas are armed, restoring state: %s",
                    state,
                    MONITORING_READY,
                )
                States.set(State.MONITORING, MONITORING_READY)
            elif arm_state in (ARM_AWAY, ARM_STAY) and arm is None:
                logger.warning(
                    "Monitor restarted during '%s', but no arm found in database, restoring : %s",
                    state,
                    MONITORING_READY,
                )
                States.set(State.MONITORING, MONITORING_READY)
        else:
            logger.error("Monitor restarted without proper shutdown, restoring state: %s", state)

        # cleanup the database
        self.cleanup_database()

        send_arm_state(get_arm_state(self._db_session))

        # keep in startup state
        sleep(3)

        # send initial states
        alert = self._db_session.query(Alert).filter_by(end_time=None).first()
        if alert:
            logger.info("Continue unresolved alert: %s", alert)
            send_alert_state(alert)
            syren_config = SyrenConfig.load_config(cleanup=True, session=self._db_session)
            if syren_config is None:
                syren_config = SyrenConfig(
                    silent=Syren.SILENT,
                    delay=Syren.DELAY,
                    duration=Syren.DURATION,
                )
            Syren.start_syren(
                silent=alert.silent,
                delay=syren_config.delay,
                duration=syren_config.duration,
            )
        else:
            send_alert_state(None)
            send_syren_state(None)

        self._area_handler = AreaHandler(session=self._db_session, broadcaster=self._broadcaster)
        self._area_handler.load_areas()
        self._area_handler.publish_areas()

        self._sensor_handler = SensorHandler(broadcaster=self._broadcaster)
        self._sensor_handler.initialize()
        self._sensor_handler.load_sensors()
        self._sensor_handler.publish_sensors()

    def teardown_monitoring(self):
        """
        Teardown the monitoring system.
        """
        logger.info("Closing monitoring system")
        States.set(State.MONITORING, MONITORING_STOPPED)

    @handle_action(MonitorUpdateConfigCommand())
    def _handle_action_update_config(self):
        """
        Handle the update config action.
        """
        logger.info("Update config command received, updating config...")
        self._area_handler.load_areas()
        self._area_handler.publish_areas()
        self._sensor_handler.update_mqtt_config()
        self._sensor_handler.load_sensors()
        self._sensor_handler.publish_sensors()

    @handle_action(UpdateSecureConnectionCommand())
    def _handle_action_update_secure_connection(self):
        """
        Handle the update secure connection action.
        """
        logger.info("Update secure connection...")
        if self._secure_connection is None:
            States.set(State.MONITORING, MONITORING_UPDATING_CONFIG)
            self._secure_connection = SecureConnection()
            self._secure_connection.start()

    @handle_action(MonitorStopCommand())
    def _handle_action_stop(self):
        """
        Handle the stop action.
        """
        logger.info("Stop command received, stopping monitoring...")
        if get_arm_state(self._db_session) != ARM_DISARM:
            self.disarm_monitoring(None, None, None)

        return MonitorActionResult.result_break

    @handle_action(MonitorArmAwayCommand())
    def _handle_action_arm_away(self, user_id, keypad_id, use_delay, area_id):
        """
        Handle the arm away action.
        """
        self.arm_monitoring(ARM_AWAY, user_id, keypad_id, use_delay, area_id)

    @handle_action(MonitorArmStayCommand())
    def _handle_action_arm_stay(self, user_id, keypad_id, use_delay, area_id):
        """
        Handle the arm stay action.
        """
        self.arm_monitoring(ARM_STAY, user_id, keypad_id, use_delay, area_id)

    @handle_action(MonitorArmDelayExpiredCommand())
    def _handle_action_arm_delay_expired(self, generation):
        """
        The exit delay expired, publish the armed states.

        Sent by the timer thread to get back onto the monitoring thread, which owns
        the database session, see arm_system().
        """
        if generation != self._delay_generation:
            # an expired timer of an arm that was replaced in the meantime
            return

        # the timer can lose the race against a disarm cancelling it, the already
        # published disarmed state must not be overwritten in that case
        if States.get(State.MONITORING) != MONITORING_ARM_DELAY:
            return

        States.set(State.MONITORING, MONITORING_ARMED)
        self._area_handler.publish_arm_states()

        # update output channel
        OutputHandler.send_system_armed()

    @handle_action(MonitorDisarmCommand())
    def _handle_action_disarm(self, user_id, keypad_id, area_id):
        """
        Handle the disarm action.
        """
        self.disarm_monitoring(user_id, keypad_id, area_id)
        return MonitorActionResult.result_continue

    @handle_action(MonitoringAlertCommand(), MonitoringAlertDelayCommand())
    def _handle_action_delays(self):
        """
        Handle the alert and alert delay actions.
        """
        if self._delay_timer:
            self._delay_timer.cancel()
            self._delay_timer = None

    def do_monitoring(self):
        """
        Start the monitoring of the sensors and manage alerting.
        """
        message_wait_time = 1 / int(environ["SAMPLE_RATE"])
        self._secure_connection = None
        while True:
            with contextlib.suppress(Empty):
                message = self._actions.get(True, message_wait_time)
                logger.debug("Action: %s", message)

                result = self.handle_action(message)
                if result == MonitorActionResult.result_break:
                    break
                elif result == MonitorActionResult.result_continue:
                    continue

            if self._secure_connection is not None and not self._secure_connection.is_alive():
                self._secure_connection = None
                if States.get(State.MONITORING) == MONITORING_UPDATING_CONFIG:
                    States.set(State.MONITORING, MONITORING_READY)
                    logger.info("Secure connection finished")

            if self._secure_connection is None:
                self.check_power()
                self._sensor_handler.scan_sensors()
                self._sensor_handler.handle_alerts()

    def arm_monitoring(self, arm_type, user_id, keypad_id, use_delay, area_id):
        """
        Arm the monitoring system to the given state (away, stay).
        """
        logger.info("Arming to %s %s", arm_type, "with delay" if use_delay else "without delay")

        arm_changed = False
        if area_id is None:
            # arm the system and all the areas
            arm_changed = self._area_handler.change_areas_arm(arm_type)
            self.arm_system(arm_type, use_delay)
        else:
            arm_state_before = get_arm_state(self._db_session)
            arm_changed = self._area_handler.change_area_arm(arm_type, area_id)
            arm_state_after = get_arm_state(self._db_session)

            if arm_state_before != arm_state_after:
                # arming an area that arms the whole system gets the exit delay too,
                # otherwise leaving the building would trip the sensors right away
                self.arm_system(arm_type, use_delay)
            elif States.get(State.MONITORING) == MONITORING_ARM_DELAY:
                # the new area joins the running exit delay
                self._area_handler.publish_arming()
            else:
                # the system was already armed, publish the new area state immediately
                self._area_handler.publish_arm_states()

        if arm_changed:
            self.update_database_arm(arm_type=arm_type, user_id=user_id, keypad_id=keypad_id)

    def arm_system(self, arm_type, use_delay):
        """
        Arm only the system (internal states, no database update).
        """
        logger.info("Arming system to %s", arm_type)

        # a new arm replaces a running exit delay, two live timers would end the
        # delay too early
        if self._delay_timer:
            self._delay_timer.cancel()
            self._delay_timer = None
        self._delay_generation += 1
        generation = self._delay_generation

        # get max delay of arm
        arm_delay = get_arm_delay(self._db_session, arm_type) if use_delay else None

        def stop_arm_delay():
            logger.debug("End arm delay => armed!!!")
            # timer thread: no database access here, the command handler publishes
            # the armed states on the monitoring thread
            self._broadcaster.send_message(MonitorArmDelayExpiredCommand(generation=generation))

        logger.debug("Arm with delay: %s / %s", arm_delay, arm_type)
        # a delay of 0 means no exit delay, the system has to be armed immediately
        if arm_delay:
            States.set(State.MONITORING, MONITORING_ARM_DELAY)
            # home assistant shows the exit delay as arming, the armed state of the
            # panels is only published when the delay expires
            self._area_handler.publish_arming()
            self._delay_timer = Timer(arm_delay, stop_arm_delay)
            self._delay_timer.start()
        else:
            States.set(State.MONITORING, MONITORING_ARMED)
            self._area_handler.publish_arm_states()

            # update output channel
            OutputHandler.send_system_armed()

        send_arm_state(get_arm_state(self._db_session))

    def disarm_monitoring(self, user_id, keypad_id, area_id):
        """
        Disarm the monitoring system.
        """
        logger.info("Disarming user=%s, keypad=%s", user_id, keypad_id)

        # do not disarm if the system is already disarmed
        # except if the system is in sabotage mode
        if (
            get_arm_state(self._db_session) == ARM_DISARM
            and States.get(State.MONITORING) != MONITORING_SABOTAGE
        ):
            logger.info("System is already disarmed")
            return

        if area_id is not None:
            # disarm only the area, and the system if no armed area is left
            self._area_handler.change_area_arm(ARM_DISARM, area_id)
            areas_state = get_arm_state(self._db_session)
            if areas_state == ARM_DISARM:
                self.disarm_system(user_id, keypad_id)

            if States.get(State.MONITORING) == MONITORING_ARM_DELAY:
                # the remaining areas are still in the exit delay, keep them arming
                self._area_handler.publish_arming()
            else:
                self._area_handler.publish_arm_states()
            send_arm_state(areas_state)
        else:
            # disarm system and all the areas
            self._area_handler.change_areas_arm(ARM_DISARM)
            self.disarm_system(user_id, keypad_id)
            self._area_handler.publish_arm_states()

    def disarm_system(self, user_id, keypad_id):
        """
        Disarm only the system.
        """
        logger.info("Disarming system")
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
        stop_alert = True
        if current_state == MONITORING_SABOTAGE:
            # do not stop alerting if the system is in sabotage mode
            stop_alert = False
        if (
            current_state
            in (MONITORING_ARM_DELAY, MONITORING_ARMED, MONITORING_ALERT_DELAY, MONITORING_ALERT)
            or current_state == MONITORING_SABOTAGE
        ):
            States.set(State.MONITORING, MONITORING_READY)

            # update output channel
            OutputHandler.send_system_disarmed()

        send_arm_state(ARM_DISARM)
        SensorAlert.stop_alerts(disarm.id)
        Syren.stop_syren()
        if stop_alert:
            self._sensor_handler.on_alert_stopped()

    def update_database_arm(self, arm_type, user_id, keypad_id):
        """
        Update the arm in the database.
        """
        # arm the system
        now = dt.now()
        arm = self._db_session.query(Arm).filter_by(disarm=None).first()
        if arm is None:
            user = self._db_session.get(User, user_id) if user_id else None
            arm = Arm(arm_type=arm_type, time=now, user=user, keypad_id=keypad_id)
            self._db_session.add(arm)
        else:
            logger.info("Arm state to database: %s", arm.type)
            arm.type = ArmStates.merge(arm.type, arm_type)

        for sensor in self._db_session.query(Sensor).filter_by(deleted=False).all():
            delay = SensorHandler.get_sensor_delay(sensor, States.get(State.MONITORING))
            logger.debug("Sensor (id=%s) delay: %s", sensor.id, delay)
            sensor_state = ArmSensor.from_sensor(arm=arm, sensor=sensor, timestamp=now, delay=delay)
            self._db_session.add(sensor_state)

        self._db_session.commit()

    def check_power(self):
        """
        Check the power source and send the state if it changed
        """
        # load the value once from the adapter
        new_power_source = self._power_adapter.source_type
        if new_power_source == SOURCE_BATTERY:
            States.set(State.POWER, POWER_SOURCE_BATTERY)
            logger.debug("System works from battery")
        elif new_power_source == SOURCE_NETWORK:
            States.set(State.POWER, POWER_SOURCE_NETWORK)
            logger.trace("System works from network")

        if new_power_source == SOURCE_BATTERY and self._power_source == SOURCE_NETWORK:
            send_power_state(POWER_SOURCE_BATTERY)
            Notifier.notify_power_outage_started(dt.now())
            logger.info("Power outage started!")
        elif new_power_source == SOURCE_NETWORK and self._power_source == SOURCE_BATTERY:
            send_power_state(POWER_SOURCE_NETWORK)
            Notifier.notify_power_outage_stopped(dt.now())
            logger.info("Power outage ended!")

        self._power_source = new_power_source

    def cleanup_database(self):
        """
        Cleanup invalid values in the database.
        """
        # close the alert if the system is not alerting
        alert_states = [MONITORING_ALERT, MONITORING_ALERT_DELAY]
        alert = self._db_session.query(Alert).filter_by(end_time=None).first()
        if alert and States.get(State.MONITORING) not in alert_states:
            alert.end_time = dt.now()
            logger.info("Close invalid alert: %s", alert)
            send_alert_state(None)

        # overwrite invalid values in the database with default values
        SSHConfig.load_config(cleanup=True, session=self._db_session)
        SyrenConfig.load_config(cleanup=True, session=self._db_session)
        AlertSensitivityConfig.load_config(cleanup=True, session=self._db_session)
        DyndnsConfig.load_config(cleanup=True, session=self._db_session)
        self._db_session.commit()
