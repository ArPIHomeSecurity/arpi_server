from logging import ERROR, INFO, DEBUG

# custom logging level for logging sensitive information
TRACE = 5

# Threads and logging
THREAD_SERVICE = "Service"
THREAD_MONITOR = "Monitor"
THREAD_IPC = "IPC"
THREAD_NOTIFIER = "Notifier"
THREAD_SOCKETIO = "SocketIO"
THREAD_ALERT = "Alert"
THREAD_KEYPAD = "Keypad"
THREAD_SECCON = "SecCon"
THREAD_OUTPUT = "Output"

LOG_SERVICE = THREAD_SERVICE
LOG_MONITOR = THREAD_MONITOR
LOG_IPC = THREAD_IPC
LOG_ALERT = THREAD_ALERT
LOG_SOCKETIO = THREAD_SOCKETIO
LOG_MQTT = "MQTT"
LOG_SENSORS = "Sensors"
LOG_NOTIFIER = THREAD_NOTIFIER
LOG_ADSENSOR = "AD.Sensor"
LOG_ADPOWER = "AD.Power"
LOG_ADOUTPUT = "AD.Output"
LOG_ADGSM = "AD.GSM"
LOG_ADKEYPAD = "AD.Keypad"
LOG_SECCON = THREAD_SECCON
LOG_SC_CERTBOT = "CertBot"
LOG_SC_DYNDNS = "DynDns"
LOG_SC_ACCESS = "SSH"
LOG_CLOCK = "Clock"
LOG_OUTPUT = THREAD_OUTPUT

LOGGING_MODULES = [
    (LOG_SERVICE, INFO),
    (LOG_MONITOR, INFO),
    (LOG_IPC, INFO),
    (LOG_ALERT, INFO),
    (LOG_SOCKETIO, INFO),
    (LOG_MQTT, INFO),
    (LOG_SENSORS, INFO),
    (LOG_NOTIFIER, INFO),
    (LOG_ADSENSOR, INFO),
    (LOG_ADOUTPUT, INFO),
    (LOG_ADGSM, INFO),
    (LOG_ADKEYPAD, DEBUG),
    (LOG_SECCON, INFO),
    (LOG_SC_CERTBOT, INFO),
    (LOG_SC_DYNDNS, INFO),
    (LOG_SC_ACCESS, INFO),
    (LOG_CLOCK, INFO),
    (LOG_OUTPUT, INFO),
    ("gsmmodem.modem.GsmModem", ERROR),
    ("gsmmodem.serial_comms.SerialComms", ERROR),
    ("SocketIOServer", INFO),
    ("sqlalchemy.engine", ERROR),
]

# INTERNAL CONSTANTS
# monitoring system commands
MONITOR_ARM_AWAY = "monitor_arm_away"
MONITOR_ARM_STAY = "monitor_arm_stay"
MONITOR_DISARM = "monitor_disarm"
MONITOR_GET_STATE = "monitor_get_state"
MONITOR_UPDATE_CONFIG = "monitor_update_config"
MONITOR_UPDATE_KEYPAD = "monitor_update_keypad"
MONITOR_REGISTER_CARD = "monitor_register_card"
MONITOR_STOP = "monitor_stop"
MONITOR_SYNC_CLOCK = "monitor_sync_clock"
MONITOR_SET_CLOCK = "monitor_set_clock"
MONITOR_ACTIVATE_OUTPUT = "activate_output"
MONITOR_DEACTIVATE_OUTPUT = "deactivate_output"

UPDATE_SECURE_CONNECTION = "monitor_update_secure_connection"
POWER_GET_STATE = "power_get_state"
UPDATE_SSH = "update_ssh"
SEND_TEST_EMAIL = "send_test_email"
SEND_TEST_SMS = "send_test_sms"
SEND_TEST_SYREN = "send_test_syren"
MAKE_TEST_CALL = "make_test_call"
GET_SMS_MESSAGES = "get_sms_messages"
DELETE_SMS_MESSAGE = "delete_sms_message"

"""---------------------------------------------------------------"""
# CONSTANTS USED ALSO BY THE WEB APPLICATION

# authentication token valid for 15 mins
USER_TOKEN_EXPIRY = 60 * 15

# arm types
ARM_MIXED = "arm_mixed"
ARM_AWAY = "arm_away"
ARM_STAY = "arm_stay"
ARM_DISARM = "disarm"

# alert types
ALERT_AWAY = "alert_away"
ALERT_STAY = "alert_stay"
ALERT_AWAY_DELAYED = "alert_away_delayed"
ALERT_STAY_DELAYED = "alert_stay_delayed"
ALERT_SABOTAGE = "alert_sabotage"

# monitoring system states
# Initial state of the system
MONITORING_STARTUP = "monitoring_startup"
# State when the system is updating its configuration
MONITORING_UPDATING_CONFIG = "monitoring_updating_config"
# State when the system configuration is invalid
MONITORING_INVALID_CONFIG = "monitoring_invalid_config"
# State when the system is ready to be armed
MONITORING_READY = "monitoring_ready"
# State when the system is armed and in the exit delay period
MONITORING_ARM_DELAY = "monitoring_arm_delay"
# State when the system is armed
MONITORING_ARMED = "monitoring_armed"
# State when the system is in the entry delay period before an alert is triggered
MONITORING_ALERT_DELAY = "monitoring_alert_delay"
# State when the system is in an alert condition
MONITORING_ALERT = "monitoring_alert"
# State when the system is in a sabotage condition (disarmed with tamper open)
MONITORING_SABOTAGE = "monitoring_sabotage"
# State when the system has encountered an error
MONITORING_ERROR = "monitoring_error"
# State when the system is stopped
MONITORING_STOPPED = "monitoring_stopped"

POWER_SOURCE_NETWORK = "network"
POWER_SOURCE_BATTERY = "battery"

ROLE_ADMIN = "admin"
ROLE_USER = "user"
