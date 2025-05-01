"""
SecureConnection
"""
import logging
from threading import Event, Thread

from monitor.socket_io import send_public_access
from tools.certbot import Certbot
from tools.dyndns import DynDns
from tools.schedule import enable_dyndns_job
from constants import THREAD_SECCON, LOG_SECCON


class SecureConnection(Thread):
    """
    SecureConnection class for updating to remote/secure secure connection
    with dynamic dns and certificate.
    """
    lock = Event()

    def __init__(self):
        super(SecureConnection, self).__init__(name=THREAD_SECCON, daemon=True)
        self._logger = logging.getLogger(LOG_SECCON)

    def run(self):
        if SecureConnection.lock.is_set():
            self._logger.info("A thread is already running...")
            return

        SecureConnection.lock.set()

        # update configuration
        self._logger.debug("Start switching to secure connection...")

        # update the IP address of the dynamic DNS
        dyndns = DynDns()
        dyndns.update_ip()
        if not dyndns.wait_for_update(300):
            self._logger.error("Failed to update IP address!")
            SecureConnection.lock.clear()
            return

        # update the certificate
        certbot = Certbot()
        certificated_updated = certbot.update_certificate()

        # enable cron jobs for update configuration periodically
        enable_dyndns_job()

        if certificated_updated:
            self._logger.debug("Certificate updated successfully")
            public_access = certbot.check_certificate_exists()
            send_public_access(public_access)
        else:
            self._logger.error("Failed to update certificate!")

        SecureConnection.lock.clear()
