#!/usr/bin/env python3
"""
ArPI SSH Service Management Tool
"""

import argparse
import logging
from ipaddress import ip_network

from tools.ssh_service import SSHService
from utils.constants import LOG_SC_ACCESS

logger = logging.getLogger(LOG_SC_ACCESS)


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
    args.add_argument("-v", "--verbose", action="store_true", help="Increase output verbosity.")

    args = args.parse_args()

    logging.basicConfig(
        format="%(asctime)-15s: %(message)s",
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

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
        ssh.enable_password_authentication(True)
    if args.disable_password is not None:
        ssh = SSHService()
        ssh.enable_password_authentication(False)

    if not any(
        [
            args.enable_ssh,
            args.disable_ssh,
            args.allow_local_networks,
            args.allow_any_networks,
            args.enable_password,
            args.disable_password,
            args.get_local_ip,
        ]
    ):
        logger.info("No SSH service action specified")


def update_ssh_service(enabled: bool):
    """
    Update SSH service status
    """
    ssh = SSHService()
    logger.info("Updating SSH service")
    if enabled:
        logger.info("Enabling SSH")
        ssh.enable_service(True)
        logger.info("SSH is enabled")
    else:
        logger.info("Disabling SSH")
        ssh.enable_service(False)
        logger.info("SSH is disabled")


def update_access_local_network(enabled: bool):
    """
    Update access from router
    """
    ssh = SSHService()
    cidr = ssh._get_local_ip()
    ip_range = ip_network(cidr, False)
    local_network = f"{ip_range.network_address}/{ip_range.netmask}"
    if enabled:
        logger.info("Allow SSH access only from local network")
        ssh._update_access_cidr(local_network, True)
        logger.info("Access from router is enabled")
    else:
        logger.info("Allow SSH access from any networks")
        ssh._update_access_cidr(local_network, False)
        logger.info("Access from router is disabled")


def cli_main():
    try:
        main()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    cli_main()
