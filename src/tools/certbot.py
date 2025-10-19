#!/usr/bin/env python3
import argparse
from dataclasses import asdict
import logging
import os
import subprocess
import sys
from time import time

from cryptography import x509
from dotenv import load_dotenv
from os import symlink
from pathlib import Path, PosixPath
from pydbus import SystemBus


load_dotenv()
load_dotenv("secrets.env")
sys.path.insert(0, os.getenv("PYTHONPATH"))

from constants import LOG_SC_CERTBOT
from monitor.config_helper import load_dyndns_config
from utils.dictionary import filter_keys


class Certbot:
    CERT_NAME = "arpi"

    def __init__(self, logger=None):
        self._logger = logger or logging.getLogger(LOG_SC_CERTBOT)

    def generate_certificate(self):
        """
        Generate certbot certificates with dynamic dns provider

        Returns: True if the certificate was generated, False otherwise
        """
        self._logger.info("Generating certbot certificate...")
        dyndns_config = load_dyndns_config()
        if not dyndns_config.provider:
            self._logger.info("No dynamic dns provider found")
            return False

        tmp_config = asdict(dyndns_config)
        filter_keys(tmp_config, ["password"])
        self._logger.info("Generate certificate with options: %s", tmp_config)

        try:
            # non interactive
            result = subprocess.run(
                [
                    "/usr/bin/certbot",
                    "certonly",
                    "--webroot",
                    "--webroot-path",
                    "/home/argus/webapplication",
                    "--agree-tos",
                    "--non-interactive",
                    "--quiet",
                    "--cert-name",
                    Certbot.CERT_NAME,
                    "--email",
                    dyndns_config.certbot_email,
                    "--post-hook",
                    "chmod -R 755 /etc/letsencrypt/live/ /etc/letsencrypt/archive/; systemctl restart mosquitto.service; systemctl restart nginx.service",
                    f"-d {dyndns_config.hostname}",
                ],
                capture_output=True,
                shell=False,
                check=False,
            )
            if result.returncode:
                self._logger.error("Certbot problem: %s", result.stderr.decode("utf-8"))
            else:
                self._logger.info("Certificate issued")
                return True
        except FileNotFoundError as error:
            self._logger.error("Missing file! %s", error)

        return False

    def renew_certificate(self):
        """
        Renew certbot certificates

        Returns: True if the certificate was renewed, False otherwise
        """
        self._logger.info("Renew certbot certificate")
        try:
            # non interactive
            result = subprocess.run(
                [
                    "/usr/bin/certbot",
                    "renew",
                    "--non-interactive",
                    "--quiet",
                    "--cert-name",
                    Certbot.CERT_NAME,
                ],
                capture_output=True,
                shell=False,
                check=False,
            )
            if result.returncode:
                self._logger.error("Certbot problem: %s", result.stderr.decode("utf-8"))
            else:
                self._logger.info("Certificate renewed")
                return True

        except FileNotFoundError as error:
            self._logger.error("Missing file! %s", error)

        return False

    def delete_certificate(self):
        """
        Replaces the certificate with letsencrypt
        """
        self._logger.info("Deleting the certificate")
        try:
            result = subprocess.run(
                [
                    "/usr/bin/certbot",
                    "delete",  # with revoke the certificate will be renewed later
                    "--non-interactive",
                    "--quiet",
                    "--cert-name",
                    Certbot.CERT_NAME,
                ],
                capture_output=True,
                shell=False,
                check=False,
            )

            if result.returncode:
                self._logger.error("Certbot problem: %s", result.stderr.decode("utf-8"))
            else:
                self._logger.info("Certificate deleted")

        except FileNotFoundError as error:
            self._logger.error("Missing file! %s", error)

    def _update_remote_configurations(self, enable=True, hostname=None):
        """
        Changes the symlinks using the certbot certificates instead of the self-signed
        """
        if enable:
            self._update_nginx_remote(hostname)
            self._enable_configuration(
                "/usr/local/nginx/conf/sites-enabled/remote.conf",
                "/usr/local/nginx/conf/sites-available/remote.conf",
            )
            self._enable_configuration(
                "/etc/mosquitto/conf.d/ssl.conf",
                "/etc/mosquitto/configs-available/ssl-certbot.conf",
            )
        else:
            self._disable_configuration("/usr/local/nginx/conf/sites-enabled/remote.conf")
            self._disable_configuration("/etc/mosquitto/conf.d/ssl.conf")

    def _update_nginx_remote(self, hostname):
        """
        Updates the server_name in the remote.conf file
        """
        self._logger.info("Updating remote configurations")
        remote_conf = Path("/usr/local/nginx/conf/sites-available/remote.conf")
        if remote_conf.is_file():
            with open(remote_conf, "r", encoding="utf-8") as file:
                lines = file.readlines()
                for i, line in enumerate(lines):
                    if "server_name" in line and "# managed by Certbot" in line:
                        lines[i] = f"    server_name {hostname}; # managed by Certbot\n"
                        break

            with open(remote_conf, "w", encoding="utf-8") as file:
                file.writelines(lines)

    def _enable_configuration(self, destination_config, source_config):
        self._logger.info("Updating configuration %s with %s", destination_config, source_config)
        if Path(destination_config).exists():
            os.remove(destination_config)

        symlink(source_config, destination_config)

    def _disable_configuration(self, destination_config):
        self._logger.info("Disabling configuration %s", destination_config)
        try:
            os.remove(destination_config)
        except FileNotFoundError:
            self._logger.error("File not found: %s", destination_config)

    def _restart_systemd_service(self, service_name):
        self._logger.info("Restarting '%s' with DBUS", service_name)
        bus = SystemBus()
        systemd = bus.get(".systemd1")
        systemd.RestartUnit(service_name, "fail")

    def check_domain_changed(self):
        """
        Check if the domain in the certificate is different from the current one

        Returns: True if the domain changed, False otherwise
        """
        self._logger.info("Checking domain change")

        cert_domain = None
        cert_path = Path(f"/etc/letsencrypt/live/{Certbot.CERT_NAME}/cert.pem")
        if cert_path.is_file():
            with open(cert_path, "rb") as cert_file:
                cert = x509.load_pem_x509_certificate(cert_file.read())
                cert_domain = cert.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)[
                    0
                ].value
                self._logger.info("Domain in certificate: %s", cert_domain)

        dyndns_config = load_dyndns_config()
        if dyndns_config and dyndns_config.hostname == cert_domain:
            self._logger.info("Domain not changed")
            return False

        self._logger.info("Domain changed: %s => %s", cert_domain, dyndns_config.hostname)
        return True

    def check_certificate_exists(self):
        """
        Check if the certificate exists

        Returns: True if the certificate exists, False otherwise
        """
        self._logger.info("Checking if certificate exists")
        full_certificate = Path(f"/etc/letsencrypt/live/{Certbot.CERT_NAME}/fullchain.pem")
        if full_certificate.is_file():
            self._logger.debug("Certificate exists")
            return True

        self._logger.info("Certificate does not exist")
        return False

    def get_certificate_timestamp(self):
        """
        Get the timestamp of the certificate

        Returns: The timestamp of the certificate
        """
        self._logger.info("Getting certificate timestamp")
        full_certificate = Path(f"/etc/letsencrypt/live/{Certbot.CERT_NAME}/fullchain.pem")
        if full_certificate.is_file():
            return full_certificate.stat().st_mtime

        return None

    def update_certificate(self):
        """
        Updates the certificate with letsencrypt

        Returns: True if the certificate was updated, False otherwise
        """
        # check if certificate already exists
        if self.check_certificate_exists():
            if self.check_domain_changed():
                self._logger.info("Certbot certificate already exists and domain changed")
                # replace certificate
                self.delete_certificate()
                self.generate_certificate()
            else:
                # if exists and domain not changed try to renew it
                self._logger.info("Certbot certificate exists and no change of domain")
                self.renew_certificate()
        else:
            # if certificate doesn't exist generate one
            self._logger.info("No certbot certificate found")
            self.generate_certificate()

            if self.check_certificate_exists():
                if Path("/usr/local/nginx/conf/sites-enabled/remote.conf").exists():
                    self._logger.info("Using certbot certificates")
                else:
                    self._logger.info("NGINX uses self-signed certificates")
                    self._update_remote_configurations(enable=True)
            else:
                self._logger.warning("No certbot certificate found")

        # check if full_certificate file changed in the past 10 mins
        if self.check_certificate_exists():
            if self.get_certificate_timestamp() > time() - 600:
                self._logger.info("Certificate renewed")
                self._restart_systemd_service("mosquitto.service")
                self._restart_systemd_service("nginx.service")
                return True
        else:
            self._logger.error("Certificate not renewed")
            self._update_remote_configurations(enable=False)
            self._restart_systemd_service("mosquitto.service")
            self._restart_systemd_service("nginx.service")

        return False


def main():
    """
    Main function to update certificates
    """
    parser = argparse.ArgumentParser(
        description="Update the system using certificates, or manage the certificate"
    )
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument("-g", "--generate", action="store_true", help="generate the certificate")
    group.add_argument("-r", "--renew", action="store_true", help="renew the certificate")
    group.add_argument("-d", "--delete", action="store_true", help="delete the certificate")
    parser.add_argument("-v", "--verbose", action="store_true", help="increase output verbosity")
    args = parser.parse_args()

    logging.basicConfig(
        format="%(asctime)-15s: %(message)s", level=logging.DEBUG if args.verbose else logging.INFO
    )

    certbot = Certbot(logging.getLogger("argus_certbot"))
    if args.generate:
        certbot.generate_certificate()
        return
    if args.renew:
        certbot.renew_certificate()
        return
    if args.delete:
        certbot.delete_certificate()
        return

    certbot.update_certificate()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
