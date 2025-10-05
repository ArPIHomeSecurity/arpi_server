import click

from install.helpers import SystemHelper, PackageHelper
from install.installers.base import BaseInstaller


class CertbotInstaller(BaseInstaller):
    """Installer for SSL certificate management"""

    def should_use_snap_certbot(self) -> bool:
        """Determine if snap should be used for certbot installation"""
        return SystemHelper.get_architecture() == "x86_64"

    def install_certbot(self):
        """Install Certbot for SSL certificate management"""

        if self.should_use_snap_certbot():
            click.echo("   🔒 Installing Certbot from Snap...")
            # Install via snap for x86_64
            if PackageHelper.install_packages(["snapd"]):
                try:
                    SystemHelper.run_command("snap install core")
                    SystemHelper.run_command("snap refresh core")
                    SystemHelper.run_command("snap install certbot --classic")
                    SystemHelper.run_command("ln -sf /snap/bin/certbot /usr/bin/certbot")
                    click.echo("   ✓ Certbot installed via snap")
                except Exception as e:
                    click.echo(f"    ⚠️ WARNING: Snap installation failed, trying apt: {e}")
                    self.warnings.append(f"Snap installation failed: {e}")
        else:
            click.echo("   🔒 Installing Certbot via apt...")
            # Install via apt for ARM architectures
            PackageHelper.install_packages(["certbot"])
            click.echo("   ✓ Certbot installed via apt")

    def install(self):
        """Install Certbot components"""
        self.install_certbot()

    def is_installed(self) -> bool:
        """Check if Certbot is installed"""
        try:
            SystemHelper.run_command("certbot --version", capture=True)
            return True
        except Exception:
            return False

    def get_status(self) -> dict:
        """Get Certbot status"""
        return {"Certbot installed": self.is_installed()}
