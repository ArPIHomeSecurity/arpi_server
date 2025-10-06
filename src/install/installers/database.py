import os
import click

from install.helpers import SystemHelper, PackageHelper, ServiceHelper, SecurityHelper
from install.installers.base import BaseInstaller


class DatabaseInstaller(BaseInstaller):
    """Installer for PostgreSQL database"""

    def __init__(self, config: dict):
        super().__init__(config)
        self.postgresql_version = config.get("postgresql_version", "15")
        self.db_username = config.get("db_username", "argus")
        self.db_name = config.get("db_name", "argus")
        self.db_password = config.get("db_password", "")
        self.user = config.get("user", "argus")

        # try to read existing password from secrets.env
        secrets_file = os.path.join(f"/home/{self.user}/server", "secrets.env")
        if os.path.exists(secrets_file):
            with open(secrets_file, "r") as f:
                for line in f:
                    if line.startswith("DB_PASSWORD="):
                        self.db_password = line.strip().split("=", 1)[1].strip('"')
                        break

    def install_postgresql(self):
        """Install PostgreSQL database"""
        click.echo("   🗄️ Installing PostgreSQL...")

        pg_packages = [
            f"postgresql-{self.postgresql_version}",
            f"postgresql-client-{self.postgresql_version}",
            f"postgresql-contrib-{self.postgresql_version}",
            "libpq-dev",
        ]

        if PackageHelper.install_packages(pg_packages, f"PostgreSQL {self.postgresql_version}"):
            ServiceHelper.start_service("postgresql")
            ServiceHelper.enable_service("postgresql")

        # Ensure service is running
        if not SystemHelper.is_service_running("postgresql"):
            ServiceHelper.start_service("postgresql")

    def configure_database(self):
        """Configure PostgreSQL database for ArPI"""
        click.echo("   ⚙️ Configuring database...")

        # Generate database password if not set
        if not self.db_password:
            self.db_password = SecurityHelper.generate_password()
            click.echo("   ✓ Generated database password")

        # Create database user
        try:
            # Check if user exists
            if not self.check_user_exists():
                # Create user
                SystemHelper.run_command(
                    f'su - postgres -c "createuser --createdb --login --no-password {self.db_username}"',
                    suppress_output=False,
                )
                click.echo(f"   ✓ Created database user: {self.db_username}")
            else:
                click.echo(f"   ✓ Database user {self.db_username} already exists")

            # we socket based authentication, so no need to set password
            # SystemHelper.run_command(
            #     f'su - postgres -c "psql -c \\"ALTER USER {self.db_username} WITH PASSWORD \'{self.db_password}\';\\""',
            #     suppress_output=False,
            # )
            # click.echo(f"   ✓ Updated password for user: {self.db_username}")
        except Exception as e:
            click.echo(f"    ⚠️ WARNING: User creation may have failed: {e}")
            self.warnings.append(f"User creation may have failed: {e}")

        # Create database
        try:
            if not self.check_database_exists():
                SystemHelper.run_command(
                    f"sudo -u postgres createdb -O {self.db_username} {self.db_name}"
                )
                click.echo(f"   ✓ Created database: {self.db_name}")
            else:
                click.echo(f"   ✓ Database {self.db_name} already exists")
        except Exception as e:
            click.echo(f"    ⚠️ WARNING: Database creation may have failed: {e}")
            self.warnings.append(f"Database creation may have failed: {e}")

    def install(self):
        """Install database components"""
        self.install_postgresql()
        self.configure_database()

    def check_user_exists(self) -> bool:
        """Check if the database user exists"""
        try:
            result = SystemHelper.run_command(
                f'su - postgres -c "psql -tAc \\"SELECT 1 FROM pg_roles WHERE rolname=\'{self.db_username}\'\\""',
                capture=True,
                check=False,
                suppress_output=True,
            )
            return "1" in result.stdout
        except Exception:
            return False

    def check_database_exists(self) -> bool:
        """Check if the database exists"""
        try:
            result = SystemHelper.run_command(
                f"sudo -u postgres psql -lqt | cut -d \\| -f 1 | grep -qw {self.db_name}",
                check=False,
                suppress_output=True,
            )
            return result.returncode == 0
        except Exception:
            return False

    def get_status(self) -> dict:
        """Get database status"""
        return {
            "PostgreSQL installed": PackageHelper.is_package_installed(
                f"postgresql-{self.postgresql_version}"
            ),
            "PostgreSQL running": SystemHelper.is_service_running("postgresql"),
            "PostgreSQL enabled": SystemHelper.is_service_enabled("postgresql"),
            "Database user exists": self.check_user_exists(),
            "Database exists": self.check_database_exists(),
        }
