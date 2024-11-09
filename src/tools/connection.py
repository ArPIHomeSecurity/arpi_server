import logging
from threading import Event, Thread

from monitor.socket_io import send_public_access
from tools.certbot import Certbot
from tools.dyndns import DynDns
from tools.schedule import enable_dyndns_job
from constants import THREAD_SECCON, LOG_SECCON


class SecureConnection(Thread):
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

        DynDns().update_ip()
        certbot = Certbot()
        certificated_updated = certbot.update_certificate()

        # enable cron jobs for update configuration periodically
        enable_dyndns_job()

        if certificated_updated:
            public_access = certbot.check_certificate_exists()
            send_public_access(public_access)

        SecureConnection.lock.clear()
