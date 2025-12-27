#!/usr/bin/env python3
import logging
from dataclasses import asdict
from ipaddress import ip_address
from time import sleep, time

import requests
from noipy.main import execute_update

from utils.constants import LOG_SC_DYNDNS
from monitor.config_helper import DyndnsConfig, load_dyndns_config
from utils.dictionary import filter_keys
from utils.lock import file_lock

logger = logging.getLogger(LOG_SC_DYNDNS)


class DynDns:
    """
    Class for managing the IP address of the dynamic DNS name.
    """

    def get_dns_records(self, hostname=None, record_type="A"):
        """
        Query IP address from google.

        Avoid conflict of local and remote IP addresses.
        """
        if hostname is None:
            return None

        api_url = "https://dns.google.com/resolve?"
        params = {"name": hostname, "type": record_type}
        try:
            response = requests.get(api_url, params=params, timeout=30)
            dns_info = response.json()
            return dns_info["Answer"][0]["data"]
        except (KeyError, TypeError) as error:
            logger.error(
                "Failed to query IP Address! (Missing key: %s) Response: %s", error, response
            )
        except requests.RequestException as request_error:
            logger.error("Failed to query DNS record! (Request error: %s)", request_error)
            return None

    def get_public_ip(self):
        """
        Get the public IP address.
        """
        try:
            return requests.get("http://checkip.amazonaws.com/", timeout=30).text.strip()
        except requests.RequestException as request_error:
            logger.error("Failed to query IP Address! (Request error: %s)", request_error)
            return None

    @file_lock("dyndns.lock", timeout=3600)
    def update_ip(self, force=False):
        """
        Compare IP address in DNS server and actual lookup result.
        Update the IP address at DNSprovider if it's necessary.
        :param force: force the update
        """
        dyndns_config = load_dyndns_config()
        if not dyndns_config.provider:
            logger.info("No dynamic dns provider found")
            return False

        tmp_config = asdict(dyndns_config)
        filter_keys(tmp_config, ["password"])
        logger.info("Update dynamics DNS provider with options: %s", tmp_config)

        if not dyndns_config.provider:
            logger.error("Missing provider!")
            return False

        # DNS lookup IP from hostname
        current_ip = self.get_dns_records(hostname=dyndns_config.hostname)
        if not current_ip:
            return False

        new_ip = self.get_public_ip()
        if not new_ip:
            return False

        try:
            # converting the address to string for comparison
            new_ip = format(ip_address(new_ip))
        except ValueError:
            logger.info("Invalid IP address: %s", new_ip)
            return False

        if (new_ip != current_ip) or force:
            logger.info("IP: '%s' => '%s'", current_ip, new_ip)
            dyndns_config.ip = new_ip
            result = self.save_ip(dyndns_config)
            logger.info("Update result: '%s'", result)
            return True
        else:
            logger.info("IP: '%s' == '%s'", current_ip, new_ip)
            logger.info("No IP update necessary")

        return True

    def save_ip(self, noip_config: DyndnsConfig):
        """
        Save IP to the DNS provider
        :param noip_config: dictionary of settings (provider, username, password, hostname, ip)
        """

        class Arguments:
            pass

        args = Arguments()
        args.store = False
        try:
            args.provider = noip_config.provider
            args.usertoken = noip_config.username
            args.password = noip_config.password
            args.hostname = noip_config.hostname
            args.ip = noip_config.ip
            return execute_update(args)
        except KeyError as key_error:
            logger.error("Failed to update NOIP provider! (%s)", key_error)
            logger.debug("NOIP settings: %s", noip_config)

        return {}

    def wait_for_update(self, timeout=120) -> bool:
        """
        Wait for the update to be finished.
        :param timeout: timeout in seconds
        """
        dyndns_config = load_dyndns_config()
        if not dyndns_config.provider:
            logger.info("No dynamic dns provider found")
            return False

        hostname = dyndns_config.hostname
        if not hostname:
            logger.error("Missing hostname!")
            return False

        public_ip = self.get_public_ip()

        start_time = time()
        while time() - start_time < timeout:
            new_ip = self.get_dns_records(hostname=hostname)
            if new_ip and new_ip == public_ip:
                logger.info("IP address for '%s' updated to '%s'", hostname, public_ip)
                return True
            logger.info("Waiting for IP address update...")
            sleep(5)

        logger.error("Timeout waiting for IP address update!")
        return False
