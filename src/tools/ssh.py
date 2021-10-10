# -*- coding: utf-8 -*-
# @Author: Gábor Kovács
# @Date:   2021-02-25 20:05:29
# @Last Modified by:   Gábor Kovács
# @Last Modified time: 2021-02-25 20:05:31
import json
import logging
from pydbus import SystemBus
from models import Option
from monitoring.constants import LOG_SC_ACCESS

from gi.repository import GLib

from monitoring.database import Session


class SSH:
    def __init__(self):
        super(SSH, self).__init__()
        self._logger = logging.getLogger(LOG_SC_ACCESS)
        self._db_session = Session()
        self._bus = SystemBus()

    def update_ssh_service(self):
        ssh_config = self._db_session.query(Option).filter_by(name="network", section="access").first()
        if ssh_config:
            ssh_config = json.loads(ssh_config.value)
        else:
            self._logger.error("Missing ssh settings!")
            return

        if ssh_config.get("ssh", True):
            self.start_ssh()
        else:
            self.stop_ssh()

    def start_ssh(self):
        self._logger.info("Starting SSH")
        systemd = self._bus.get(".systemd1")

        try:
            systemd.StartUnit("ssh.service", "fail")
            systemd[".Manager"].EnableUnitFiles(["ssh.service"], False, True)
        except GLib.Error as error:
            self._logger.error("Failed: %s", error)

    def stop_ssh(self):
        self._logger.info("Stopping SSH")
        systemd = self._bus.get(".systemd1")

        try:
            systemd.StopUnit("ssh.service", "fail")
            systemd[".Manager"].DisableUnitFiles(["ssh.service"], False)
        except GLib.Error as error:
            self._logger.error("Failed: %s", error)
