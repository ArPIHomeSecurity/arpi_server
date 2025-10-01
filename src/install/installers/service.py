import os
import subprocess
import click

from install.helpers import SystemHelper, ServiceHelper, SecurityHelper
from install.installers.base import BaseInstaller


class ServiceInstaller(BaseInstaller):
    """Installer for ArPI services and configurations"""

    def __init__(self, config: dict):
        super().__init__(config)
        self.user = config.get("user", "argus")
        self.db_password = config.get("db_password", "")
        self.salt = config.get("salt", "")
        self.secret = config.get("secret", "")
        self.mqtt_password = config.get("mqtt_password", "")

    def generate_service_secrets(self):
        """Generate secrets for ArPI services"""
        click.echo("   🔑 Generating service secrets...")

        secrets_generated = False

        if not self.db_password:
            self.db_password = SecurityHelper.generate_password()
            secrets_generated = True

        if not self.salt:
            self.salt = SecurityHelper.generate_password()
            secrets_generated = True

        if not self.secret:
            self.secret = SecurityHelper.generate_password()
            secrets_generated = True

        if not self.mqtt_password:
            self.mqtt_password = SecurityHelper.generate_password()
            secrets_generated = True

        if secrets_generated:
            click.echo("   ✓ Service secrets generated")
        else:
            click.echo("   ✓ Service secrets already exist")

    def create_service_directories(self):
        """Create ArPI service directories"""
        click.echo("   📁 Creating service directories...")

        # Create argus user if it doesn't exist
        try:
            SystemHelper.run_command(f"id {self.user}", capture=True)
            click.echo(f"   ✓ User '{self.user}' already exists")
        except subprocess.CalledProcessError:
            SystemHelper.run_command(f"useradd -m -s /bin/bash {self.user}")
            click.echo(f"   ✓ Created user '{self.user}'")

        # Create service directories
        directories = [
            f"/home/{self.user}/server",
            f"/home/{self.user}/webapplication",
            f"/run/{self.user}",
            f"/run/{self.user}",
        ]
        for directory in directories:
            SystemHelper.run_command(f"mkdir -p {directory}")

        SecurityHelper.set_file_permissions(
            f"/home/{self.user}", f"{self.user}:{self.user}", "755", recursive=True
        )
        SecurityHelper.set_file_permissions(
            f"/run/{self.user}", f"{self.user}:{self.user}", "755", recursive=True
        )

        # Create tmpfiles configuration
        tmpfiles_config = f"""# Type Path                     Mode    UID     GID     Age     Argument
d /run/{self.user} 0755 {self.user} {self.user}
"""
        SystemHelper.run_command("mkdir -p /usr/lib/tmpfiles.d")
        SystemHelper.write_file(f"/usr/lib/tmpfiles.d/{self.user}.conf", tmpfiles_config)

        click.echo("   ✓ Service directories created")

    def save_secrets_to_file(self):
        """Save generated secrets to file"""

        if os.path.exists(f"/home/{self.user}/server/secrets.env"):
            click.echo("   ✓ Secrets file already exists, skipping save")
            return

        click.echo("   💾 Saving secrets to file...")

        secrets_file = f"/home/{self.user}/server/secrets.env"
        SystemHelper.run_command(f"mkdir -p {os.path.dirname(secrets_file)}")

        secrets_content = f"""# Argus Service Secrets
# Generated on {datetime.now()}

SALT="{self.salt}"
SECRET="{self.secret}"
DB_PASSWORD="{self.db_password}"
ARGUS_MQTT_PASSWORD="{self.mqtt_password}"
"""

        SystemHelper.write_file(secrets_file, secrets_content)

        # Set proper ownership and permissions
        SystemHelper.run_command(f"chown {self.user}:{self.user} {secrets_file}")
        SecurityHelper.set_file_permissions(secrets_file, f"{self.user}:{self.user}", "600")

        click.echo("   ✓ Secrets saved to file")

    def setup_systemd_services(self):
        """Setup systemd services"""
        click.echo("   ⚙️ Setting up systemd services...")

        # Copy systemd service files
        SystemHelper.run_command("cp -r /tmp/server/etc/systemd/* /etc/systemd/system/")

        # Reload systemd daemon
        SystemHelper.run_command("systemctl daemon-reload")

        # Enable services
        services_to_enable = ["argus_server", "argus_monitor", "nginx"]
        for service in services_to_enable:
            ServiceHelper.enable_service(service)
            click.echo(f"   ✓ Enabled {service} service")

        click.echo("   ✓ Systemd services configured")

    def create_python_virtual_environment(self):
        """Create Python virtual environment"""
        click.echo("   🐍 Creating Python virtual environment...")

        venv_path = f"/home/{self.user}/.venvs"

        if not os.path.exists(venv_path):
            SystemHelper.run_command(f"mkdir -p {venv_path}")
            SecurityHelper.set_file_permissions(venv_path, f"{self.user}:{self.user}", "755")
            click.echo("   ✓ Python virtual environment created")
        else:
            click.echo("   ✓ Python virtual environment already exists")

    def install(self):
        """Install service components"""
        self.generate_service_secrets()
        self.create_service_directories()
        self.create_python_virtual_environment()
        self.save_secrets_to_file()
        self.setup_systemd_services()

    def is_installed(self) -> bool:
        """Check if services are installed"""
        return os.path.exists(f"/home/{self.user}/server/secrets.env")

    def get_status(self) -> dict:
        """Get service status"""
        return {
            "user_exists": os.path.exists(f"/home/{self.user}"),
            "secrets_file_exists": os.path.exists(f"/home/{self.user}/server/secrets.env"),
            "env_file_exists": os.path.exists(f"/home/{self.user}/server/.env"),
            "venv_exists": os.path.exists(f"/home/{self.user}/.venvs/server"),
            "service_directories_exist": os.path.exists(f"/run/{self.user}"),
            "argus_server_enabled": SystemHelper.is_service_enabled("argus_server"),
            "argus_monitor_enabled": SystemHelper.is_service_enabled("argus_monitor"),
            "nginx_enabled": SystemHelper.is_service_enabled("nginx"),
        }
