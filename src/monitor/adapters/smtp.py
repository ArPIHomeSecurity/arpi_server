import logging

from smtplib import SMTP, SMTPException
from socket import gaierror

from constants import LOG_NOTIFIER


class SMTPSender:

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
            return True
        except (gaierror, SMTPException) as error:
            self._logger.error("Can't connect to SMTP server! Error: %s ", error)
            return False

    def send_email(self, to_address, subject, content):
        if not self._server:
            return False

        try:
            self._logger.info("Sending email to '%s' ...", to_address)
            message = f"Subject: {subject}\n\n{content}".encode(encoding="utf_8", errors="strict")
            self._server.sendmail(
                from_addr="alert@arpi-security.info",
                to_addrs=to_address,
                msg=message
            )
        except SMTPException as error:
            self._logger.error("Can't send email! Error: %s ", error)
            return False

        self._logger.info("Sent email")
        return True

    def destroy(self):
        if self._server:
            self._logger.debug("Closing SMTP")
            self._server.quit()
