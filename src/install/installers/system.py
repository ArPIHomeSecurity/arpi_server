import os
import subprocess
import click

from install.installers.base import BaseInstaller
from install.helpers import SystemHelper, PackageHelper

class SystemInstaller(BaseInstaller):
    """Installer for system packages and shell configuration"""
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.user = config.get("user", "argus")
    
    def is_zsh_configured(self) -> bool:
        """Check if zsh is configured with oh-my-zsh and ArPI environment"""
        home = f"/home/{self.user}"
        oh_my_zsh_dir = os.path.join(home, ".oh-my-zsh")
        zshrc_file = os.path.join(home, ".zshrc")
        
        return (
            os.path.exists(oh_my_zsh_dir) and
            SystemHelper.run_command(f"getent passwd {self.user}", capture=True).stdout.strip().endswith("/bin/zsh") and
            SystemHelper.file_contains_text(zshrc_file, "source ~/.venvs/server/bin/activate")
        )

    def install_system_packages(self):
        """Install and configure system packages"""
        click.echo("   🔧 Installing system packages...")
        
        PackageHelper.update_package_cache()
        PackageHelper.upgrade_system()
        
        essential_packages = [
            "zsh", "curl", "git", "vim", "minicom", "net-tools", "telnet", "dnsutils",
        ]
        
        PackageHelper.install_packages(essential_packages, "essential packages")
    
    def install_oh_my_zsh(self):
        """Install oh-my-zsh"""
        click.echo("   🐚 Installing oh-my-zsh...")
        
        home = f"/home/{self.user}"
        oh_my_zsh_dir = os.path.join(home, ".oh-my-zsh")
        
        if not os.path.exists(oh_my_zsh_dir):
            # Install oh-my-zsh
            try:
                install_script = f"su - {self.user} -c \"$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh) --unattended\""
                SystemHelper.run_command(install_script)
            except subprocess.CalledProcessError as error:
                if error.returncode == 1:
                    # suppress error code 1
                    # the install fails with code 1 but oh-my-zsh is installed correctly
                    click.echo("   ✓ oh-my-zsh installed")
                else:
                    click.echo("   ✗ oh-my-zsh installation failed")
                    raise
        else:
            click.echo("   ✓ oh-my-zsh already cloned")

        # is zsh shell selected for argus user
        if not SystemHelper.run_command(f"getent passwd {self.user}", capture=True).stdout.strip().endswith("/bin/zsh"):
            # Change shell for argus user
            SystemHelper.run_command(f"chsh -s /bin/zsh {self.user}")
            click.echo("   ✓ Shell changed to zsh for argus user")
        else:
            click.echo("   ✓ zsh is already the default shell for argus user")
    
    def configure_zsh_environment(self):
        """Configure zsh environment for ArPI"""
        click.echo("   ⚙️ Configuring zsh environment...")
        
        if not self.is_zsh_configured():
            home = f"/home/{self.user}"
            zshrc_file = os.path.join(home, ".zshrc")
            
            config_addition = """

# active python virtual environment and load env variables
source ~/.venvs/server/bin/activate
set -a
. ~/server/.env
. ~/server/secrets.env
set +a
"""
            
            SystemHelper.append_to_file(zshrc_file, config_addition)
            click.echo("   ✓ Zsh environment configured")
        else:
            click.echo("   ✓ Zsh environment already configured")
    
    def install_common_tools(self):
        """Install common development tools"""
        click.echo("   🛠️ Installing common development tools...")
        
        tools_packages = [
            "python3", "python3-cryptography", "python3-dev",
            "python3-gpiozero", "python3-gi", "python3-setuptools", "cmake",
            "gcc", "libgirepository1.0-dev", "libcairo2-dev", "pkg-config",
            "gir1.2-gtk-3.0", "fail2ban", "python3-pip", "pipenv"
        ]
        
        if PackageHelper.install_packages(tools_packages, "common development tools"):
            # Remove pip configuration to avoid hash mismatch
            if os.path.exists("/etc/pip.conf"):
                os.remove("/etc/pip.conf")
    
    def install(self):
        """Install system components"""
        self.install_system_packages()
        self.install_oh_my_zsh()
        self.configure_zsh_environment()
        self.install_common_tools()
    
    def is_installed(self) -> bool:
        """Check if system components are installed"""
        return (PackageHelper.is_package_installed("zsh") and 
                self.is_zsh_configured())
    
    def get_status(self) -> dict:
        """Get system component status"""
        return {
            "zsh_installed": PackageHelper.is_package_installed("zsh"),
            "zsh_configured": self.is_zsh_configured(),
            "python3_installed": PackageHelper.is_package_installed("python3")
        }
