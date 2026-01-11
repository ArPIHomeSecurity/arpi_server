import subprocess
import click

from installer.helpers import SystemHelper, PackageHelper, ServiceHelper
from installer.installers.base import BaseInstaller, InstallerConfig


class DatabaseInstaller(BaseInstaller):
    """Installer for PostgreSQL database"""

    def __init__(self, config: InstallerConfig):
        super().__init__(config)
        self.postgresql_version = config.postgresql_version
        self.db_username = config.user
        self.db_name = config.db_name
        self.user = config.user

    def install_postgresql(self):
        """Install PostgreSQL database"""
        click.echo("   🗄️ Installing PostgreSQL...")

        if self.postgresql_version is None:
            pg_packages = [
                "postgresql",
                "postgresql-client",
                "postgresql-contrib",
                "libpq-dev",
            ]
        else:
            pg_packages = [
                f"postgresql-{self.postgresql_version}",
                f"postgresql-client-{self.postgresql_version}",
                f"postgresql-contrib-{self.postgresql_version}",
                "libpq-dev",
            ]

        version = (
            "with default version" if self.postgresql_version is None else self.postgresql_version
        )
        if PackageHelper.install_packages(pg_packages, f"PostgreSQL {version}"):
            ServiceHelper.start_service("postgresql")
            ServiceHelper.enable_service("postgresql")

        # Ensure service is running
        if not ServiceHelper.is_service_running("postgresql"):
            ServiceHelper.start_service("postgresql")

    def configure_database(self):
        """Configure PostgreSQL database for ArPI"""
        click.echo("   ⚙️ Configuring database...")

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

    def get_system_postgresql_version(self) -> str | None:
        """Get the installed PostgreSQL version"""
        result = SystemHelper.run_command("psql --version", check=False, capture=True)
        if result.returncode == 0:
            version_line = result.stdout.strip()
            if "psql (PostgreSQL)" in version_line:
                # format: psql (PostgreSQL) 15.3 (Ubuntu 15.3-1.pgdg22.04+1)
                return version_line.split()[2].split(".")[0]

    def needs_installation(self) -> bool:
        """Determine if PostgreSQL needs installation or upgrade"""
        click.echo(
            f"   ℹ️ PostgreSQL Actual: {self.get_system_postgresql_version()} | Desired: {self.postgresql_version}"
        )
        if self.postgresql_version is None:
            return self.get_system_postgresql_version() is None

        return self.get_system_postgresql_version() != self.postgresql_version

    def install(self):
        """Install database components"""
        if self.needs_installation():
            self.install_postgresql()
        else:
            click.echo("   ✓ PostgreSQL already at the desired version")

        self.configure_database()

    def get_status(self) -> dict:
        """Get database status"""
        return {
            "PostgreSQL installed": PackageHelper.is_package_installed(
                f"postgresql-{self.postgresql_version}"
            )
            or PackageHelper.is_package_installed("postgresql"),
            "PostgreSQL version": not self.needs_installation(),
            "PostgreSQL running": ServiceHelper.is_service_running("postgresql"),
            "PostgreSQL enabled": ServiceHelper.is_service_enabled("postgresql"),
            "Database user exists": self.check_user_exists(),
            "Database exists": self.check_database_exists(),
        }
