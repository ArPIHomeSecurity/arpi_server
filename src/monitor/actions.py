from dataclasses import dataclass, fields

from utils.constants import (
    DELETE_SMS_MESSAGE,
    GET_SMS_MESSAGES,
    MAKE_TEST_CALL,
    MONITOR_ACTIVATE_OUTPUT,
    MONITOR_ARM_AWAY,
    MONITOR_ARM_DELAY_EXPIRED,
    MONITOR_ARM_STAY,
    MONITOR_DEACTIVATE_OUTPUT,
    MONITOR_DISARM,
    MONITOR_GET_STATE,
    MONITOR_REGISTER_CARD,
    MONITOR_SET_CLOCK,
    MONITOR_STOP,
    MONITOR_SYNC_CLOCK,
    MONITOR_UPDATE_CONFIG,
    MONITOR_UPDATE_KEYPAD,
    MONITORING_ALERT,
    MONITORING_ALERT_DELAY,
    MONITORING_SABOTAGE,
    POWER_GET_STATE,
    SEND_TEST_EMAIL,
    SEND_TEST_SMS,
    SEND_TEST_SYREN,
    UPDATE_SECURE_CONNECTION,
    UPDATE_SSH,
)


@dataclass(frozen=True)
class MonitorStopCommand:
    action: str = MONITOR_STOP


@dataclass(frozen=True)
class MonitorUpdateConfigCommand:
    action: str = MONITOR_UPDATE_CONFIG


@dataclass(frozen=True)
class MonitorUpdateKeypadCommand:
    action: str = MONITOR_UPDATE_KEYPAD


@dataclass(frozen=True)
class MonitorRegisterCardCommand:
    action: str = MONITOR_REGISTER_CARD


@dataclass(frozen=True)
class MonitorArmAwayCommand:
    action: str = MONITOR_ARM_AWAY
    user_id: int | None = None
    keypad_id: int | None = None
    use_delay: bool = True
    area_id: int | None = None


@dataclass(frozen=True)
class MonitorArmStayCommand:
    action: str = MONITOR_ARM_STAY
    user_id: int | None = None
    keypad_id: int | None = None
    use_delay: bool = True
    area_id: int | None = None


@dataclass(frozen=True)
class MonitorArmDelayExpiredCommand:
    """
    Sent by the exit delay timer thread, the armed states are published by the
    monitoring thread handling this command (it owns the database session).

    The generation identifies the arm that started the timer, so that the expiry of a
    replaced timer that fired before it could be cancelled is ignored.
    """

    action: str = MONITOR_ARM_DELAY_EXPIRED
    generation: int = 0


@dataclass(frozen=True)
class MonitorDisarmCommand:
    action: str = MONITOR_DISARM
    user_id: int | None = None
    keypad_id: int | None = None
    area_id: int | None = None


@dataclass(frozen=True)
class MonitorActivateOutputCommand:
    action: str = MONITOR_ACTIVATE_OUTPUT
    output_id: int = 0


@dataclass(frozen=True)
class MonitorDeactivateOutputCommand:
    action: str = MONITOR_DEACTIVATE_OUTPUT
    output_id: int = 0


@dataclass(frozen=True)
class MonitoringAlertCommand:
    action: str = MONITORING_ALERT


@dataclass(frozen=True)
class MonitoringAlertDelayCommand:
    action: str = MONITORING_ALERT_DELAY


@dataclass(frozen=True)
class MonitoringSabotageCommand:
    action: str = MONITORING_SABOTAGE


@dataclass(frozen=True)
class UpdateSecureConnectionCommand:
    action: str = UPDATE_SECURE_CONNECTION


@dataclass(frozen=True)
class MonitorGetStateCommand:
    action: str = MONITOR_GET_STATE


@dataclass(frozen=True)
class PowerGetStateCommand:
    action: str = POWER_GET_STATE


@dataclass(frozen=True)
class UpdateSSHCommand:
    action: str = UPDATE_SSH


@dataclass(frozen=True)
class SendTestEmailCommand:
    action: str = SEND_TEST_EMAIL


@dataclass(frozen=True)
class SendTestSMSCommand:
    action: str = SEND_TEST_SMS


@dataclass(frozen=True)
class GetSMSMessagesCommand:
    action: str = GET_SMS_MESSAGES


