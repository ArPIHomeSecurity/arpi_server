"""
Handles SMS messages received from GSM modem.
"""

import contextlib
import logging
from enum import Enum
from queue import Empty, Queue
from threading import Thread

from gsmmodem.modem import ReceivedSms

from monitor.actions import MonitorStopCommand, MonitorUpdateConfigCommand
from monitor.adapters.gsm_provider import GSMProvider
from monitor.broadcast import Broadcaster
from monitor.config.models import GSMConfig
from monitor.database import get_database_session
from utils.constants import LOG_SMS, THREAD_SMS
from utils.queries import get_user_with_access_code

logger = logging.getLogger(LOG_SMS)

POLL_TIMEOUT = 1  # sec, queue poll timeout to stay responsive to stop commands


class SmsCommand(Enum):
    """SMS command types parsed from message content."""

    ARM_AWAY = "arm_away"
    ARM_STAY = "arm_stay"
    DISARM = "disarm"
    STATUS = "status"
    UNKNOWN = "unknown"


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
        except Exception:
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
        except Exception:
            logger.exception("Failed to queue SMS message")

    def handle_message(self, number: str, text: str):
        """
        Process an SMS message: validate sender, parse command, dispatch.
        """
        # Normalize and mask sender number (e.g., keep last 4 digits)
        masked_number = self._mask_number(number)
        logger.debug("Processing SMS from %s", masked_number)

        # Validate sender against configured phone numbers
        config = GSMProvider.get_config()
        if not self._is_authorized_sender(number, config):
            logger.warning("SMS from unauthorized number %s, ignoring", masked_number)
            return

        # Parse the message for an access code and command keyword
        parts = text.strip().split(None, 1)  # Split on first whitespace
        if not parts:
            logger.warning("Empty SMS message from %s", masked_number)
            return

        access_code = parts[0]
        command_text = parts[1] if len(parts) > 1 else ""

        # Validate access code
        session = get_database_session()
        try:
            user = get_user_with_access_code(session, access_code)
            if not user:
                logger.warning("Invalid access code in SMS from %s", masked_number)
                return

            logger.info("Valid SMS access code from user %s", user.id)
        finally:
            session.close()

        # Parse command keyword
        command = self._parse_command(command_text)
        logger.debug("Parsed SMS command: %s from %s", command.name, masked_number)

        # Dispatch to command handler (stub for now)
        self._dispatch_command(command, user, masked_number)

    def _is_authorized_sender(self, number: str, config: GSMConfig) -> bool:
        """Check if sender number matches configured phone numbers."""
        if not number:
            return False

        # Normalize numbers for comparison (remove spaces, dashes, etc.)
        normalized = self._normalize_number(number)
        authorized_numbers = [
            self._normalize_number(n)
            for n in [config.phone_number_1, config.phone_number_2]
            if n
        ]
        return normalized in authorized_numbers

    @staticmethod
    def _normalize_number(number: str) -> str:
        """Remove non-digit characters from phone number."""
        if not number:
            return ""
        return "".join(c for c in number if c.isdigit())

    @staticmethod
    def _mask_number(number: str) -> str:
        """Mask phone number for logging (show last 4 digits only)."""
        if not number or len(number) < 4:
            return "****"
        return "****" + number[-4:]

    @staticmethod
    def _parse_command(text: str) -> SmsCommand:
        """Parse command keyword from message text."""
        if not text:
            return SmsCommand.UNKNOWN

        keyword = text.strip().lower().split()[0]
        match keyword:
            case "arm_away" | "armaway" | "arm away":
                return SmsCommand.ARM_AWAY
            case "arm_stay" | "armstay" | "arm stay":
                return SmsCommand.ARM_STAY
            case "disarm":
                return SmsCommand.DISARM
            case "status":
                return SmsCommand.STATUS
            case _:
                return SmsCommand.UNKNOWN

    @staticmethod
    def _dispatch_command(command: SmsCommand, user, masked_number: str):
        """Dispatch SMS command to appropriate handler (stub implementations)."""
        match command:
            case SmsCommand.ARM_AWAY:
                logger.info("SMS: arm_away command from user %s (%s)", user.id, masked_number)
                # TODO: implement actual arm_away logic
            case SmsCommand.ARM_STAY:
                logger.info("SMS: arm_stay command from user %s (%s)", user.id, masked_number)
                # TODO: implement actual arm_stay logic
            case SmsCommand.DISARM:
                logger.info("SMS: disarm command from user %s (%s)", user.id, masked_number)
                # TODO: implement actual disarm logic
            case SmsCommand.STATUS:
                logger.info("SMS: status command from user %s (%s)", user.id, masked_number)
                # TODO: implement actual status logic
            case SmsCommand.UNKNOWN:
                logger.warning("SMS: unknown command from user %s (%s)", user.id, masked_number)
