# -*- coding: utf-8 -*-
# @Author: Gábor Kovács
# @Date:   2021-02-25 20:04:32
# @Last Modified by:   Gábor Kovács
# @Last Modified time: 2021-02-25 20:04:34
import logging
from threading import Event, Thread

from tools.certbot import Certbot
from tools.dyndns import DynDns
from tools.schedule import enable_certbot_job, enable_dyndns_job
from constants import THREAD_SECCON, LOG_SECCON


class SecureConnection(Thread):
    lock = Event()

    def __init__(self, actions):
        super(SecureConnection, self).__init__(name=THREAD_SECCON, daemon=True)
        self._actions = actions
        self._logger = logging.getLogger(LOG_SECCON)

    def run(self):
        if SecureConnection.lock.is_set():
            self._logger.info("A thread is already running...")
            return

        SecureConnection.lock.set()

        # update configuration
        self._logger.debug("Start switching to secure connection...")
        DynDns().update_ip()
        Certbot().update_certificates()

        # enable cron jobs for update configuration periodically
        enable_dyndns_job()
        enable_certbot_job()

        SecureConnection.lock.clear()
