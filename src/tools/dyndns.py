#!/usr/bin/env python3
import argparse
import logging
import os
import sys
from copy import copy
from ipaddress import ip_address

import requests
from dotenv import load_dotenv
from noipy.main import execute_update
from psycopg2 import OperationalError


load_dotenv()
load_dotenv("secrets.env")
sys.path.insert(0, os.getenv("PYTHONPATH"))

from constants import LOG_SC_DYNDNS
from monitor.config_helper import load_dyndns_config
from tools.dictionary import filter_keys


def get_dns_records(hostname=None, record_type="A"):
    """
    Query IP address from google.

    Avoid conflict of local and remote IP addresses.
    """
    if hostname is None:
        return None

    api_url = "https://dns.google.com/resolve?"
    params = {"name": hostname, "type": record_type}
    try:
        response = requests.get(api_url, params=params)
        return response.json()
    except requests.RequestException as request_error:
        logging.error("Failed to query DNS record! (Request error: %s)", request_error)
        return None


class DynDns:
    """
    Class for managing the IP address of the dynamic DNS name.
    """

    def __init__(self, logger=None):
        self._logger = logger or logging.getLogger(LOG_SC_DYNDNS)

    def update_ip(self, force=False):
        """
        Compare IP address in DNS server and actual lookup result.
        Update the IP address at DNSprovider if it's necessary.
        :param force: force the update
        """
        dyndns_config = load_dyndns_config()

        if not dyndns_config:
            self._logger.info("No dynamic dns configuration found")
            return

        if not dyndns_config.provider:
            self._logger.info("No dynamic dns provider found")
            return False

        dyndns_config["force"] = force
        tmp_config = copy(dyndns_config)
        filter_keys(tmp_config, ["password"])
        self._logger.info("Update dynamics DNS provider with options: %s", tmp_config)

        if not dyndns_config["provider"]:
            self._logger.error("Missing provider!")
            return False

        # DNS lookup IP from hostname
        response = None
        try:
            response = get_dns_records(hostname=dyndns_config["hostname"])
            current_ip = response["Answer"][0]["data"]
        except KeyError as key_error:
            self._logger.error(
                "Failed to query IP Address! (Missing key: %s) Response: %s",
                key_error,
                response,
            )
            return False
        except TypeError as type_error:
            self._logger.error(
                "Failed to query IP Address! (Type: %s) Response: %s",
                type_error,
                response,
            )
            return False

        try:
            # Getting public IP
            new_ip = requests.get("http://checkip.amazonaws.com/", timeout=30).text.strip()
        except requests.RequestException as request_error:
            self._logger.error("Failed to query IP Address! (Request error: %s)", request_error)
            return False

        try:
            # converting the address to string for comparison
            new_ip = format(ip_address(new_ip))
        except ValueError:
            self._logger.info("Invalid IP address: %s", new_ip)
            return False

        if (new_ip != current_ip) or force:
            self._logger.info("IP: '%s' => '%s'", current_ip, new_ip)
            dyndns_config["ip"] = new_ip
            result = self.save_ip(dyndns_config)
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
        except KeyError as key_error:
            self._logger.error("Failed to update NOIP provider! (%s)", key_error)
            self._logger.debug("NOIP settings: %s", noip_config)

        return {}


def main():
    parser = argparse.ArgumentParser(description="Update IP address at DNS provider")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="increase output verbosity"
    )
    parser.add_argument("-f", "--force", action="store_true", help="force update")

    args = parser.parse_args()

    logging.basicConfig(
        format="%(asctime)-15s: %(message)s",
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    dyndns = DynDns(logging.getLogger("argus_noip"))
    dyndns.update_ip(force=args.force)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except OperationalError as database_error:
        logging.warning("Database error: %s", database_error)
