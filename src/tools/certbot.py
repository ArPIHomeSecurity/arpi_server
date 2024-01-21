#!/usr/bin/env python3
import argparse
import json
import logging
import os
import subprocess
import sys

from cryptography import x509
from dataclasses import dataclass, asdict
from dotenv import load_dotenv
from os import symlink
from pathlib import Path, PosixPath
from pydbus import SystemBus

load_dotenv()
load_dotenv("secrets.env")
sys.path.insert(0, os.getenv("PYTHONPATH"))

from models import Option
from constants import LOG_SC_CERTBOT
from monitor.database import Session
from tools.dictionary import filter_keys


@dataclass
class NoIPConfig:
    username: str
    password: str
    hostname: str
    provider: str
    restrict_host: str


class Certbot:
    CERT_NAME = "arpi"

    def __init__(self, logger=None):
        self._logger = logger or logging.getLogger(LOG_SC_CERTBOT)
        self._db_session = Session()

    def _generate_certificate(self):
        """
        Generate certbot certificates with dynamic dns provider

        Returns: True if the certificate was generated, False otherwise
        """
        self._logger.info("Generating certbot certificate")
        noip_config = self._load_config()
        if noip_config is None:
            return False

        tmp_config = asdict(noip_config)
        filter_keys(tmp_config, ["password"])
        self._logger.info("Generate certificate with options: %s", tmp_config)

        try:
            # non interactive
            results = subprocess.run(
                [
                    "/usr/bin/certbot",
                    "certonly",
                    "--webroot",
                    "--webroot-path", "/home/argus/webapplication",
                    "--agree-tos",
                    "--non-interactive",
                    "--quiet",
                    "--cert-name", Certbot.CERT_NAME,
                    "--email",
                    noip_config.username,
                    f'-d {noip_config.hostname}',
                ],
                capture_output=True,
            )
            if results.returncode:
                self._logger.error("Certbot problem: %s", results.stderr.decode("utf-8"))
            else:
                self._logger.info("Certificate generated")
                return True
        except FileNotFoundError as error:
            self._logger.error("Missing file! %s", error)

        return False

    def _load_config(self) -> NoIPConfig:
        noip_data = self._db_session.query(Option).filter_by(name="network", section="dyndns").first()
        if noip_data:
            noip_config = json.loads(noip_data.value)
            return NoIPConfig(**noip_config)
        else:
            self._logger.error("Missing dyndns settings!")

    def _renew_certificate(self):
        """
        Renew certbot certificates

        Returns: True if the certificate was renewed, False otherwise
        """
        self._logger.info("Renew certbot certificate")
        try:
            # non interactive
            results = subprocess.run(
                [
                    "/usr/bin/certbot",
                    "renew",
                    "--non-interactive",
                    "--quiet",
                    "--cert-name", Certbot.CERT_NAME
                ],
                capture_output=True,
            )
            if results.returncode:
                self._logger.error("Certbot problem: %s", results.stderr.decode("utf-8"))
            else:
                self._logger.info("Certificate renewed")
                return True

        except FileNotFoundError as error:
            self._logger.error("Missing file! %s", error)

        return False

    def _switch2certbot(self):
        """
        Changes the symlinks using the certbot certificates instead of the self-signed
        """
        self._replace_configuration(
            "/usr/local/nginx/conf/snippets/certificates.conf",
            "/usr/local/nginx/conf/snippets/certbot-signed.conf",
        )
        self._replace_configuration(
            "/etc/mosquitto/conf.d/ssl.conf",
            "/etc/mosquitto/configs-available/ssl-certbot.conf",
        )

    def _replace_configuration(self, used_config, new_config):
        self._logger.info("Updating configuration %s with %s", used_config, new_config)
        Path(used_config).unlink()
        symlink(new_config, used_config)

    def _restart_systemd_sevice(self, service_name):
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
                cert_domain = cert.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)[0].value
                self._logger.debug("Domain in certificate: %s", cert_domain)

        noip_config = self._load_config()
        if noip_config and noip_config.hostname == cert_domain:
            self._logger.info("Domain not changed")
            return False

        self._logger.info("Domain changed: %s => %s", cert_domain, noip_config.hostname)
        return True
    
    def _delete_certificate(self):
        """
        Replaces the certificate with letsencrypt
        """
        self._logger.info("Replacing certificate")
        subprocess.run(
            [
                "/usr/bin/certbot",
                "delete",
                "--cert-name", Certbot.CERT_NAME
            ],
            capture_output=True,
        )

    def update_certificate(self):
        """
        Updates the certificate with letsencrypt
        """
        # check if certificate already exists
        full_certificate = Path(f"/etc/letsencrypt/live/{Certbot.CERT_NAME}/fullchain.pem")
        if full_certificate.is_file():
            if self.check_domain_changed():
                self._logger.info("Certbot certificate already exists and domain changed")
                # replace certificate
                self._delete_certificate()
                self._generate_certificate()
            else:
                # if exists and domain not changed try to renew it
                self._logger.info("Certbot certificate exists and no change of domain")
                self._renew_certificate()

            self._restart_systemd_sevice("mosquitto.service")
            self._restart_systemd_sevice("nginx.service")
        else:
            # if certificate doesn't exist generate one
            self._logger.info("No certbot certificate found")
            self._generate_certificate()

            if full_certificate.is_file():
                if Path("/usr/local/nginx/conf/snippets/certificates.conf").resolve() == PosixPath(
                    "/usr/local/nginx/conf/snippets/self-signed.conf"
                ):
                    self._logger.info("NGINX uses self-signed certificates")
                    self._switch2certbot()
                    self._restart_systemd_sevice("mosquitto.service")
                    self._restart_systemd_sevice("nginx.service")
                elif Path("/usr/local/nginx/conf/snippets/certificates.conf").resolve() == PosixPath(
                    "/usr/local/nginx/conf/snippets/certbot-signed.conf"
                ):
                    self._logger.info("Using certbot certificates")
                else:
                    self._logger.error("Failed detecting certificate configuration")
            else:
                self._logger.error("No certbot certificate found")


def main():
    parser = argparse.ArgumentParser(description="Update certificates with certbot")
    parser.add_argument("-v", "--verbose", action="store_true", help="increase output verbosity")
    args = parser.parse_args()

    logging.basicConfig(format="%(asctime)-15s: %(message)s", level=logging.DEBUG if args.verbose else logging.INFO)

    Certbot(logging.getLogger("argus_certbot")).update_certificate()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass

