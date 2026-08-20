#!/usr/bin/env python3
import logging
import os
import subprocess
from dataclasses import asdict
from pathlib import Path
from time import time

from cryptography import x509

from monitor.config.helper import save_config
from monitor.config.models import (
    DEFAULT_MQTT_CA_CERT,
    DyndnsConfig,
    MQTTConfigInternalPublish,
    MQTTConfigExternalPublish,
    MQTTConnection,
)
from utils.constants import LOG_SC_CERTBOT
from utils.dictionary import filter_keys

logger = logging.getLogger(LOG_SC_CERTBOT)


NGINX_CONF_DIR = "/usr/local/nginx/conf"
NGINX_REMOTE_AVAILABLE = f"{NGINX_CONF_DIR}/sites-available/remote.conf"
NGINX_REMOTE_CONF = f"{NGINX_CONF_DIR}/sites-enabled/remote.conf"
NGINX_MQTT_SELF_SIGNED_AVAILABLE = f"{NGINX_CONF_DIR}/stream-available/mqtt-self-signed.conf"
NGINX_MQTT_CERTBOT_AVAILABLE = f"{NGINX_CONF_DIR}/stream-available/mqtt-certbot.conf"
NGINX_MQTT_CONF = f"{NGINX_CONF_DIR}/stream-enabled/mqtt.conf"


