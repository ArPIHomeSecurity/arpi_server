from functools import cached_property
import os
import tempfile
import click

from installer.helpers import ServiceHelper, SystemHelper, PackageHelper, SecurityHelper
from installer.installers.base import BaseInstaller, InstallerConfig


ETC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "etc")


class NginxInstaller(BaseInstaller):
    """Installer for NGINX web server"""

    def __init__(self, config: InstallerConfig):
        super().__init__(config)
        self.nginx_version = config.nginx_version
        self.user = config.user
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

        is_remote_enabled = os.path.exists("/usr/local/nginx/conf/sites-enabled/remote.conf")

        # Remove existing config and copy new one
        SystemHelper.run_command("rm -fr /usr/local/nginx/conf/*")
        SystemHelper.run_command(f"cp -r {ETC_DIR}/nginx/* /usr/local/nginx/conf/")

        # create modules-enabled directory and symlinks
        SystemHelper.run_command("mkdir -p /usr/local/nginx/conf/modules-enabled/")
        SystemHelper.run_command(
            "ln -s /usr/local/nginx/conf/modules-available/* /usr/local/nginx/conf/modules-enabled/"
        )

        # create certificate symlink
        SystemHelper.run_command(
            "ln -s /usr/local/nginx/conf/snippets/self-signed.conf /usr/local/nginx/conf/snippets/certificates.conf"
        )

        # create sites-enabled directory and symlinks
        SystemHelper.run_command("mkdir -p /usr/local/nginx/conf/sites-enabled/")
        SystemHelper.run_command(
            "ln -s /usr/local/nginx/conf/sites-available/http.conf /usr/local/nginx/conf/sites-enabled/http.conf"
        )
        SystemHelper.run_command(
            "ln -s /usr/local/nginx/conf/sites-available/local.conf /usr/local/nginx/conf/sites-enabled/local.conf"
        )
        if is_remote_enabled:
            SystemHelper.run_command(
                "ln -s /usr/local/nginx/conf/sites-available/remote.conf /usr/local/nginx/conf/sites-enabled/remote.conf"
            )

        # copy dhparam file
        SystemHelper.run_command(
            f"cp {ETC_DIR}/arpi_dhparam.pem /usr/local/nginx/conf/ssl/arpi_dhparam.pem"
        )
        click.echo("   ✓ Copied dhparam file")

        # set proper ownership for SSL directory
        SecurityHelper.set_permissions(
            "/usr/local/nginx/conf", f"{self.user}:{self.nginx_user}", "744", recursive=True
        )

        click.echo("   ✓ NGINX configuration setup complete")

    def setup_dynamic_config(self):
        """Setup dynamic NGINX configuration"""
        is_remote_enabled = False
        if os.path.exists("/usr/local/nginx/conf/sites-enabled/remote.conf"):
            is_remote_enabled = True
            # remove symlink if exists
            SystemHelper.run_command(
                "rm -fr /usr/local/nginx/conf/sites-enabled/remote.conf"
            )
            click.echo("   ✓ Removed existing remote.conf from NGINX sites-enabled")

        if (
            not os.path.exists(f"{self.config_directory}/remote.conf") and
            os.path.exists("/usr/local/nginx/conf/sites-available/remote.conf")
        ):
            # setup dynamic remote config
            SystemHelper.run_command(
                f"mv /usr/local/nginx/conf/sites-available/remote.conf {self.config_directory}/remote.conf"
            )
            click.echo("   ✓ Moved remote.conf to configuration directory")
        
        if os.path.exists("/usr/local/nginx/conf/sites-available/remote.conf"):
            SystemHelper.run_command(
                "rm -fr /usr/local/nginx/conf/sites-available/remote.conf"
            )
            click.echo("   ✓ Removed existing remote.conf from NGINX sites-available")


        SystemHelper.run_command(
            f"ln -s {self.config_directory}/remote.conf /usr/local/nginx/conf/sites-available/remote.conf"
        )
        click.echo("   ✓ Created symlink for remote.conf in sites-available")

        if is_remote_enabled:
            SystemHelper.run_command(
                "ln -s /usr/local/nginx/conf/sites-available/remote.conf "
                "/usr/local/nginx/conf/sites-enabled/remote.conf"
            )
            click.echo("   ✓ Created symlink for remote.conf in sites-enabled")

        SecurityHelper.set_permissions(
            "/usr/local/nginx/conf", f"{self.user}:{self.nginx_user}", "744", recursive=True
        )

    def check_config_valid(self) -> bool:
        """Check if NGINX configuration is valid"""
        result = SystemHelper.run_command("/usr/local/nginx/sbin/nginx -t", check=False)
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
        click.echo(
            f"   ℹ️ NGINX Actual: {self.get_system_nginx_version} | Desired: {self.nginx_version}"
        )
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

    def post_install(self):
        """Post installation steps for NGINX"""
        # setup dynamic config
        click.echo("   ⚙️ Running NGINX post-installation steps...")
        self.setup_dynamic_config()
        click.echo("   ✓ NGINX post-installation complete")

    def get_status(self) -> dict:
        """Get NGINX status"""
        return {
            "NGINX installed": os.path.exists("/usr/local/nginx/sbin/nginx"),
            "NGINX version": os.path.exists("/usr/local/nginx/sbin/nginx")
            and not self.needs_installation(),
            "NGINX configured": os.path.exists("/usr/local/nginx/conf/sites-enabled/http.conf"),
            "NGINX config valid": self.check_config_valid(),
            "NGINX running": ServiceHelper.is_service_running("nginx"),
            "NGINX SSL certificates": (
                os.path.exists("/usr/local/nginx/conf/ssl/arpi_dhparam.pem")
                and os.path.exists("/usr/local/nginx/conf/ssl/arpi_app.crt")
                and os.path.exists("/usr/local/nginx/conf/ssl/arpi_app.key")
            ),
        }
