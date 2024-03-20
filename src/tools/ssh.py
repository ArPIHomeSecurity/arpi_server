#!/usr/bin/env python3

import argparse
from ipaddress import ip_network
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

    def update_access_for_local_network(self):
        self._logger.info("Updating access for local network")
        ssh_config = load_ssh_config()
        if not ssh_config:
            self._logger.info("Missing ssh settings!")
            return

        cidr = os.environ.get("SSH_LOCAL_NETWORK", self._get_local_ip())
        ip_range = ip_network(cidr, False)
        local_network = f"{ip_range.network_address}/{ip_range.netmask}"
        if ssh_config.ssh_from_local_network:
            self._update_access_cidr(local_network, True)
        else:
            self._update_access_cidr(local_network, False)

    def _get_local_ip(self) -> str:
        """
        Get the local IP of the device in CIDR format.
        IP/prefix
        """
        return os.popen('ip addr show wlan0').read().split("inet ")[1].split(" brd")[0]

    def _update_access_cidr(self, network, enable: bool):
        self._logger.info("Updating access for %s to %s", network, enable)

        if enable:
            # allow access for cidr with hosts.allow
            # replace line starting with sshd: with sshd: network or add new line
            os.system("sed -i '/sshd:/d' /etc/hosts.allow")
            os.system(f"echo 'sshd: {network}' >> /etc/hosts.allow")
        else:
            # remove access for cidr with hosts.allow
            os.system("sed -i '/sshd:/d' /etc/hosts.allow")


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
        "--enable-access-from-local-network",
        action="store_true",
        default=None,
        help="Enable access from local network",
    )
    args.add_argument(
        "--disable-access-from-local-network",
        action="store_true",
        default=None,
        help="Disable access from local network"
    )
    args.add_argument(
        "--get-local-ip",
        action="store_true",
        default=None,
        help="Get local IP"
    )

    args = args.parse_args()

    logging.basicConfig(level=logging.INFO)
    print(args)

    if args.get_local_ip:
        ssh = SSH()
        print(ssh._get_local_ip())

    if args.enable_ssh is not None:
        update_ssh_service(args.enable_ssh)

    if args.enable_access_from_local_network is not None:
        update_access_from_local_network(True)
    if args.disable_access_from_local_network is not None:
        update_access_from_local_network(False)


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


def update_access_from_local_network(enabled: bool):
    """
    Update access from router
    """
    ssh = SSH()
    cidr = ssh._get_local_ip()
    ip_range = ip_network(cidr, False)
    local_network = f"{ip_range.network_address}/{ip_range.netmask}"
    if enabled:
        logging.info("Enabling access for local network")
        ssh._update_access_cidr(local_network, True)
        logging.info("Access from router is enabled")
    else:
        logging.info("Disabling access for local network")
        ssh._update_access_cidr(local_network, False)
        logging.info("Access from router is disabled")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
