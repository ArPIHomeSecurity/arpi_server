from datetime import datetime
import os
import subprocess
import click

from install.helpers import SystemHelper, ServiceHelper, SecurityHelper
from install.installers.base import BaseInstaller


class ServerInstaller(BaseInstaller):
    """Installer for ArPI services and configurations"""

    def __init__(self, config: dict):
        super().__init__(config)
        self.user = config["user"]
        self.db_password = config["db_password"]
        self.salt = config["salt"]
        self.secret = config["secret"]
        self.mqtt_password = config["mqtt_password"]
        self.install_source = config["install_source"]
        self.data_set_name = config["data_set_name"]

    def generate_service_secrets(self):
        """Generate secrets for ArPI services"""

        if os.path.exists(f"/home/{self.user}/server/secrets.env"):
            click.echo("   ✓ Secrets file already exists, skipping generation")
            return

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
            click.echo("   ✓ All service secrets presented, skipping generation")

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

        SecurityHelper.set_file_permissions(
            f"/home/{self.user}", f"{self.user}:{self.user}", "755", recursive=True
        )
        SecurityHelper.set_file_permissions(
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

        if os.path.exists(f"/home/{self.user}/server/secrets.env"):
            click.echo("   ✓ Secrets file already exists, skipping save")
            return

        click.echo("   💾 Saving secrets to file...")

        secrets_file = f"/home/{self.user}/server/secrets.env"

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

        venv_path = f"/home/{self.user}/.venvs"

        if not os.path.exists(venv_path):
            SystemHelper.run_command(f"mkdir -p {venv_path}")
            SecurityHelper.set_file_permissions(venv_path, f"{self.user}:{self.user}", "755")
            click.echo("   ✓ Python virtual environment root created")
        else:
            click.echo("   ✓ Python virtual environment root already exists")

        # always update the virtual environment
        packages = ["packages"]
        if ServiceHelper.is_raspberry_pi():
            packages.append("device")

        if self.config.get("deploy_simulator", "false").lower() == "true":
            packages.append("simulator")

        install_config = {
            "PIPENV_TIMEOUT": "9999",
            "CI": "1",
            "WORKON_HOME": venv_path,
            "PIPENV_CUSTOM_VENV_NAME": "server",
        }

        SystemHelper.run_command(
            f"sudo -u {self.user} -H bash -c 'cd /home/{self.user}/server && "
            f"{' '.join(f'{key}={value}' for key, value in install_config.items())} "
            f'pipenv install --site-packages --categories "{" ".join(packages)}"\'',
            suppress_output=False,
        )
        SecurityHelper.set_file_permissions(
            os.path.join(venv_path, "server"), f"{self.user}:{self.user}", "755"
        )
        click.echo("   ✓ Python virtual environment synced")

    def update_database_schema(self):
        """Update database schema using Alembic"""
        click.echo("   🗄️ Updating database schema...")

        SystemHelper.run_command(
            f'sudo -u {self.user} -H bash -c "cd /home/{self.user}/server; '
            f"source /home/{self.user}/.venvs/server/bin/activate && "
            "export $(grep -hv '^#' .env secrets.env | sed 's/\\\"//g' | xargs -d '\\n') && "
            "printenv && "
            'flask --app server:app db upgrade"'
        )

        click.echo("   ✓ Database schema updated")

    def update_database_contents(self):
        """Update database contents if needed"""
        click.echo("   🗄️ Updating database contents...")

        if self.data_set_name:
            SystemHelper.run_command(
                f'sudo -u {self.user} -H bash -c "cd /home/{self.user}/server; '
                f"source /home/{self.user}/.venvs/server/bin/activate && "
                "export $(grep -hv '^#' .env secrets.env | sed 's/\\\"//g' | xargs -d '\\n') && "
                f'src/data.py -d -c {self.data_set_name}"'
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
                f"sudo -u {self.user} -H bash -c 'cd /home/{self.user}/server && "
                f"source /home/{self.user}/.venvs/server/bin/activate && "
                "export $(grep -hv '^#' .env secrets.env | sed 's/\\\"//g' | xargs -d '\\n') && "
                'flask --app server:app db current"',
                capture=True,
            ).stdout.strip()
            head_revision = SystemHelper.run_command(
                f"sudo -u {self.user} -H bash -c 'cd /home/{self.user}/server && "
                f"source /home/{self.user}/.venvs/server/bin/activate && "
                "export $(grep -hv '^#' .env secrets.env | sed 's/\\\"//g' | xargs -d '\\n') && "
                'flask --app server:app db heads"',
                capture=True,
            ).stdout.strip()
            return current_revision == head_revision
        except subprocess.CalledProcessError:
            return False

    def install(self):
        """Install service components"""
        self.generate_service_secrets()
        self.create_service_directories()
        self.create_python_virtual_environment()
        self.save_secrets_to_file()
        self.setup_systemd_services()
        self.update_database_schema()
        self.update_database_contents()

    def upgrade(self):
        """Upgrade ArPI service components"""
        # 1. Check if service config/code is outdated
        # 2. If outdated, remove/replace as needed and call install()
        # 3. If not outdated, skip install
        # (Implement actual logic here)
        pass

    def get_status(self) -> dict:
        """Get service status"""
        return {
            "User exists": self.check_user_exists(),
            "Env file exists": os.path.exists(f"/home/{self.user}/server/.env"),
            "Secrets file exists": os.path.exists(f"/home/{self.user}/server/secrets.env"),
            "Venv exists": os.path.exists(f"/home/{self.user}/.venvs/server"),
            "Run directory exists": os.path.exists(f"/run/{self.user}"),
            "Service directories exist": (
                os.path.exists(f"/home/{self.user}/server")
                and os.path.exists(f"/home/{self.user}/webapplication")
            ),
            "Database schema updated": self.check_database_schema_updated(),
            "Argus server enabled": SystemHelper.is_service_enabled("argus_server"),
            "Argus monitor enabled": SystemHelper.is_service_enabled("argus_monitor"),
            "Nginx enabled": SystemHelper.is_service_enabled("nginx"),
            "Tmpfiles configured": self.check_tmpfiles_configured(),
        }