@dataclass(frozen=True)
class DeleteSMSMessageCommand:
    message_id: int = 0
    action: str = DELETE_SMS_MESSAGE


@dataclass(frozen=True)
class MakeTestCallCommand:
    action: str = MAKE_TEST_CALL


@dataclass(frozen=True)
class SendTestSyrenCommand:
    duration: int = 5
    action: str = SEND_TEST_SYREN


@dataclass(frozen=True)
class MonitorSyncClockCommand:
    action: str = MONITOR_SYNC_CLOCK


@dataclass(frozen=True)
class MonitorSetClockCommand:
    timezone: str | None = None
    datetime: str | None = None
    action: str = MONITOR_SET_CLOCK


MonitorCommand = (
    MonitorStopCommand
    | MonitorUpdateConfigCommand
    | MonitorUpdateKeypadCommand
    | MonitorRegisterCardCommand
    | MonitorArmAwayCommand
    | MonitorArmStayCommand
    | MonitorArmDelayExpiredCommand
    | MonitorDisarmCommand
    | MonitorActivateOutputCommand
    | MonitorDeactivateOutputCommand
    | MonitoringAlertCommand
    | MonitoringAlertDelayCommand
    | MonitoringSabotageCommand
    | UpdateSecureConnectionCommand
    | MonitorGetStateCommand
    | PowerGetStateCommand
    | UpdateSSHCommand
    | SendTestEmailCommand
    | SendTestSMSCommand
    | GetSMSMessagesCommand
    | DeleteSMSMessageCommand
    | MakeTestCallCommand
    | SendTestSyrenCommand
    | MonitorSyncClockCommand
    | MonitorSetClockCommand
)


class ParseCommandError(ValueError):
    pass


_ACTION_TO_CLASS = {
    MONITOR_STOP: MonitorStopCommand,
    MONITOR_UPDATE_CONFIG: MonitorUpdateConfigCommand,
    MONITOR_UPDATE_KEYPAD: MonitorUpdateKeypadCommand,
    MONITOR_REGISTER_CARD: MonitorRegisterCardCommand,
    MONITOR_ARM_AWAY: MonitorArmAwayCommand,
    MONITOR_ARM_STAY: MonitorArmStayCommand,
    MONITOR_ARM_DELAY_EXPIRED: MonitorArmDelayExpiredCommand,
    MONITOR_DISARM: MonitorDisarmCommand,
    MONITOR_ACTIVATE_OUTPUT: MonitorActivateOutputCommand,
    MONITOR_DEACTIVATE_OUTPUT: MonitorDeactivateOutputCommand,
    MONITORING_ALERT: MonitoringAlertCommand,
    MONITORING_ALERT_DELAY: MonitoringAlertDelayCommand,
    MONITORING_SABOTAGE: MonitoringSabotageCommand,
    UPDATE_SECURE_CONNECTION: UpdateSecureConnectionCommand,
    MONITOR_GET_STATE: MonitorGetStateCommand,
    POWER_GET_STATE: PowerGetStateCommand,
    UPDATE_SSH: UpdateSSHCommand,
    SEND_TEST_EMAIL: SendTestEmailCommand,
    SEND_TEST_SMS: SendTestSMSCommand,
    GET_SMS_MESSAGES: GetSMSMessagesCommand,
    DELETE_SMS_MESSAGE: DeleteSMSMessageCommand,
    MAKE_TEST_CALL: MakeTestCallCommand,
    SEND_TEST_SYREN: SendTestSyrenCommand,
    MONITOR_SYNC_CLOCK: MonitorSyncClockCommand,
    MONITOR_SET_CLOCK: MonitorSetClockCommand,
}


def from_dict(payload: dict) -> MonitorCommand:
    action = payload.get("action")
    if not isinstance(action, str):
        raise ParseCommandError("Missing or invalid 'action'")

    command_class = _ACTION_TO_CLASS.get(action)
    if command_class is None:
        raise ParseCommandError(f"Unsupported action: {action}")

    field_names = {field.name for field in fields(command_class)}

    # check for unexpected fields in the payload
    for payload_key in payload:
        if payload_key not in field_names:
            raise ParseCommandError(f"Unexpected field '{payload_key}' for action '{action}'")

    kwargs = {key: value for key, value in payload.items() if key in field_names}

    try:
        return command_class(**kwargs)
    except TypeError as error:
        raise ParseCommandError(str(error)) from error
