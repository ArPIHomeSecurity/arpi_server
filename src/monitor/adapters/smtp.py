import logging

from smtplib import SMTP, SMTPException
from socket import gaierror

from constants import LOG_NOTIFIER


class SMTPNotConnected(Exception):
    """Thrown when SMTP is disconnected after a while."""
    pass


class SMTPSender:
    """Class for sending messages in email."""

    def __init__(self, hostname, port, username, password) -> None:
        self._logger = logging.getLogger(LOG_NOTIFIER)
        self._hostname = hostname
        self._port = port
        self._username = username
        self._password = password
        self._server = None

    def setup(self):
        if not self._hostname or \
                not self._port or \
                not self._username or \
                not self._password:
            self._logger.error("Invalid SMTP options: %s:%s / %s=>%s",
                               self._hostname,
                               self._port,
                               self._username,
                               self._password
                               )
            return False

        try:
            self._server = SMTP(f"{self._hostname}:{self._port}")
            self._server.ehlo()
            self._server.starttls()
            self._server.login(self._username, self._password)
            self._server.close()
            return True
        except (gaierror, SMTPException, OSError) as error:
            self._logger.error("Can't connect to SMTP server! Error: %s ", error)
            return False

    def send_email(self, to_address, subject, content):
        """Send an email with re-try when disconnected."""
        if not self._server:
            return False

        sent_email_counter = 0
        while sent_email_counter <= 2:
            try:
                self._send_email(to_address, subject, content)
                sent_email_counter = 2
                self._logger.info("Sent email")
                return True
            except SMTPNotConnected:
                # re-try when disconnected
                self.setup()
                sent_email_counter += 1
            except SMTPException as error:
                self._logger.error("Can't send email! Error: %s ", error)
                return False

        self._logger.error("Sending email failed")
        return False

    def _send_email(self, to_address, subject, content):
        """Send an email and detect disconnected state."""
        try:
            self._logger.info("Sending email to '%s' ...", to_address)
            message = f"Subject: {subject}\n\n{content}".encode(encoding="utf_8", errors="strict")
            self._server.sendmail(
                from_addr="alert@arpi-security.info",
                to_addrs=to_address,
                msg=message
            )
        except SMTPException as error:
            if "please run connect() first" in str(error):
                self._logger.warning("Can't send email because of disconnected server")
                raise SMTPNotConnected from error

            raise error

    def destroy(self):
        """Destroy the connection"""
        if self._server:
            self._logger.debug("Closing SMTP")
            self._server.quit()
