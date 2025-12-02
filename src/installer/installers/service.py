import os
import subprocess
import click

from installer.helpers import SystemHelper, ServiceHelper, SecurityHelper
from installer.installers.base import BaseInstaller, InstallerConfig

ETC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "etc")

class ServiceInstaller(BaseInstaller):
    """Installer for ArPI services and configurations"""

    def __init__(self, config: InstallerConfig):
        super().__init__(config)
        self.user = config.user
        self.secrets_manager = config.secrets_manager
        self.data_set_name = config.data_set_name
        self.db_name = config.db_name
        self.verbose = config.verbose

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

        click.echo("   🔐 Checking MQTT secrets...")
        if self.secrets_manager.get_secret("ARGUS_MQTT_PASSWORD"):
            click.echo("   ✓ MQTT password already in secrets file")
        else:
            self.secrets_manager.generate_secret('ARGUS_MQTT_PASSWORD')
            click.echo("   ✓ MQTT password created")

        if self.secrets_manager.get_secret("ARGUS_READER_MQTT_PASSWORD"):
            click.echo("   ✓ Reader MQTT password already in secrets file")
        else:
            self.secrets_manager.generate_secret('ARGUS_READER_MQTT_PASSWORD')
            click.echo("   ✓ Reader MQTT password created")

        self.secrets_manager.save_secrets()

    def setup_systemd_services(self):
        """Setup systemd services"""
        click.echo("   ⚙️ Setting up systemd services...")

        # Copy systemd service files
        SystemHelper.run_command(f"cp -r {ETC_DIR}/systemd/* /etc/systemd/system/")

        # Reload systemd daemon
        SystemHelper.run_command("systemctl daemon-reload")

        # Enable services
        services_to_enable = ["argus_server", "argus_monitor", "nginx"]
        for service in services_to_enable:
            ServiceHelper.enable_service(service)
            click.echo(f"   ✓ Enabled {service} service")

        click.echo("   ✓ Systemd services configured")

    def remove_virtual_env_if_exists(self):
        """Remove existing Python virtual environment if it exists"""
        # remove existing virtual environment
        click.echo("   🗑️ Removing existing Python virtual environment if it exists...")
        try:
            SystemHelper.run_command(
                f"sudo -u {self.user} -E -H zsh --login -c '"
                "pipenv --rm || true'",
                suppress_output=True,
                cwd=f"/home/{self.user}/server",
            )
        except FileNotFoundError:
            pass

        # remove line from .zshrc "source ~/.venvs/server/bin/activate"
        click.echo("   🗑️ Removing source line from .zshrc if it exists...")
        SystemHelper.remove_from_file(
            f"/home/{self.user}/.zshrc",
            "source ~/.venvs/server/bin/activate",
        )

        venv_path = f"/home/{self.user}/.venvs"
        if os.path.exists(venv_path):
            click.echo("   🗑️ Removing virtual environment folder...")
            SystemHelper.run_command(f"rm -rf {venv_path}")

    def update_database_schema(self):
        """Update database schema using Alembic"""
        click.echo("   🗄️ Updating database schema...")

        if not self.shared_directory:
            click.echo("   ⚠️ Shared directory not found, cannot update database schema")
            self.warnings.append("Shared directory not found, cannot update database schema")
            return

        SystemHelper.run_command(
            f"sudo -u {self.user} -E -H zsh --login -c '"
            f"flask --app server:app db upgrade --directory {self.shared_directory}/migrations'",   
        )
        click.echo("   ✓ Database schema updated")

    def update_database_contents(self):
        """Update database contents if needed"""
        click.echo("   🗄️ Updating database contents...")

        if self.data_set_name:
            SystemHelper.run_command(
                f"sudo -u {self.user} -E -H zsh --login -c '"
                f"arpi-data -d -c {self.data_set_name}'",
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
                f"sudo -u {self.user} -H zsh --login -c '"
                f"flask --app server:app db current --directory {self.shared_directory}/migrations'",
                capture=True
            ).stdout.strip()
            head_revision = SystemHelper.run_command(
                f"sudo -u {self.user} -H zsh --login -c '"
                f"flask --app server:app db heads --directory {self.shared_directory}/migrations'",
                capture=True,
            ).stdout.strip()
            return current_revision == head_revision
        except subprocess.CalledProcessError:
            return False

    def remove_old_code(self):
        """Remove old version of the service if it exists"""
        if os.path.exists(f"/home/{self.user}/server"):
            SystemHelper.run_command(f"rm -rf /home/{self.user}/server")
            click.echo(f"   ✓ Old version removed in /home/{self.user}/server")

    def install(self):
        """Install service components"""
        self.remove_virtual_env_if_exists()
        self.create_service_directories()
        self.save_secrets_to_file()
        self.setup_systemd_services()

    def post_install(self):
        self.update_database_schema()
        self.update_database_contents()
        self.remove_old_code()

    def get_status(self) -> dict:
        """Get service status"""
        return {
            "User exists": self.check_user_exists(),
            "Env file exists": os.path.exists(f"{self.config_directory}/config.env"),
            "Secrets file exists": os.path.exists(f"/home/{self.user}/secrets.env"),
            "Run directory exists": os.path.exists(f"/run/{self.user}"),
            "Web application directories exist": (
                os.path.exists(f"/home/{self.user}/webapplication")
            ),
            "Database schema updated": self.check_database_schema_updated(),
            "Argus server enabled": ServiceHelper.is_service_enabled("argus_server"),
            "Argus monitor enabled": ServiceHelper.is_service_enabled("argus_monitor"),
            "Nginx enabled": ServiceHelper.is_service_enabled("nginx"),
            "Tmpfiles configured": self.check_tmpfiles_configured(),
        }
