#!/usr/bin/env python3
import json
import logging
import os
import sys
from copy import copy
from ipaddress import ip_address
from noipy.main import execute_update
from dotenv import load_dotenv

import argparse
import requests

load_dotenv()
load_dotenv("secrets.env")
sys.path.insert(0, os.getenv("PYTHONPATH"))

from models import Option
from monitor.database import Session
from constants import LOG_SC_DYNDNS
from tools.dictionary import filter_keys


def get_dns_records(hostname=None, record_type='A'):
    """
    Query IP address from google.

    Avoid conflict of local and remote IP addresses.
    """
    if hostname is None:
        return None

    api_url = 'https://dns.google.com/resolve?'
    params = {'name': hostname, 'type': record_type}
    try:
        response = requests.get(api_url, params=params)
        return response.json()
    except requests.exceptions.RequestException:
        return None


class DynDns:
    """
    Class for managing the IP address of the dynamic DNS name.
    """
    def __init__(self, logger=None):
        self._logger = logger or logging.getLogger(LOG_SC_DYNDNS)
        self._db_session = Session()

    def update_ip(self, force=False):
        """
        Compare IP address in DNS server and actual lookup result.
        Update the IP address at DNSprovider if it's necesarry.
        :param force: force the update
        """
        noip_config = self._db_session.query(Option).filter_by(name="network", section="dyndns").first()
        if noip_config:
            noip_config = json.loads(noip_config.value)

        if not noip_config:
            self._logger.error("Missing dyndns settings!")
            return

        noip_config["force"] = force
        tmp_config = copy(noip_config)
        filter_keys(tmp_config, ["password"])
        self._logger.info("Update dynamics DNS provider with options: %s", tmp_config)

        # DNS lookup IP from hostname
        try:
            current_ip = get_dns_records(hostname=noip_config["hostname"])["Answer"][0]["data"]
        except KeyError as error:
            self._logger.error("Failed to query IP Address! %s", error)
            return False

        # Getting public IP
        new_ip = requests.get("http://ifconfig.me/ip").text.strip()
        try:
            # converting the address to string for comparison
            new_ip = format(ip_address(new_ip))
        except ValueError:
            self._logger.info("Invalid IP address: %s", new_ip)
            return False

        if (new_ip != current_ip) or force:
            self._logger.info("IP: '%s' => '%s'", current_ip, new_ip)
            noip_config["ip"] = new_ip
            result = self.save_ip(noip_config)
            self._logger.info("Update result: '%s'", result)
            return True
        else:
            self._logger.info("IP: '%s' == '%s'", current_ip, new_ip)
            self._logger.info("No IP update necessary")

        return True

    def save_ip(self, noip_config):
        """
        Save IP to the DNS provider
        :param noip_config: dictionary of settings (provider, username, password, hostname, ip)
        """

        class Arguments:
            pass

        args = Arguments()
        args.store = False
        try:
            args.provider = noip_config["provider"]
            args.usertoken = noip_config["username"]
            args.password = noip_config["password"].replace(".duckdns.org", "")
            args.hostname = noip_config["hostname"]
            args.ip = noip_config["ip"]
            return execute_update(args)
        except KeyError as error:
            self._logger.error("Failed to update NOIP provider! (%s)", error)
            self._logger.debug("NOIP settings: %s", noip_config)

        return {}


def main():
    parser = argparse.ArgumentParser(description="Update IP address at DNS provider")
    parser.add_argument("-v", "--verbose", action="store_true", help="increase output verbosity")
    parser.add_argument("-f", "--force", action="store_true", help="force update")

    args = parser.parse_args()

    logging.basicConfig(format="%(asctime)-15s: %(message)s", level=logging.DEBUG if args.verbose else logging.INFO)

    dyndns = DynDns(logging.getLogger("argus_noip"))
    dyndns.update_ip(force=args.force)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass

