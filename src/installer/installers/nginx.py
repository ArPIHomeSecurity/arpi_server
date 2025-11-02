from functools import cached_property
import os
import tempfile
import click

from installer.helpers import SystemHelper, PackageHelper, SecurityHelper
from installer.installers.base import BaseInstaller


class NginxInstaller(BaseInstaller):
    """Installer for NGINX web server"""

    def __init__(self, config: dict):
        super().__init__(config)
        self.nginx_version = config["nginx_version"]
        self.dhparam_file = config["dhparam_file"]
        self.user = config["user"]
        self.install_source = config["install_source"]
        self.nginx_user = "www-data"

    def install_nginx_dependencies(self):
        """Install NGINX build dependencies"""
        click.echo("   📦 Installing NGINX build dependencies...")
        build_deps = ["build-essential", "libpcre3-dev", "libssl-dev", "zlib1g-dev"]
        PackageHelper.install_packages(build_deps, "NGINX build dependencies")

    def compile_nginx_from_source(self):
        """Compile and install NGINX from source"""
        click.echo(f"   🔨 Compiling NGINX {self.nginx_version} from source...")

        # Check if already installed
        if os.path.exists("/usr/local/nginx/sbin/nginx"):
            click.echo("   ✓ NGINX already installed")
            return

        with tempfile.TemporaryDirectory() as temp_dir:
            nginx_archive = f"nginx-{self.nginx_version}.tar.gz"
            nginx_dir = f"nginx-{self.nginx_version}"

            # Download NGINX source
            SystemHelper.run_command(
                f"curl -s -O -J http://nginx.org/download/{nginx_archive}", cwd=temp_dir
            )

            # Extract and compile
            SystemHelper.run_command(f"tar xzf {nginx_archive}", cwd=temp_dir)

            nginx_source_dir = os.path.join(temp_dir, nginx_dir)

            # Configure build
            SystemHelper.run_command(
                "./configure --with-http_stub_status_module --with-http_ssl_module",
                cwd=nginx_source_dir,
            )

            # Compile
            SystemHelper.run_command("make", cwd=nginx_source_dir)

            # Install
            SystemHelper.run_command("make install", cwd=nginx_source_dir)

            click.echo("   ✓ NGINX compiled and installed successfully")

    def configure_nginx_setup(self):
        """Configure NGINX setup matching bash script"""
        click.echo("   ⚙️ Configuring NGINX...")

        # Add user to group
        if not self.check_user_in_group(self.user, self.nginx_user):
            SystemHelper.run_command(f"adduser {self.nginx_user} {self.user}")
            click.echo(f"   ✓ Added {self.nginx_user} to {self.user} group")

        # Remove existing config and copy new one
        SystemHelper.run_command("rm -fr /usr/local/nginx/conf/*")
        SystemHelper.run_command(f"cp -r {self.install_source}/etc/nginx/* /usr/local/nginx/conf/")

        # Create modules-enabled directory and symlinks
        SystemHelper.run_command("mkdir -p /usr/local/nginx/conf/modules-enabled/")
        SystemHelper.run_command(
            "ln -s /usr/local/nginx/conf/modules-available/* /usr/local/nginx/conf/modules-enabled/"
        )

        # Create certificate symlink
        SystemHelper.run_command(
            "ln -s /usr/local/nginx/conf/snippets/self-signed.conf /usr/local/nginx/conf/snippets/certificates.conf"
        )

        # Create sites-enabled directory and symlinks
        SystemHelper.run_command("mkdir -p /usr/local/nginx/conf/sites-enabled/")
        SystemHelper.run_command(
            "ln -s /usr/local/nginx/conf/sites-available/http.conf /usr/local/nginx/conf/sites-enabled/http.conf"
        )
        SystemHelper.run_command(
            "ln -s /usr/local/nginx/conf/sites-available/local.conf /usr/local/nginx/conf/sites-enabled/local.conf"
        )

        # Copy dhparam file
        SystemHelper.run_command(
            f"cp {self.install_source}/{self.dhparam_file} /usr/local/nginx/conf/ssl/arpi_dhparam.pem"
        )
        click.echo("   ✓ Copied dhparam file")

        # Set proper ownership for SSL directory
        SecurityHelper.set_file_permissions(
            "/usr/local/nginx/conf", f"{self.nginx_user}:{self.nginx_user}", "755", recursive=True
        )

        click.echo("   ✓ NGINX configuration setup complete")

    def check_user_in_group(self, user: str, group: str) -> bool:
        """Check if a user is in a specific group"""
        try:
            result = SystemHelper.run_command(f"groups {user}", capture=True, check=False)
            return group in result.stdout.split()
        except Exception:
            return False

    def check_config_valid(self) -> bool:
        """Check if NGINX configuration is valid"""
        result = SystemHelper.run_command(
            "/usr/local/nginx/sbin/nginx -t", check=False
        )
        if result.returncode == 0:
            return True
        
        for line in result.stdout:
            if "syntax is ok" in line:
                return True

        return False

    @cached_property
    def get_system_nginx_version(self) -> str | None:
        """Get the installed NGINX version"""
        result = SystemHelper.run_command(
            "/usr/local/nginx/sbin/nginx -v", check=False, capture=True
        )
        if result.returncode == 0:
            version_line = result.stderr.strip()
            if "nginx version:" in version_line:
                click.echo(f"   ℹ️ Found NGINX version: {version_line}")
                # format: nginx version: nginx/1.28.0
                return version_line.split(":")[1].strip().split("/")[1]

    def needs_installation(self) -> bool:
        """Determine if NGINX needs installation or upgrade"""
        click.echo(f"   ℹ️ NGINX Actual: {self.get_system_nginx_version} | Desired: {self.nginx_version}")
        return self.get_system_nginx_version != self.nginx_version

    def install(self):
        """Install NGINX components"""
        if self.needs_installation():
            if self.get_system_nginx_version:
                # remove old version
                click.echo("   🗑️ Removing old NGINX version...")
                SystemHelper.run_command("rm -fr /usr/local/nginx | true")

            self.install_nginx_dependencies()
            self.compile_nginx_from_source()
        else:
            click.echo("   ✓ NGINX already at the desired version")

        self.configure_nginx_setup()

    def get_status(self) -> dict:
        """Get NGINX status"""
        return {
            "NGINX installed": os.path.exists("/usr/local/nginx/sbin/nginx"),
            "NGINX version": os.path.exists("/usr/local/nginx/sbin/nginx") and not self.needs_installation(),
            "NGINX configured": os.path.exists("/usr/local/nginx/conf/sites-enabled/http.conf"),
            "NGINX user": self.check_user_in_group(self.nginx_user, self.user),
            "NGINX config valid": self.check_config_valid(),
            "NGINX running": SystemHelper.is_service_running("nginx"),
            "NGINX SSL certificates": (
                os.path.exists("/usr/local/nginx/conf/ssl/arpi_dhparam.pem")
                and os.path.exists("/usr/local/nginx/conf/ssl/arpi_app.crt")
                and os.path.exists("/usr/local/nginx/conf/ssl/arpi_app.key")
            ),
        }
