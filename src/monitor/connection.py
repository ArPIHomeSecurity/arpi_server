"""
SecureConnection
"""

import logging
from threading import Event, Thread

from monitor.socket_io import send_public_access
from tools.certbot import Certbot
from tools.dyndns import DynDns
from tools.schedule import enable_dyndns_job
from utils.constants import LOG_SECCON, THREAD_SECCON

logger = logging.getLogger(LOG_SECCON)


class SecureConnection(Thread):
    """
    SecureConnection class for updating to remote/secure secure connection
    with dynamic dns and certificate.
    """

    lock = Event()

    def __init__(self):
        super().__init__(name=THREAD_SECCON, daemon=True)

    def run(self):
        if SecureConnection.lock.is_set():
            logger.info("A thread is already running...")
            return

        SecureConnection.lock.set()

        # update configuration
        logger.debug("Start switching to secure connection...")

        # update the IP address of the dynamic DNS
        dyndns = DynDns()
        dyndns.update_ip()
        if not dyndns.wait_for_update(300):
            logger.error("Failed to update IP address!")
            SecureConnection.lock.clear()
            return

        # update the certificate
        certbot = Certbot()
        certificated_updated = certbot.update_certificate()

        # enable cron jobs for update configuration periodically
        enable_dyndns_job()

        if certificated_updated:
            logger.debug("Certificate updated successfully")
            public_access = certbot.check_certificate_exists()
            send_public_access(public_access)
        else:
            logger.error("Failed to update certificate!")

        SecureConnection.lock.clear()
