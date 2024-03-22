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

    def update_access_local_network(self):
        self._logger.info("Updating SSH access...")
        ssh_config = load_ssh_config()
        if not ssh_config:
            self._logger.info("Missing ssh settings!")
            return

        cidr = os.environ.get("SSH_LOCAL_NETWORK", self._get_local_ip())
        ip_range = ip_network(cidr, False)
        local_network = f"{ip_range.network_address}/{ip_range.netmask}"
        if ssh_config.ssh_restrict_local_network:
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
        self._logger.info("Restrict SSH access only for %s to %s", network, enable)

        if enable:
            os.system("sed -i '/sshd:/d' /etc/hosts.allow")
            os.system(f"echo 'sshd: {network}' >> /etc/hosts.allow")
            os.system("echo 'sshd: ALL' >> /etc/hosts.deny")
        else:
            os.system("sed -i '/sshd:/d' /etc/hosts.allow")
            os.system("sed -i '/sshd: ALL/d' /etc/hosts.deny")


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
        "--allow-local-networks",
        action="store_true",
        default=None,
        help="Restrict SSH access only from local network",
    )
    args.add_argument(
        "--allow-any-networks",
        action="store_true",
        default=None,
        help="Allow SSH access from all networks"
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

    if args.allow_local_networks is not None:
        update_access_local_network(True)
    if args.allow_any_networks is not None:
        update_access_local_network(False)


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


def update_access_local_network(enabled: bool):
    """
    Update access from router
    """
    ssh = SSH()
    cidr = ssh._get_local_ip()
    ip_range = ip_network(cidr, False)
    local_network = f"{ip_range.network_address}/{ip_range.netmask}"
    if enabled:
        logging.info("Allow SSH access only from local network")
        ssh._update_access_cidr(local_network, True)
        logging.info("Access from router is enabled")
    else:
        logging.info("Allow SSH access from any networks")
        ssh._update_access_cidr(local_network, False)
        logging.info("Access from router is disabled")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