class Certbot:
    CERT_NAME = "arpi"

    def generate_certificate(self):
        """
        Generate certbot certificates with dynamic dns provider

        Returns: True if the certificate was generated, False otherwise
        """
        logger.info("Generating certbot certificate...")
        dyndns_config = DyndnsConfig.load_config()
        if not dyndns_config.provider:
            logger.info("No dynamic dns provider found")
            return False

        tmp_config = asdict(dyndns_config)
        filter_keys(tmp_config, ["password"])
        logger.info("Generate certificate with options: %s", tmp_config)

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
                    "chmod -R 755 /etc/letsencrypt/live/ /etc/letsencrypt/archive/; systemctl reload nginx.service",
                    f"-d {dyndns_config.hostname}",
                ],
                capture_output=True,
                shell=False,
                check=False,
            )
            if result.returncode:
                logger.error("Certbot problem: %s", result.stderr.decode("utf-8"))
            else:
                logger.info("Certificate issued")
                return True
        except FileNotFoundError as error:
            logger.error("Missing file! %s", error)

        return False

    def renew_certificate(self):
        """
        Renew certbot certificates

        Returns: True if the certificate was renewed, False otherwise
        """
        logger.info("Renew certbot certificate")
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
                    "--deploy-hook",
                    "systemctl reload nginx.service",
                ],
                capture_output=True,
                shell=False,
                check=False,
            )
            if result.returncode:
                logger.error("Certbot problem: %s", result.stderr.decode("utf-8"))
            else:
                logger.info("Certificate renewed")
                return True

        except FileNotFoundError as error:
            logger.error("Missing file! %s", error)

        return False

    def delete_certificate(self):
        """
        Replaces the certificate with letsencrypt
        """
        logger.info("Deleting the certificate")
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
                logger.error("Certbot problem: %s", result.stderr.decode("utf-8"))
            else:
                logger.info("Certificate deleted")

        except FileNotFoundError as error:
            logger.error("Missing file! %s", error)

    def _update_remote_configurations(self, enable=True):
        """
        Changes the symlinks using the certbot certificates instead of the self-signed
        """
        if enable:
            self._update_nginx_remote()
            self._enable_configuration(
                NGINX_REMOTE_CONF,
                NGINX_REMOTE_AVAILABLE,
            )
            self._enable_configuration(
                NGINX_MQTT_CONF,
                NGINX_MQTT_CERTBOT_AVAILABLE,
            )
            self._set_mqtt_ca_certificate(None)
        else:
            self._disable_configuration(NGINX_REMOTE_CONF)
            self._enable_configuration(
                NGINX_MQTT_CONF,
                NGINX_MQTT_SELF_SIGNED_AVAILABLE,
            )
            self._set_mqtt_ca_certificate(DEFAULT_MQTT_CA_CERT)

    def _set_mqtt_ca_certificate(self, ca_certificate):
        """
        Keep the MQTT client CA configuration aligned with nginx's certificate.
        """
        dyndns_config = DyndnsConfig.load_config()

        mqtt_connection = MQTTConnection().load_config()

        if mqtt_connection.external:
            mqtt_config = MQTTConfigExternalPublish.load_config()
            mqtt_config.ca_certs = ca_certificate
            save_config(
                MQTTConfigExternalPublish.OPTION_NAME,
                MQTTConfigExternalPublish.SECTION_NAME,
                asdict(mqtt_config),
            )
        else:
            mqtt_config = MQTTConfigInternalPublish.load_config()
            mqtt_config.hostname = dyndns_config.hostname
            mqtt_config.ca_certs = ca_certificate
            save_config(
                MQTTConfigInternalPublish.OPTION_NAME,
                MQTTConfigInternalPublish.SECTION_NAME,
                asdict(mqtt_config),
            )

    def _update_nginx_remote(self):
        """
        Updates the server_name in the remote.conf file
        """
        dyndns_config = DyndnsConfig.load_config()
        if not dyndns_config:
            logger.info("Missing dynamic dns configuration")
            return

        logger.info("Updating remote configurations for hostname %s", dyndns_config.hostname)
        # it is linked to NGINX_REMOTE_AVAILABLE
        remote_conf = os.path.expanduser("~/.local/etc/arpi-server/remote.conf")
        if os.path.isfile(remote_conf):
            with open(remote_conf, "r", encoding="utf-8") as file:
                lines = file.readlines()
                for i, line in enumerate(lines):
                    if "server_name" in line and "# managed by Certbot" in line:
                        lines[i] = (
                            f"    server_name {dyndns_config.hostname}; # managed by Certbot\n"
                        )
                        break

            with open(remote_conf, "w", encoding="utf-8") as file:
                file.writelines(lines)

    def _enable_configuration(self, destination_config, source_config):
        """
        Enables a configuration by creating a symlink from source_config to destination_config.
        """
        logger.info("Updating configuration %s with %s", destination_config, source_config)
        if Path(destination_config).exists():
            try:
                subprocess.run(["sudo", "rm", destination_config], check=True)
            except subprocess.CalledProcessError as error:
                logger.error("Error removing file %s: %s", destination_config, error)

        os.symlink(source_config, destination_config)

    def _disable_configuration(self, destination_config):
        """
        Disables a configuration by removing the symlink at destination_config.
        """
        logger.info("Disabling configuration %s", destination_config)
        try:
            subprocess.run(["sudo", "rm", destination_config], check=True)
        except subprocess.CalledProcessError as error:
            logger.error("Error removing file %s: %s", destination_config, error)

    def _reload_systemd_service(self, service_name):
        logger.info("Reloading '%s' with systemctl", service_name)
        try:
            subprocess.run(["sudo", "systemctl", "reload", service_name], check=True)
        except subprocess.CalledProcessError as error:
            logger.error("Failed to reload %s: %s", service_name, error)

    def check_domain_changed(self):
        """
        Check if the domain in the certificate is different from the current one

        Returns: True if the domain changed, False otherwise
        """
        logger.info("Checking domain change")

        cert_domain = None
        cert_path = Path(f"/etc/letsencrypt/live/{Certbot.CERT_NAME}/cert.pem")
        if cert_path.is_file():
            with open(cert_path, "rb") as cert_file:
                cert = x509.load_pem_x509_certificate(cert_file.read())
                cert_domain = cert.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)[
                    0
                ].value
                logger.info("Domain in certificate: %s", cert_domain)

        dyndns_config = DyndnsConfig.load_config()
        if dyndns_config and dyndns_config.hostname == cert_domain:
            logger.info("Domain not changed")
            return False

        logger.info("Domain changed: %s => %s", cert_domain, dyndns_config.hostname)
        return True

    def check_certificate_exists(self):
        """
        Check if the certificate exists

        Returns: True if the certificate exists, False otherwise
        """
        logger.info("Checking if certificate exists")
        full_certificate = Path(f"/etc/letsencrypt/live/{Certbot.CERT_NAME}/fullchain.pem")
        if full_certificate.is_file():
            logger.debug("Certificate exists")
            return True

        logger.info("Certificate does not exist")
        return False

    def verify_configuration(self, fix=True):
        """
        Verify that the system configuration matches the state stored in the database
        and fix it if they diverged (eg. certificate changed while the backend was down).

        Returns: True if the configuration was changed, False otherwise
        """
        logger.info("Verifying certificate configuration")
        dyndns_config = DyndnsConfig.load_config()
        use_certbot = bool(dyndns_config.provider) and self.check_certificate_exists()

        nginx_enabled = Path(NGINX_REMOTE_CONF).exists()
        mqtt_stream = Path(NGINX_MQTT_CONF)
        mqtt_certbot_enabled = (
            mqtt_stream.is_symlink() and os.readlink(mqtt_stream) == NGINX_MQTT_CERTBOT_AVAILABLE
        )

        logger.info(
            "Remote certificate configuration: expected=%s, nginx=%s, mqtt=%s",
            use_certbot,
            nginx_enabled,
            mqtt_certbot_enabled,
        )
        if all(state == use_certbot for state in (nginx_enabled, mqtt_certbot_enabled)):
            logger.info("Configuration is consistent (certbot=%s)", use_certbot)
            return False

        if not fix:
            return False

        logger.warning("Inconsistent configuration, switching certbot to: %s", use_certbot)
        self._update_remote_configurations(enable=use_certbot)
        self._reload_systemd_service("nginx.service")
        return True

    def get_certificate_timestamp(self):
        """
        Get the timestamp of the certificate

        Returns: The timestamp of the certificate
        """
        logger.info("Getting certificate timestamp")
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
                logger.info("Certbot certificate already exists and domain changed")
                # replace certificate
                self.delete_certificate()
                self.generate_certificate()
            else:
                # if exists and domain not changed try to renew it
                logger.info("Certbot certificate exists and no change of domain")
                self.renew_certificate()
        else:
            # if certificate doesn't exist generate one
            logger.info("No certbot certificate found")
            self.generate_certificate()

            if self.check_certificate_exists():
                if Path(NGINX_REMOTE_CONF).exists():
                    logger.info("Using certbot certificates")
                else:
                    logger.info("NGINX uses self-signed certificates")
                    self._update_remote_configurations(enable=True)
            else:
                logger.warning("No certbot certificate found")

        # check if full_certificate file changed in the past 10 mins
        if self.check_certificate_exists():
            if self.get_certificate_timestamp() > time() - 600:
                logger.info("Certificate renewed")
                self._reload_systemd_service("nginx.service")
                return True
        else:
            logger.error("Certificate not renewed")
            self._update_remote_configurations(enable=False)
            self._reload_systemd_service("nginx.service")

        return False
