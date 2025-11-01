#!/usr/bin/env python3

import argparse
import logging
import os
from ipaddress import ip_network

from gi.repository import GLib
from pydbus import SystemBus

from constants import LOG_SC_ACCESS
from monitor.config_helper import load_ssh_config
from monitor.database import get_database_session


class SSHService:
    def __init__(self):
        super(SSHService, self).__init__()
        self._logger = logging.getLogger(LOG_SC_ACCESS)
        self._bus = SystemBus()
        self._ssh_config = load_ssh_config(get_database_session(new_connection=True))

    def update_service_state(self):
        self._logger.debug("Updating SSH service state...")
        self._enable_service(self._ssh_config.service_enabled)

    def _enable_service(self, enable: bool):
        systemd = self._bus.get(".systemd1")
        try:
            if enable:
                self._logger.info("Enabling SSH service")
                systemd.StartUnit("ssh.service", "fail")
                systemd[".Manager"].EnableUnitFiles(["ssh.service"], False, True)
            else:
                self._logger.info("Disabling SSH service")
                systemd.StopUnit("ssh.service", "fail")
                systemd[".Manager"].DisableUnitFiles(["ssh.service"], False)
        except GLib.Error as error:
            self._logger.error("Failed to update SSH service state: %s", error)

    def update_access_local_network(self):
        self._logger.debug("Updating SSH access...")

        cidr = os.environ.get("SSH_LOCAL_NETWORK", self._get_local_ip())
        ip_range = ip_network(cidr, False)
        local_network = f"{ip_range.network_address}/{ip_range.netmask}"
        if self._ssh_config.restrict_local_network:
            self._update_access_cidr(local_network, True)
        else:
            self._update_access_cidr(local_network, False)

    def _get_local_ip(self) -> str:
        """
        Get the local IP of the device in CIDR format.
        IP/prefix
        """
        return os.popen("ip addr show wlan0").read().split("inet ")[1].split(" brd")[0]

    def _update_access_cidr(self, network, enable: bool):
        if enable:
            self._logger.info("Restrict SSH access only for %s to %s", network, enable)
            os.system("sed -i '/sshd:/d' /etc/hosts.allow")
            os.system(f"echo 'sshd: {network}' >> /etc/hosts.allow")
            os.system("echo 'sshd: ALL' >> /etc/hosts.deny")
        else:
            self._logger.info("Allow SSH access from any networks")
            os.system("sed -i '/sshd:/d' /etc/hosts.allow")
            os.system("sed -i '/sshd: ALL/d' /etc/hosts.deny")

    def update_password_authentication(self):
        """
        Update password authentication
        """
        self._logger.info("Updating password authentication")
        self._enable_password_authentication(self._ssh_config.password_authentication_enabled)

    def _enable_password_authentication(self, enable: bool):
        """
        Enable password authentication
        """
        if enable:
            self._logger.info("Enabling password authentication")
            os.system(
                'sed -i -E -e "s/.*PasswordAuthentication (yes|no)/PasswordAuthentication yes/g" /etc/ssh/sshd_config'
            )
        else:
            self._logger.info("Disabling password authentication")
            os.system(
                'sed -i -E -e "s/.*PasswordAuthentication (yes|no)/PasswordAuthentication no/g" /etc/ssh/sshd_config'
            )

        self._logger.info("Restarting SSH service")
        systemd = self._bus.get(".systemd1")
        systemd.RestartUnit("ssh.service", "fail")


def main():
    args = argparse.ArgumentParser(description="SSH service")
    args.add_argument("--enable-ssh", action="store_true", default=None, help="Enable SSH")
    args.add_argument("--disable-ssh", action="store_true", default=None, help="Disable SSH")
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
        help="Allow SSH access from all networks",
    )
    args.add_argument("--get-local-ip", action="store_true", default=None, help="Get local IP")
    args.add_argument(
        "--enable-password",
        action="store_true",
        default=None,
        help="Enable password authentication",
    )
    args.add_argument(
        "--disable-password",
        action="store_true",
        default=None,
        help="Disable password authentication",
    )

    args = args.parse_args()

    logging.basicConfig(level=logging.INFO)
    print(args)

    if args.get_local_ip:
        ssh = SSHService()
        print(ssh._get_local_ip())

    if args.enable_ssh is not None:
        update_ssh_service(args.enable_ssh)

    if args.allow_local_networks is not None:
        update_access_local_network(True)
    if args.allow_any_networks is not None:
        update_access_local_network(False)

    if args.enable_password is not None:
        ssh = SSHService()
        ssh._enable_password_authentication(True)
    if args.disable_password is not None:
        ssh = SSHService()
        ssh._enable_password_authentication(False)


def update_ssh_service(enabled: bool):
    """
    Update SSH service status
    """
    ssh = SSHService()
    logging.info("Updating SSH service")
    if enabled:
        logging.info("Enabling SSH")
        ssh._enable_service(True)
        logging.info("SSH is enabled")
    else:
        logging.info("Disabling SSH")
        ssh._enable_service(False)
        logging.info("SSH is disabled")


def update_access_local_network(enabled: bool):
    """
    Update access from router
    """
    ssh = SSHService()
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
