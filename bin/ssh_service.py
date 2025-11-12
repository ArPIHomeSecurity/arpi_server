#!/usr/bin/env python3
"""
ArPI SSH Service Management Tool
"""

import argparse
import logging
from ipaddress import ip_network

from tools.ssh_service import SSHService


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


def update_ssh_service(enabled: bool):
    """
    Update SSH service status
    """
    ssh = SSHService()
    logging.info("Updating SSH service")
    if enabled:
        logging.info("Enabling SSH")
        ssh.enable_service(True)
        logging.info("SSH is enabled")
    else:
        logging.info("Disabling SSH")
        ssh.enable_service(False)
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
