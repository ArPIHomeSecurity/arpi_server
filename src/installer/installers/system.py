import os
import subprocess
import click

from installer.installers.base import BaseInstaller
from installer.helpers import SystemHelper, PackageHelper


class SystemInstaller(BaseInstaller):
    """Installer for system packages and shell configuration"""

    def __init__(self, config: dict):
        super().__init__(config)
        self.user = config["user"]
        self.python_version = config["python_version"]

    def check_zsh_configured(self) -> bool:
        """Check if zsh is configured with oh-my-zsh and ArPI environment"""
        home = f"/home/{self.user}"
        oh_my_zsh_dir = os.path.join(home, ".oh-my-zsh")
        zshrc_file = os.path.join(home, ".zshrc")

        return (
            os.path.exists(oh_my_zsh_dir)
            and SystemHelper.run_command(f"getent passwd {self.user}", capture=True)
            .stdout.strip()
            .endswith("/bin/zsh")
            and SystemHelper.file_contains_text(zshrc_file, ". ~/server/.env")
            and SystemHelper.file_contains_text(zshrc_file, ". ~/server/secrets.env")
        )

    def install_system_packages(self):
        """Install and configure system packages"""
        click.echo("   🔧 Installing system packages...")

        PackageHelper.update_package_cache()
        PackageHelper.upgrade_system()

        essential_packages = [
            "zsh",
            "curl",
            "git",
            "vim",
            "minicom",
            "net-tools",
            "telnet",
            "dnsutils",
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
                install_script = f'su - {self.user} -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh) --unattended"'
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
        if (
            not SystemHelper.run_command(f"getent passwd {self.user}", capture=True)
            .stdout.strip()
            .endswith("/bin/zsh")
        ):
            # Change shell for argus user
            SystemHelper.run_command(f"chsh -s /bin/zsh {self.user}")
            click.echo("   ✓ Shell changed to zsh for argus user")
        else:
            click.echo("   ✓ zsh is already the default shell for argus user")

    def configure_zsh_environment(self):
        """Configure zsh environment for ArPI"""
        click.echo("   ⚙️ Configuring zsh environment...")

        if not SystemHelper.file_contains_text(
            f"/home/{self.user}/.zshrc", ". ~/server/.env"
        ):
            home = f"/home/{self.user}"
            zshrc_file = os.path.join(home, ".zshrc")

            config_addition = """

# active python virtual environment and load env variables
set -a
. ~/server/.env
. ~/server/secrets.env
set +a
"""

            SystemHelper.append_to_file(zshrc_file, config_addition)
            # update theme
            SystemHelper.run_command(
                f"sed -i 's/^ZSH_THEME=.*$/ZSH_THEME=\"ys\"/' {zshrc_file}"
            )
            click.echo("   ✓ Zsh environment configured")
        else:
            click.echo("   ✓ Zsh environment already configured")

    def install_common_tools(self):
        """Install common development tools"""
        click.echo("   🛠️ Installing common development tools...")

        tools_packages = [
            "python3",
            "python3-dev",
            "python3-cryptography",
            "python3-gpiozero",
            "python3-setuptools",
            "cmake",
            "gcc",
            "libsystemd-dev",
            "pkg-config",
            "gir1.2-gtk-3.0",
            "fail2ban",
            "python3-pip",
            "pipenv",
        ]

        if PackageHelper.install_packages(tools_packages, "common development tools"):
            # Remove pip configuration to avoid hash mismatch
            if os.path.exists("/etc/pip.conf"):
                os.remove("/etc/pip.conf")

    def is_user_in_gpio_group(self) -> bool:
        """Check if user is in gpio group"""
        try:
            groups_output = SystemHelper.run_command(
                f"groups {self.user}", capture=True
            ).stdout
            groups = groups_output.strip().split(":")[-1].strip().split()
            return "gpio" in groups
        except subprocess.CalledProcessError:
            return False

    def user_gpio_group(self):
        """Add user to gpio group for GPIO access"""
        click.echo("   👥 Adding user to gpio group...")

        if not self.is_user_in_gpio_group():
            SystemHelper.run_command(f"usermod -aG gpio {self.user}")
            click.echo(f"   ✓ User '{self.user}' added to gpio group")
        else:
            click.echo(f"   ✓ User '{self.user}' is already in gpio group")

    def check_python_version(self) -> bool:
        """Check if the required Python version is installed"""
        try:
            python_executable = f"python{self.python_version}"
            version_output = SystemHelper.run_command(
                f"{python_executable} --version", capture=True
            ).stdout
            return version_output.startswith(f"Python {self.python_version}")
        except subprocess.CalledProcessError:
            return False

    def setup_polkit_rule(self):
        """Setup polkit rule for systemd access without password"""
        click.echo("   🛂 Setting up polkit rule for systemd access...")

        rule_file = "/etc/polkit-1/rules.d/49-nopasswd_systemd.rules"
        rule_content = """
polkit.addRule(function(action, subject) {
    if ((action.id == "org.freedesktop.systemd1.manage-units" ||
         action.id == "org.freedesktop.systemd1.manage-unit-files") &&
        subject.isInGroup("sudo")) {
        return polkit.Result.YES;
    }
});

"""
        if not os.path.exists(rule_file):
            SystemHelper.write_file(rule_file, rule_content)
    
    def install(self):
        """Install system components"""
        self.install_system_packages()
        self.install_oh_my_zsh()
        self.configure_zsh_environment()
        self.install_common_tools()
        self.user_gpio_group()
        self.setup_polkit_rule()

    def get_status(self) -> dict:
        """Get system component status"""
        return {
            "ZSH installed": PackageHelper.is_package_installed("zsh"),
            "ZSH configured": self.check_zsh_configured(),
            "User in GPIO group": self.is_user_in_gpio_group(),
            "Python 3 installed": PackageHelper.is_package_installed("python3"),
            f"Python version={self.python_version}": self.check_python_version(),
            "Polkit rule": os.path.exists("/etc/polkit-1/rules.d/49-nopasswd_systemd.rules"),
        }
