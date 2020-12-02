#!/usr/bin/env python
"""
Created on 2018. ápr. 16.

@author: gkovacs
"""

import json
import logging
import subprocess
from copy import copy
from os import symlink
from pathlib import Path, PosixPath

from pydbus import SystemBus

from tools.dictionary import filter_keys
from models import Option, db
from monitoring.constants import LOG_SC_CERTBOT


class Certbot:

    def __init__(self, logger=None):
        self._logger = logger if logger else logging.getLogger(LOG_SC_CERTBOT)

    def generate_certificate(self):
        """
        Generate certbot certificates with dynamic dsn provider
        """
        self._logger.info("Generating certbot certificate")
        noip_config = Option.query.filter_by(name="network", section="dyndns").first()
        if noip_config:
            noip_config = json.loads(noip_config.value)
        else:
            self._logger.error("Missing dyndns settings!")
            return

        tmp_config = copy(noip_config)
        filter_keys(tmp_config, ['password'])
        self._logger.info("Generate certificate with options: %s", tmp_config)

        try:
            # non interactive
            subprocess.call(
                [
                    "/usr/bin/certbot",
                    "certonly",
                    "--webroot",
                    "--webroot-path",
                    "/home/argus/server/webapplication",
                    "--agree-tos",
                    "--non-interactive",
                    "--cert-name", "arpi",
                    "--email",
                    noip_config["username"],
                    "-d %s" % noip_config["hostname"]
                ]
            )
        except FileNotFoundError as error:
            self._logger.error("Missing file! %s", error)

    def swith2certbot(self):
        """
        Changes the symlink for nginx using the certbot certificates instead of the self-signed
        """
        self._logger.info("Switch nginx to use certbot certificates")
        Path("/usr/local/nginx/conf/snippets/certificates.conf").unlink()
        symlink("/usr/local/nginx/conf/snippets/certbot-signed.conf", "/usr/local/nginx/conf/snippets/certificates.conf")

    def restart_nginx(self):
        """
        Restarts the nginx-1.12.2 service with DBUS
        """
        self._logger.info("Restarting NGINX")
        bus = SystemBus()
        systemd = bus.get(".systemd1")
        systemd.RestartUnit("nginx.service", "fail")

    def update_certificates(self):
        full_certificate = Path("/etc/letsencrypt/live/arpi/fullchain.pem")
        if not full_certificate.is_file():
            self._logger.info("No certbot certificate found")
            self.generate_certificate()

        if full_certificate.is_file():
            if Path("/usr/local/nginx/conf/snippets/certificates.conf").resolve() == PosixPath("/usr/local/nginx/conf/snippets/self-signed.conf"):
                self._logger.info("NGINX uses self-signed certificates")
                self.swith2certbot()
                self.restart_nginx()
            elif Path("/usr/local/nginx/conf/snippets/certificates.conf").resolve() == PosixPath("/usr/local/nginx/conf/snippets/certbot-signed.conf"):
                self._logger.info("Using certbot certificates")
            else:
                self._logger.info("Error detecting certificate configuration")
                return
        else:
            self._logger.info("No certbot certificate found")


if __name__ == "__main__":
    logging.basicConfig(format='%(asctime)-15s %(message)s', level=logging.INFO)

    Certbot(logging.getLogger("argus_certbot")).update_certificates()
