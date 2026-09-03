"""
Handles SMS messages received from GSM modem.
"""

import contextlib
import logging
from queue import Empty, Queue
from threading import Thread

from gsmmodem.modem import ReceivedSms

from monitor.actions import (
    MonitorArmAwayCommand,
    MonitorArmStayCommand,
    MonitorDisarmCommand,
    MonitorStopCommand,
    MonitorUpdateConfigCommand,
)
from monitor.adapters.gsm_provider import GSMProvider
from monitor.broadcast import Broadcaster
from monitor.config.models import GSMConfig, SMSActionConfig, SMSCommandConfig
from monitor.database import get_database_session
from utils.constants import LOG_SMS, THREAD_SMS
from utils.models import User
from utils.queries import get_user_with_access_code

logger = logging.getLogger(LOG_SMS)

POLL_TIMEOUT = 1  # sec, queue poll timeout to stay responsive to stop commands


class SmsHandler(Thread):
    """
    Class for handling SMS messages received from GSM modem.
    """

    def __init__(self, broadcaster: Broadcaster):
        super().__init__(name=THREAD_SMS)
        self._actions = Queue()
        self._inbox = Queue()
        self._broadcaster = broadcaster
        self._broadcaster.register_queue(id(self), self._actions)

        # Register callback with GSMProvider for incoming SMS
        with GSMProvider.session() as gsm:
            gsm.set_sms_received_callback(self._on_sms_received)

    def run(self):
        try:
            self.communicate()
        except Exception:  # pylint: disable=broad-except
            logger.exception("SMS handler crashed!")

        logger.info("SMS handler stopped")

    def communicate(self):
        """Main event loop for SMS handler."""
        while True:
            # Check for control messages (stop, config update)
            with contextlib.suppress(Empty):
                message = self._actions.get(timeout=POLL_TIMEOUT)
                match message:
                    case MonitorStopCommand():
                        break
                    case MonitorUpdateConfigCommand():
                        GSMProvider.load_config()

            # Process any queued SMS messages
            with contextlib.suppress(Empty):
                sms = self._inbox.get_nowait()
                self.handle_message(sms.number, sms.text)

        logger.info("SMS handler communication stopped")

    def _on_sms_received(self, sms: ReceivedSms):
        """
        Callback invoked when a new SMS is received.
        Must never raise (raising suppresses gsmmodem's auto-delete).
        Only enqueues the message; actual processing happens on handler thread.
        """
        try:
            self._inbox.put_nowait(sms)
        except Exception:  # pylint: disable=broad-except
            logger.exception("Failed to queue SMS message")

    def handle_message(self, number: str, text: str):
        """
        Process an SMS message: validate sender, parse command, dispatch.
        """
        # Normalize and mask sender number (e.g., keep last 4 digits)
        logger.debug("Processing SMS from %s", number)

        action_config = SMSActionConfig.load_config()

        # Validate sender against configured phone numbers if required
        if action_config.check_phone_number:
            config = GSMProvider.get_config()
            if not self._is_authorized_sender(number, config):
                logger.warning("SMS from unauthorized number %s, ignoring", number)
                return

        # Parse access code if required
        user = None
        command_text = ""
        if action_config.access_code_required:
            # Parse the message for an access code and command keyword
            parts = text.strip().split(None, 1)  # Split on first whitespace
            if not parts:
                logger.warning("Empty SMS message from %s", number)
                return

            access_code = parts[0]
            command_text = parts[1] if len(parts) > 1 else ""

            # Validate access code
            session = get_database_session()
            try:
                user = get_user_with_access_code(session, access_code)
                if not user:
                    logger.warning("Invalid access code in SMS from %s", number)
                    return

                logger.info("Valid SMS access code from user %s", user.id)
            finally:
                session.close()
        else:
            command_text = text.strip()

        # Dispatch to command handler (stub for now)
        self._dispatch_command(command_text, user)

    def _is_authorized_sender(self, number: str, config: GSMConfig) -> bool:
        """Check if sender number matches configured phone numbers."""
        if not number:
            return False

        # Normalize numbers for comparison (remove spaces, dashes, etc.)
        normalized = self._normalize_number(number)
        authorized_numbers = [
            self._normalize_number(n) for n in [config.phone_number_1, config.phone_number_2] if n
        ]
        return normalized in authorized_numbers

    @staticmethod
    def _normalize_number(number: str) -> str:
        """Remove non-digit characters from phone number."""
        if not number:
            return ""

        number = number.removeprefix("+")  # Remove leading '+'
        number = number.removeprefix("00")  # Remove leading '00'

        return "".join(c for c in number if c.isdigit())

    def _dispatch_command(self, command: str, user: User | None):
        """Dispatch SMS command to appropriate handler (stub implementations)."""

        logger.debug("Handling message: %s from user %s", command, user.id if user else None)
        command_config = SMSCommandConfig.load_config()

        def compare(a: str, b: str, case_sensitive: bool) -> bool:
            if case_sensitive:
                return a == b
            return a.lower() == b.lower()

        if compare(command, command_config.arm_away_command, command_config.case_sensitive):
            logger.info("SMS: arm_away command from user %s", user.id if user else None)
            self._broadcaster.send_message(MonitorArmAwayCommand(user_id=user.id if user else None))
        elif compare(command, command_config.arm_stay_command, command_config.case_sensitive):
            logger.info("SMS: arm_stay command from user %s", user.id if user else None)
            self._broadcaster.send_message(MonitorArmStayCommand(user_id=user.id if user else None))
        elif compare(command, command_config.disarm_command, command_config.case_sensitive):
            logger.info("SMS: disarm command from user %s", user.id if user else None)
            self._broadcaster.send_message(MonitorDisarmCommand(user_id=user.id if user else None))
        else:
            logger.warning("Invalid message '%s' from user %s", command, user.id if user else None)
