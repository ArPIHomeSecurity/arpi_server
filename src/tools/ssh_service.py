#!/usr/bin/env python3

import logging
import os
import subprocess
from ipaddress import ip_network

from constants import LOG_SC_ACCESS
from monitor.config_helper import load_ssh_config
from monitor.database import get_database_session


class SSHService:
    def __init__(self):
        super(SSHService, self).__init__()
        self._logger = logging.getLogger(LOG_SC_ACCESS)
        self._ssh_config = load_ssh_config(get_database_session(new_connection=True))

    def update_service_state(self):
        self._logger.debug("Updating SSH service state...")
        self.enable_service(self._ssh_config.service_enabled)

    def enable_service(self, enable: bool):
        try:
            if enable:
                self._logger.info("Enabling SSH service")
                subprocess.run(["sudo", "systemctl", "start", "ssh.service"], check=True)
                subprocess.run(["sudo", "systemctl", "enable", "ssh.service"], check=True)
            else:
                self._logger.info("Disabling SSH service")
                subprocess.run(["sudo", "systemctl", "stop", "ssh.service"], check=True)
                subprocess.run(["sudo", "systemctl", "disable", "ssh.service"], check=True)
        except subprocess.CalledProcessError as error:
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
        # identify default interface IP
        interface = os.popen("ip route show default").read().split("dev ")[1].split(" ")[0]
        return os.popen(f"ip addr show {interface}").read().split("inet ")[1].split(" brd")[0]

    def _update_access_cidr(self, network, enable: bool):
        if enable:
            self._logger.info("Restrict SSH access only for %s to %s", network, enable)
            os.system("sudo sed -i '/sshd:/d' /etc/hosts.allow")
            os.system(f"echo 'sshd: {network}' | sudo tee -a /etc/hosts.allow")
            os.system("echo 'sshd: ALL' | sudo tee -a /etc/hosts.deny")
        else:
            self._logger.info("Allow SSH access from any networks")
            os.system("sudo sed -i '/sshd:/d' /etc/hosts.allow")
            os.system("sudo sed -i '/sshd: ALL/d' /etc/hosts.deny")

    def update_password_authentication(self):
        """
        Update password authentication
        """
        self._logger.info("Updating password authentication")
        self.enable_password_authentication(
            self._ssh_config.password_authentication_enabled,
            self._ssh_config.service_enabled
        )

    def enable_password_authentication(self, enable: bool, restart=True):
        """
        Enable password authentication
        """
        if enable:
            self._logger.info("Enabling password authentication")
            os.system(
                'sudo sed -i -E -e "s/.*PasswordAuthentication (yes|no)/PasswordAuthentication yes/g" /etc/ssh/sshd_config'
            )
        else:
            self._logger.info("Disabling password authentication")
            os.system(
                'sudo sed -i -E -e "s/.*PasswordAuthentication (yes|no)/PasswordAuthentication no/g" /etc/ssh/sshd_config'
            )

        if restart:
            self._logger.info("Restarting SSH service")
            try:
                subprocess.run(["systemctl", "restart", "ssh.service"], check=True)
            except subprocess.CalledProcessError as error:
                self._logger.error("Failed to restart SSH service: %s", error)
