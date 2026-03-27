import os
import tempfile
import click

from installer.helpers import SystemHelper, PackageHelper, ServiceHelper, SecurityHelper
from installer.installers.base import BaseInstaller, InstallerConfig

ETC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "etc")


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
        click.echo("   🔐 Configuring MQTT SSL certificates...")

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

        click.echo("   ✓ MQTT SSL certificates configured")

    def configure_mqtt(self):
        """Configure MQTT configuration files"""
        click.echo("   ⚙️ Configuring MQTT configuration files...")

        # Copy auth and logging configurations
        SystemHelper.run_command(f"cp {ETC_DIR}/mosquitto/auth.conf /etc/mosquitto/conf.d/")
        SystemHelper.run_command(f"cp {ETC_DIR}/mosquitto/logging.conf /etc/mosquitto/conf.d/")

        # Create configs-available directory and copy SSL configs
        SystemHelper.run_command("mkdir -p /etc/mosquitto/configs-available/")
        SystemHelper.run_command(
            f"cp {ETC_DIR}/mosquitto/ssl*.conf /etc/mosquitto/configs-available/"
        )

        # Create symlink for SSL configuration
        SystemHelper.run_command(
            "ln -sf /etc/mosquitto/configs-available/ssl-self-signed.conf /etc/mosquitto/conf.d/ssl.conf"
        )

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
                argus_password = self.secrets_manager.generate_secret('ARGUS_MQTT_PASSWORD')
                click.echo("   ✓ MQTT password created")

            argus_reader_password = self.secrets_manager.get_secret("ARGUS_READER_MQTT_PASSWORD")
            if argus_reader_password:
                click.echo("   ✓ Reader MQTT password already exists")
            else:
                argus_reader_password = self.secrets_manager.generate_secret('ARGUS_READER_MQTT_PASSWORD')
                click.echo("   ✓ Reader MQTT password created")
            
            # configure password for argus user
            SystemHelper.run_command(
                f"mosquitto_passwd -b -c /etc/mosquitto/.passwd argus \"{argus_password}\""
            )
            # configure password for argus_reader user
            SystemHelper.run_command(
                f"mosquitto_passwd -b /etc/mosquitto/.passwd argus_reader \"{argus_reader_password}\""
            )
            SecurityHelper.set_permissions("/etc/mosquitto/.passwd", "mosquitto:mosquitto", "700")
            click.echo(f"   ✓ MQTT authentication configured argus:{argus_password} argus_reader:{argus_reader_password}")
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
            "Mosquitto SSL configured": (
                os.path.exists("/etc/mosquitto/certs/arpi_app.crt")
                and os.path.exists("/etc/mosquitto/certs/arpi_app.key")
            ),
        }
