import os
import subprocess
import click

from installer.installers.base import BaseInstaller, InstallerConfig
from installer.helpers import SystemHelper, PackageHelper


class SystemInstaller(BaseInstaller):
    """Installer for system packages and shell configuration"""

    def __init__(self, config: InstallerConfig):
        super().__init__(config)
        self.user = config.user

    def check_zsh_configured(self) -> bool:
        """Check if zsh is configured with oh-my-zsh and ArPI environment"""
        home = f"/home/{self.user}"
        oh_my_zsh_dir = os.path.join(home, ".oh-my-zsh")
        zshenv_file = os.path.join(home, ".zshenv")

        return (
            os.path.exists(oh_my_zsh_dir)
            and SystemHelper.run_command(f"getent passwd {self.user}", capture=True)
            .stdout.strip()
            .endswith("/bin/zsh")
            and SystemHelper.file_contains_text(zshenv_file, f"{self.config_directory}/config.env")
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

        zshenv_file = f"/home/{self.user}/.zshenv"
        if not SystemHelper.file_contains_text(zshenv_file, f"{self.config_directory}/config.env"):
            config_addition = f"""

# load env variables for ArPI
set -a
. {self.config_directory}/config.env
. ~/secrets.env
set +a

# add .local/bin to PATH
export PATH="$HOME/.local/bin:$PATH"
"""

            SystemHelper.append_to_file(zshenv_file, config_addition)
            click.echo("   ✓ Zsh environment configured")
        else:
            click.echo("   ✓ Zsh environment already configured")

        # update zsh theme to 'ys'
        SystemHelper.run_command(
            f"sed -i 's/^ZSH_THEME=.*$/ZSH_THEME=\"ys\"/' /home/{self.user}/.zshrc"
        )

    def remove_old_zsh_configuration(self):
        """
        Remove old configuration (secrest.env and .env) in .zshrc
        """

        SystemHelper.remove_from_file(
            f"/home/{self.user}/.zshrc",
            [
                "set -a",
                ". ~/server/secrets.env",
                ". ~/server/.env",
                "set +a",
            ],
        )



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
        self.install_common_tools()
        self.user_gpio_group()
        self.setup_polkit_rule()

    def post_install(self):
        """Post installation steps for system components"""
        self.configure_zsh_environment()
        self.remove_old_zsh_configuration()
        

    def get_status(self) -> dict:
        """Get system component status"""
        return {
            "ZSH installed": PackageHelper.is_package_installed("zsh"),
            "ZSH configured": self.check_zsh_configured(),
            "User in GPIO group": self.is_user_in_gpio_group(),
            "Python 3 installed": PackageHelper.is_package_installed("python3"),
            "Polkit rule": os.path.exists("/etc/polkit-1/rules.d/49-nopasswd_systemd.rules"),
        }
