import os

import click

from installer.helpers import PackageHelper, SecurityHelper, ServiceHelper, SystemHelper
from installer.installers.base import BaseInstaller, InstallerConfig

# source etc directory for configuration files
ETC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "etc")

# must stay in sync with DEFAULT_MQTT_CA_CERT in monitor.config.models
CLIENT_CA_DIR = "/home/argus/.local/etc/arpi-server/certs"
CLIENT_CA_CERT = f"{CLIENT_CA_DIR}/arpi_ca.crt"


class MqttInstaller(BaseInstaller):
    """Installer for MQTT broker"""

    def __init__(self, config: InstallerConfig):
        super().__init__(config)
        self.user = config.user
        self.secrets_manager = config.secrets_manager

    def setup_mosquitto_repository(self):
        """Setup Mosquitto repository for installation"""
        click.echo("   📡 Setting up Mosquitto repository...")

        # Check if repository is already configured
        sources_file = "/etc/apt/sources.list.d/mosquitto.list"
        if os.path.exists(sources_file):
            with open(sources_file, "r") as f:
                if "repo.mosquitto.org" in f.read():
                    click.echo("   ✓ Mosquitto repository already configured")
                    return

        # download the repository key
        SystemHelper.run_command(
            "wget https://repo.mosquitto.org/debian/mosquitto-repo.gpg -O /etc/apt/keyrings/mosquitto-repo.gpg",
        )

        codename = SystemHelper.run_command("lsb_release -cs", capture=True).stdout.strip()

        # Add repository to sources list
        SystemHelper.write_file(
            sources_file,
            f"deb [signed-by=/etc/apt/keyrings/mosquitto-repo.gpg] https://repo.mosquitto.org/debian {codename} main\n",
        )

        click.echo("   ✓ Mosquitto repository configured")

    def install_mosquitto(self):
        """Install Mosquitto MQTT broker"""
        click.echo("   🦟 Installing Mosquitto MQTT broker...")

        # Setup repository first
        self.setup_mosquitto_repository()

        # Update package list
        PackageHelper.update_package_cache()

        # Install Mosquitto
        if PackageHelper.install_packages(["mosquitto"], "Mosquitto MQTT broker"):
            ServiceHelper.enable_service("mosquitto")

        # Ensure service is running
        if not ServiceHelper.is_service_running("mosquitto"):
            ServiceHelper.start_service("mosquitto")

    def install_client_ca_certificate(self):
        """Install the CA certificate the MQTT clients verify the broker with"""
        click.echo("   🔐 Install MQTT CA certificate...")

        # The clients connect through nginx, which presents the self signed certificate
        # of the application, so they need a readable copy of the issuing CA.
        SystemHelper.run_command(f"mkdir -p {CLIENT_CA_DIR}")
        SystemHelper.run_command(f"cp {ETC_DIR}/nginx/ssl/arpi_ca.crt {CLIENT_CA_CERT}")
        SecurityHelper.set_permissions(CLIENT_CA_CERT, "argus:argus", "640")
        click.echo(f"   ✓ MQTT CA certificate installed for the monitor at {CLIENT_CA_CERT}")

    def remove_legacy_ssl_configuration(self):
        """Remove the TCP TLS listener of the previous versions"""
        # nginx owns port 8883 now, an old listener would keep it occupied
        SystemHelper.run_command("rm -f /etc/mosquitto/conf.d/ssl.conf")
        SystemHelper.run_command("rm -f /etc/mosquitto/configs-available/ssl-self-signed.conf")
        SystemHelper.run_command("rm -f /etc/mosquitto/configs-available/ssl-certbot.conf")
        SystemHelper.run_command("rm -fr /etc/mosquitto/certs")
        click.echo("   ✓ Legacy MQTT SSL configuration removed")

    def configure_mqtt(self):
        """Configure MQTT configuration files"""
        click.echo("   ⚙️ Configuring MQTT configuration files...")

        self.remove_legacy_ssl_configuration()

        # Copy listener, auth and logging configurations
        SystemHelper.run_command(f"cp {ETC_DIR}/mosquitto/listener.conf /etc/mosquitto/conf.d/")
        SystemHelper.run_command(f"cp {ETC_DIR}/mosquitto/auth.conf /etc/mosquitto/conf.d/")
        SystemHelper.run_command(f"cp {ETC_DIR}/mosquitto/logging.conf /etc/mosquitto/conf.d/")

        SystemHelper.run_command(f"cp {ETC_DIR}/mosquitto/acl.conf /etc/mosquitto/acl.conf")
        SecurityHelper.set_permissions("/etc/mosquitto/acl.conf", "mosquitto:mosquitto", "600")
        click.echo("   ✓ MQTT access control list installed")

        SecurityHelper.set_permissions(
            "/etc/mosquitto/conf.d/", f"mosquitto:{self.user}", "774", recursive=True
        )

        # the drop-in creates the socket directory and makes the socket readable by nginx
        SystemHelper.run_command("mkdir -p /etc/systemd/system/mosquitto.service.d/")
        SystemHelper.run_command(
            f"cp {ETC_DIR}/systemd/mosquitto.service.d/arpi.conf "
            "/etc/systemd/system/mosquitto.service.d/"
        )
        SystemHelper.run_command("systemctl daemon-reload")

        click.echo("   ✓ MQTT configuration files setup complete")

    def setup_mqtt_authentication(self):
        """Configure MQTT authentication"""
        click.echo("   🔐 Configuring MQTT authentication...")

        try:
            click.echo("   🔐 Checking MQTT secrets...")
            argus_password = self.secrets_manager.get_secret("ARGUS_MQTT_PASSWORD")
            if argus_password:
                click.echo("   ✓ MQTT password exists")
            else:
                argus_password = self.secrets_manager.generate_secret("ARGUS_MQTT_PASSWORD")
                click.echo("   ✓ MQTT password created")

            argus_reader_password = self.secrets_manager.get_secret("ARGUS_READER_MQTT_PASSWORD")
            if argus_reader_password:
                click.echo("   ✓ Reader MQTT password already exists")
            else:
                argus_reader_password = self.secrets_manager.generate_secret(
                    "ARGUS_READER_MQTT_PASSWORD"
                )
                click.echo("   ✓ Reader MQTT password created")

            argus_control_password = self.secrets_manager.get_secret("ARGUS_CONTROL_MQTT_PASSWORD")
            if argus_control_password:
                click.echo("   ✓ Control MQTT password already exists")
            else:
                argus_control_password = self.secrets_manager.generate_secret(
                    "ARGUS_CONTROL_MQTT_PASSWORD"
                )
                click.echo("   ✓ Control MQTT password created")

            # configure password for argus user
            create_flag = "-c" if not os.path.exists("/etc/mosquitto/.passwd") else ""
            SystemHelper.run_command(
                f'mosquitto_passwd -b {create_flag} /etc/mosquitto/.passwd argus "{argus_password}"'
            )
            # configure password for argus_reader user
            SystemHelper.run_command(
                f'mosquitto_passwd -b /etc/mosquitto/.passwd argus_reader "{argus_reader_password}"'
            )
            SystemHelper.run_command(
                f'mosquitto_passwd -b /etc/mosquitto/.passwd argus_control "{argus_control_password}"'
            )
            SecurityHelper.set_permissions("/etc/mosquitto/.passwd", "mosquitto:mosquitto", "700")
            # the passwords must not end up in the install log, the reader and control passwords
            # can be looked up by an administrator in the MQTT configuration of the web application
            click.echo(
                "   ✓ MQTT authentication configured for argus, argus_reader and argus_control"
            )
        except Exception as e:
            click.echo(f"    ⚠️ WARNING: MQTT authentication setup failed: {e}")
            self.warnings.append(f"MQTT authentication setup failed: {e}")

    def restart_service(self):
        """Restart Mosquitto service"""
        click.echo("   🔄 Restarting Mosquitto service...")
        ServiceHelper.restart_service("mosquitto")
        click.echo("   ✓ Mosquitto service restarted")

    def install(self):
        """Install MQTT components"""
        self.install_mosquitto()
        self.install_client_ca_certificate()
        self.configure_mqtt()
        self.setup_mqtt_authentication()
        self.restart_service()

    def get_status(self) -> dict:
        """Get MQTT status"""
        return {
            "Mosquitto installed": PackageHelper.is_package_installed("mosquitto"),
            "Mosquitto running": ServiceHelper.is_service_running("mosquitto"),
            "Mosquitto enabled": ServiceHelper.is_service_enabled("mosquitto"),
            "Mosquitto authentication configured": os.path.exists("/etc/mosquitto/.passwd"),
            "Mosquitto ACL configured": os.path.exists("/etc/mosquitto/acl.conf"),
            "MQTT CA certificate for the monitor": os.path.exists(CLIENT_CA_CERT),
            "Mosquitto socket listener configured": os.path.exists(
                "/etc/mosquitto/conf.d/listener.conf"
            ),
            "Mosquitto socket available": os.path.exists("/run/mosquitto/mosquitto.sock"),
        }
