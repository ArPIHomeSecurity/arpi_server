#!/usr/bin/env python3

import argparse
import subprocess
import logging
import os
import sys

from dotenv import load_dotenv
from gi.repository import GLib
from pydbus import SystemBus


load_dotenv()
load_dotenv("secrets.env")
sys.path.insert(0, os.getenv("PYTHONPATH"))

from models import Option
from constants import LOG_SC_ACCESS
from monitor.config_helper import load_ssh_config
from monitor.database import Session


class SSH:
    def __init__(self):
        super(SSH, self).__init__()
        self._logger = logging.getLogger(LOG_SC_ACCESS)
        self._db_session = Session()
        self._bus = SystemBus()

    def update_ssh_service(self):
        ssh_config = load_ssh_config()

        if not ssh_config:
            self._logger.info("Missing ssh settings!")
            return

        if ssh_config.ssh:
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

    def update_access_from_router(self):
        self._logger.info("Updating access from router")
        ssh_config = load_ssh_config()
        if not ssh_config:
            self._logger.info("Missing ssh settings!")
            return

        router_ip = os.environ.get("SSH_ROUTER_IP", self._get_router_local_ip())
        if ssh_config.ssh_from_router:
            self._update_access_for_ip(router_ip, True)
        else:
            self._update_access_for_ip(router_ip, False)

    def _get_router_local_ip(self) -> str:
        """
        Get the local IP of the router with "route" command
        """
        routes = subprocess.check_output(["route", "-n"]).decode("utf-8")
        DESTINATION = 0
        GATEWAY = 1
        FLAGS = 3
        for line in routes.splitlines():
            fields = line.strip().split()
            if fields[DESTINATION] != '0.0.0.0' or "G" not in fields[FLAGS]:
                # If not default route or not RTF_GATEWAY, skip it
                continue

            return fields[GATEWAY]

    def _update_access_for_ip(self, ip, enable: bool):
        self._logger.info("Updating access for %s to %s", ip, enable)

        rule = f"rule family='ipv4' source address='{ip}' reject"

        if enable:
            cmd = f'firewall-cmd --zone=public --remove-rich-rule="{rule}"'
            subprocess.run(cmd, check=True, shell=True)
        else:
            cmd = f'firewall-cmd --zone=public --add-rich-rule="{rule}"'
            subprocess.run(cmd, check=True, shell=True)


def main():
    args = argparse.ArgumentParser(description="SSH service")
    args.add_argument(
        "--enable-ssh",
        action="store_true",
        default=None,
        help="Enable SSH"
    )
    args.add_argument(
        "--disable-ssh",
        action="store_true",
        default=None,
        help="Disable SSH"
    )
    args.add_argument(
        "--enable-access-from-router",
        action="store_true",
        default=None,
        help="Enable access from router",
    )
    args.add_argument(
        "--disable-access-from-router",
        action="store_true",
        default=None,
        help="Disable access from router",
    )
    args.add_argument(
        "--get-router-ip",
        action="store_true",
        default=None,
        help="Get router IP",
    )

    args = args.parse_args()

    if args.get_router_ip:
        ssh = SSH()
        print(ssh._get_router_local_ip())

    if args.enable_ssh == True:
        update_ssh_service(True)
    elif args.disable_ssh == False:
        update_ssh_service(False)

    if args.enable_access_from_router == True:
        update_access_from_router(True)
    elif args.disable_access_from_router == False:
        update_access_from_router(False)


def update_ssh_service(enabled: bool):
    """
    Update SSH service status
    """
    ssh = SSH()
    logging.info("Updating SSH service")
    if enabled:
        logging.info("Enabling SSH")
        ssh.start_ssh()
        logging.info("SSH is enabled")
    else:
        logging.info("Disabling SSH")
        # ssh.stop_ssh()
        logging.info("SSH is disabled")


def update_access_from_router(enabled: bool):
    """
    Update access from router
    """
    ssh = SSH()
    if enabled:
        logging.info("Enabling access from router")
        ssh._update_access_for_ip(ssh._get_router_local_ip(), True)
        logging.info("Access from router is enabled")
    else:
        logging.info("Disabling access from router")
        ssh._update_access_for_ip(ssh._get_router_local_ip(), False)
        logging.info("Access from router is disabled")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
