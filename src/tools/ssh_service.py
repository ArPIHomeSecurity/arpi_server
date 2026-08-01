#!/usr/bin/env python3

import logging
import os
import subprocess
from ipaddress import ip_network

from monitor.config.models import SSHConfig
from monitor.database import get_database_session
from utils.constants import LOG_SC_ACCESS

logger = logging.getLogger(LOG_SC_ACCESS)


class SSHService:
    def __init__(self):
        super().__init__()
        self._ssh_config = SSHConfig.load_config(get_database_session())

    def update_service_state(self):
        logger.debug("Updating SSH service state...")
        self.enable_service(self._ssh_config.service_enabled)

    def enable_service(self, enable: bool):
        try:
            if enable:
                logger.info("Enabling SSH service")
                subprocess.run(["sudo", "systemctl", "start", "ssh.service"], check=True)
                subprocess.run(["sudo", "systemctl", "enable", "ssh.service"], check=True)
            else:
                logger.info("Disabling SSH service")
                subprocess.run(["sudo", "systemctl", "stop", "ssh.service"], check=True)
                subprocess.run(["sudo", "systemctl", "disable", "ssh.service"], check=True)
        except subprocess.CalledProcessError as error:
            logger.error("Failed to update SSH service state: %s", error)

    def update_access_local_network(self):
        logger.debug("Updating SSH access...")

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
            logger.info("Restrict SSH access only for %s to %s", network, enable)
            os.system("sudo sed -i '/sshd:/d' /etc/hosts.allow")
            os.system(f"echo 'sshd: {network}' | sudo tee -a /etc/hosts.allow")
            os.system("echo 'sshd: ALL' | sudo tee -a /etc/hosts.deny")
        else:
            logger.info("Allow SSH access from any networks")
            os.system("sudo sed -i '/sshd:/d' /etc/hosts.allow")
            os.system("sudo sed -i '/sshd: ALL/d' /etc/hosts.deny")

    def update_password_authentication(self):
        """
        Update password authentication
        """
        logger.info("Updating password authentication")
        self.enable_password_authentication(
            self._ssh_config.password_authentication_enabled, self._ssh_config.service_enabled
        )

    def enable_password_authentication(self, enable: bool, restart=True):
        """
        Enable password authentication
        """
        if enable:
            logger.info("Enabling password authentication")
            os.system(
                'sudo sed -i -E -e "s/.*PasswordAuthentication (yes|no)/PasswordAuthentication yes/g" /etc/ssh/sshd_config'
            )
        else:
            logger.info("Disabling password authentication")
            os.system(
                'sudo sed -i -E -e "s/.*PasswordAuthentication (yes|no)/PasswordAuthentication no/g" /etc/ssh/sshd_config'
            )

        if restart:
            logger.info("Restarting SSH service")
            try:
                subprocess.run(["systemctl", "restart", "ssh.service"], check=True)
            except subprocess.CalledProcessError as error:
                logger.error("Failed to restart SSH service: %s", error)
