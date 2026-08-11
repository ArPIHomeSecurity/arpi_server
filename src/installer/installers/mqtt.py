import os

import click

from installer.helpers import PackageHelper, SecurityHelper, ServiceHelper, SystemHelper
from installer.installers.base import BaseInstaller, InstallerConfig

ETC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "etc")

# must stay in sync with DEFAULT_MQTT_CA_CERT in monitor.config.models
CLIENT_CA_DIR = "/etc/arpi-server/certs"
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

    def configure_mqtt_ssl_certificates(self):
        """Configure SSL certificates for MQTT"""
        click.echo("   🔐 Install MQTT SSL self-signed certificates...")

        # Create certs directory and copy certificates
        SystemHelper.run_command("mkdir -p /etc/mosquitto/certs")

        # Copy dhparam file
        SystemHelper.run_command(f"cp {ETC_DIR}/arpi_dhparam.pem /etc/mosquitto/certs/")
        click.echo("   ✓ Copied dhparam file")

        # Copy SSL certificates from nginx config
        ssl_files = [
            f"{ETC_DIR}/nginx/ssl/arpi_app.crt",
            f"{ETC_DIR}/nginx/ssl/arpi_app.key",
            f"{ETC_DIR}/nginx/ssl/arpi_ca.crt",
        ]

        for ssl_file in ssl_files:
            SystemHelper.run_command(f"cp {ssl_file} /etc/mosquitto/certs/")

        # Set proper ownership for certs directory
        SecurityHelper.set_permissions(
            "/etc/mosquitto/certs", "mosquitto:mosquitto", "700", recursive=True
        )

        # The monitor verifies the broker certificate against the CA, so it needs its own
        # readable copy: /etc/mosquitto/certs is only accessible by the mosquitto user.
        SystemHelper.run_command(f"mkdir -p {CLIENT_CA_DIR}")
        SystemHelper.run_command(f"cp {ETC_DIR}/nginx/ssl/arpi_ca.crt {CLIENT_CA_CERT}")
        SecurityHelper.set_permissions(CLIENT_CA_CERT, f"root:{self.user}", "640")
        click.echo(f"   ✓ MQTT CA certificate installed for the monitor at {CLIENT_CA_CERT}")

        click.echo("   ✓ MQTT SSL self-signed certificates installed")

    def configure_mqtt(self):
        """Configure MQTT configuration files"""
        click.echo("   ⚙️ Configuring MQTT configuration files...")

        # Copy auth and logging configurations
        SystemHelper.run_command(f"cp {ETC_DIR}/mosquitto/auth.conf /etc/mosquitto/conf.d/")
        SystemHelper.run_command(f"cp {ETC_DIR}/mosquitto/logging.conf /etc/mosquitto/conf.d/")

        SystemHelper.run_command(f"cp {ETC_DIR}/mosquitto/acl.conf /etc/mosquitto/acl.conf")
        SecurityHelper.set_permissions("/etc/mosquitto/acl.conf", "mosquitto:mosquitto", "600")
        click.echo("   ✓ MQTT access control list installed")

        # Create configs-available directory and copy SSL configs
        SystemHelper.run_command("mkdir -p /etc/mosquitto/configs-available/")
        SystemHelper.run_command(
            f"cp {ETC_DIR}/mosquitto/ssl*.conf /etc/mosquitto/configs-available/"
        )

        if os.path.exists("/etc/mosquitto/conf.d/ssl.conf"):
            click.echo("   ✓ MQTT SSL configuration already exists")
        else:
            # Create symlink for SSL configuration
            SystemHelper.run_command(
                "ln -sf /etc/mosquitto/configs-available/ssl-self-signed.conf /etc/mosquitto/conf.d/ssl.conf"
            )
            click.echo("   ✓ MQTT SSL configuration enabled")

        SecurityHelper.set_permissions(
            "/etc/mosquitto/conf.d/", f"mosquitto:{self.user}", "774", recursive=True
        )

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
        self.configure_mqtt_ssl_certificates()
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
            "Mosquitto SSL configured": (
                os.path.exists("/etc/mosquitto/certs/arpi_app.crt")
                and os.path.exists("/etc/mosquitto/certs/arpi_app.key")
            ),
        }
