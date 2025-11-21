import os
import subprocess
import click

from installer.helpers import SystemHelper, ServiceHelper, SecurityHelper
from installer.installers.base import BaseInstaller


class ServerInstaller(BaseInstaller):
    """Installer for ArPI services and configurations"""

    def __init__(self, config: dict):
        super().__init__(config)
        self.user = config["user"]
        self.secrets_manager = config.get("secrets_manager")
        self.install_source = config["install_source"]
        self.data_set_name = config["data_set_name"]
        self.verbose = config.get("verbose", False)


    def create_service_directories(self):
        """Create ArPI service directories"""
        click.echo("   📁 Creating service directories...")

        # Create argus user if it doesn't exist
        if not self.check_user_exists():
            SystemHelper.run_command(f"useradd -m -s /bin/zsh {self.user}")
            click.echo(f"   ✓ User '{self.user}' created")
        else:
            click.echo(f"   ✓ User '{self.user}' already exists")

        # Create service directories
        directories = [
            f"/home/{self.user}/server",
            f"/home/{self.user}/webapplication",
            f"/run/{self.user}",
        ]
        for directory in directories:
            SystemHelper.run_command(f"mkdir -p {directory}")

        SecurityHelper.set_permissions(
            f"/home/{self.user}", f"{self.user}:{self.user}", "755", recursive=True
        )
        SecurityHelper.set_permissions(
            f"/run/{self.user}", f"{self.user}:{self.user}", "755", recursive=True
        )
        click.echo("   ✓ Service directories created")

        if not self.check_tmpfiles_configured():
            click.echo("   ⚙️ Configuring tmpfiles...")
            # Create tmpfiles configuration
            tmpfiles_config = f"""# Type Path                     Mode    UID     GID     Age     Argument
d /run/{self.user} 0755 {self.user} {self.user}

"""
            SystemHelper.run_command("mkdir -p /usr/lib/tmpfiles.d")
            SystemHelper.write_file(f"/usr/lib/tmpfiles.d/{self.user}.conf", tmpfiles_config)
            click.echo("   ✓ Tmpfiles configuration created")
        else:
            click.echo("   ✓ Tmpfiles configuration already exists")

    def save_secrets_to_file(self):
        """Save generated secrets to file"""

        click.echo("   💾 Saving secrets to file...")
        secrets_file = f"/home/{self.user}/server/secrets.env"
        if not self.secrets_manager:
            click.echo("   ⚠️ Warning: No secrets manager available, skipping save")
            self.warnings.append("No secrets manager available to save secrets")
            return

        if SystemHelper.file_contains_text(secrets_file, "ARGUS_MQTT_PASSWORD"):
            click.echo("   ✓ MQTT password already in secrets file, skipping save")
        else:
            SystemHelper.append_to_file(secrets_file, f"ARGUS_MQTT_PASSWORD={self.secrets_manager.get_mqtt_password()}\n")
            click.echo("   ✓ MQTT password saved to secrets file")

        if SystemHelper.file_contains_text(secrets_file, "ARGUS_READER_MQTT_PASSWORD"):
            click.echo("   ✓ Reader MQTT password already in secrets file, skipping save")
        else:
            SystemHelper.append_to_file(secrets_file, f"ARGUS_READER_MQTT_PASSWORD={self.secrets_manager.get_mqtt_reader_password()}\n")
            click.echo("   ✓ Reader MQTT password saved to secrets file")

        # Set proper ownership and permissions
        SystemHelper.run_command(f"chown {self.user}:{self.user} {secrets_file}")
        SecurityHelper.set_permissions(secrets_file, f"{self.user}:{self.user}", "600")

        click.echo("   ✓ Secrets saved to file")

    def setup_systemd_services(self):
        """Setup systemd services"""
        click.echo("   ⚙️ Setting up systemd services...")

        # Copy systemd service files
        SystemHelper.run_command(f"cp -r {self.install_source}/etc/systemd/* /etc/systemd/system/")

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

        # always update the virtual environment
        packages = ["packages"]
        if ServiceHelper.is_raspberry_pi():
            packages.append("device")

        if self.config.get("deploy_simulator", "false").lower() == "true":
            packages.append("simulator")

        install_config = {
            "PIPENV_TIMEOUT": "9999",
            "CI": "1",
        }

        if SystemHelper.run_command(
            f"sudo -u {self.user} -E PYTHONPATH=/home/{self.user}/server/src -H zsh --login -c '"
            f"{' '.join(f'{key}={value}' for key, value in install_config.items())} "
            f'pipenv install {"-v" if self.verbose else ""} --system --deploy --categories "{" ".join(packages)}"\'',
            suppress_output=False,
            cwd=f"/home/{self.user}/server",
        ):
            click.echo("   ✓ Python virtual environment created/updated")
        else:
            click.echo("   ✗ Failed to create/update Python virtual environment")
            self.warnings.append("Failed to create/update Python virtual environment")

    def update_database_schema(self):
        """Update database schema using Alembic"""
        click.echo("   🗄️ Updating database schema...")
        SystemHelper.run_command(
            f'sudo -u {self.user} -E PYTHONPATH=/home/{self.user}/server/src -H zsh --login -c "'
            'python3 -m flask --app server:app db upgrade"',
            cwd=f"/home/{self.user}/server",
        )
        click.echo("   ✓ Database schema updated")

    def update_database_contents(self):
        """Update database contents if needed"""
        click.echo("   🗄️ Updating database contents...")

        if self.data_set_name:
            SystemHelper.run_command(
                f'sudo -u {self.user} -E PYTHONPATH=/home/{self.user}/server/src -H zsh --login -c "'
                f'bin/data.py -d -c {self.data_set_name}"',
                cwd=f"/home/{self.user}/server",
            )
            click.echo(f"   ✓ Database contents updated with data set '{self.data_set_name}'")
        else:
            click.echo("   ✓ No data set name provided, skipping database contents update")

    def check_user_exists(self) -> bool:
        """Check if service user exists"""
        return os.path.exists(f"/home/{self.user}")

    def check_tmpfiles_configured(self) -> bool:
        """Check if tmpfiles configuration exists"""
        return os.path.exists(f"/usr/lib/tmpfiles.d/{self.user}.conf")

    def check_database_schema_updated(self) -> bool:
        """Check if database schema is up to date"""
        try:
            current_revision = SystemHelper.run_command(
                f"sudo -u {self.user} -E PYTHONPATH=/home/{self.user}/server/src -H zsh --login -c '"
                "python3 -m flask --app server:app db current'",
                capture=True,
                cwd=f"/home/{self.user}/server",
            ).stdout.strip()
            head_revision = SystemHelper.run_command(
                f"sudo -u {self.user} -E PYTHONPATH=/home/{self.user}/server/src -H zsh --login -c '"
                "python3 -m flask --app server:app db heads'",
                cwd=f"/home/{self.user}/server",
                capture=True,
            ).stdout.strip()
            return current_revision == head_revision
        except subprocess.CalledProcessError:
            return False

    def install(self):
        """Install service components"""
        self.create_service_directories()
        self.create_python_virtual_environment()
        self.save_secrets_to_file()
        self.setup_systemd_services()
        self.update_database_schema()
        self.update_database_contents()

    def get_status(self) -> dict:
        """Get service status"""
        return {
            "User exists": self.check_user_exists(),
            "Env file exists": os.path.exists(f"/home/{self.user}/server/.env"),
            "Secrets file exists": os.path.exists(f"/home/{self.user}/server/secrets.env"),
            "Run directory exists": os.path.exists(f"/run/{self.user}"),
            "Service directories exist": (
                os.path.exists(f"/home/{self.user}/server")
                and os.path.exists(f"/home/{self.user}/webapplication")
            ),
            "Database schema updated": self.check_database_schema_updated(),
            "Argus server enabled": ServiceHelper.is_service_enabled("argus_server"),
            "Argus monitor enabled": ServiceHelper.is_service_enabled("argus_monitor"),
            "Nginx enabled": ServiceHelper.is_service_enabled("nginx"),
            "Tmpfiles configured": self.check_tmpfiles_configured(),
        }
