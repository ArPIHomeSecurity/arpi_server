from datetime import datetime
import os
import platform
import secrets
import string
import subprocess

import shutil
from time import sleep

import click


class AptLockError(Exception):
    """Custom exception for apt lock errors"""

    pass


class SystemHelper:
    """Helper class for general system operations"""

    @staticmethod
    def run_command(
        command: str,
        input: str = "",
        check: bool = True,
        capture: bool = False,
        cwd: str = None,
        suppress_output: bool = True,
    ) -> subprocess.CompletedProcess:
        """
        Run shell command with proper error handling

        Args:
            command (str): Command to execute
            input (str, optional): Input to pass to the command's stdin. Defaults to "".
            check (bool, optional): Whether to raise an error on non-zero exit code. Defaults to True.
            capture (bool, optional): Whether to capture the command's terminal output. Defaults to False.
            cwd (str, optional): Working directory to execute the command in. Defaults to None.
            suppress_output (bool, optional): Whether to suppress command terminal output. Defaults to True.
        """

        if capture and input:
            raise ValueError("Cannot use 'input' with 'capture=True'")

        result: subprocess.CompletedProcess = None
        try:
            if not suppress_output:
                click.echo(
                    f"   ⚡Starting command at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
                click.echo(f"    > Running: {command}")

            collected_output = []

            def print_lines(output):
                for line in output or []:
                    line = "    |\t" + line.rstrip()
                    if not suppress_output:
                        click.echo(line)
                    collected_output.append(line)

            if capture:
                result = subprocess.run(
                    command, shell=True, check=check, capture_output=True, text=True, cwd=cwd
                )
                if result.stdout and not suppress_output:
                    print_lines(result.stdout.splitlines())
            else:
                # Stream output line by line, indenting each line
                process = subprocess.Popen(
                    command,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.PIPE if input else None,
                    text=True,
                    cwd=cwd,
                )

                if input:
                    process.stdin.write(input)
                    process.stdin.flush()
                    process.stdin.close()

                print_lines(process.stdout)

                process.wait()
                result = subprocess.CompletedProcess(
                    args=command, returncode=process.returncode, stdout=collected_output
                )

                if check and process.returncode != 0:
                    raise subprocess.CalledProcessError(
                        process.returncode, command, output=process.stdout.readlines()
                    )

            if not suppress_output:
                click.echo(
                    f"   ⚡Finished command at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )

            return result
        except subprocess.CalledProcessError as e:
            if "apt-get" in command and e.returncode == 100:
                click.echo("    ⚠️ APT lock error encountered. Another process may be using apt.")
                raise AptLockError(
                    "APT lock error encountered. Another process may be using apt."
                ) from e

            click.echo(f"    Command failed! Error: {e}")
            if suppress_output:
                click.echo("    ⚠️ Command failed!")
                if result and (e.stdout or result.stdout):
                    for line in e.stdout or result.stdout:
                        click.echo(line)

            raise

    @staticmethod
    def is_service_running(service: str) -> bool:
        """Check if systemd service is running"""
        try:
            result = SystemHelper.run_command(f"systemctl is-active --quiet {service}", check=False)
            return result.returncode == 0
        except Exception:
            return False

    @staticmethod
    def is_service_enabled(service: str) -> bool:
        """Check if systemd service is enabled"""
        try:
            result = SystemHelper.run_command(
                f"systemctl is-enabled --quiet {service}", check=False
            )
            return result.returncode == 0
        except Exception:
            return False

    @staticmethod
    def get_architecture() -> str:
        """Get system architecture"""
        return platform.machine()

    @staticmethod
    def file_contains_text(file_path: str, text: str) -> bool:
        """Check if file contains specific text"""
        if not os.path.exists(file_path):
            return False

        try:
            with open(file_path, "r") as f:
                content = f.read()
                return text in content
        except Exception:
            return False

    @staticmethod
    def append_to_file(file_path: str, text: str):
        """Append text to file"""
        with open(file_path, "a") as f:
            f.write(text)

    @staticmethod
    def remove_from_file(file_path: str, text: str):
        """Remove lines containing specific text from file"""
        if not os.path.exists(file_path):
            return

        with open(file_path, "r") as f:
            lines = f.readlines()

        with open(file_path, "w") as f:
            for line in lines:
                if text not in line:
                    f.write(line)

    @staticmethod
    def write_file(file_path: str, content: str):
        """Write content to file"""
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w") as f:
            f.write(content)

    @staticmethod
    def copy_tree(src, dst):
        """Copy directory tree, replacing destination if exists"""
        if os.path.exists(dst):
            shutil.rmtree(dst)

        shutil.copytree(src, dst, symlinks=True)


class SecurityHelper:
    """Helper class for security-related operations"""

    @staticmethod
    def generate_password(length: int = 24) -> str:
        """Generate a secure random password"""
        alphabet = string.ascii_letters + string.digits + "!#*+"
        return "".join(secrets.choice(alphabet) for _ in range(length))

    @staticmethod
    def set_file_permissions(file_path: str, owner: str, mode: str, recursive: bool = False):
        """Set file ownership and permissions"""
        recursive_flag = "-R" if recursive else ""
        SystemHelper.run_command(f"chown {recursive_flag} {owner} {file_path}")
        SystemHelper.run_command(f"chmod {recursive_flag} {mode} {file_path}")


class PackageHelper:
    """Helper class for package management operations"""

    MAX_RETRIES = 5
    RETRY_DELAY = 10

    @staticmethod
    def update_package_cache():
        """Update package cache"""
        attempts = 0
        error = None
        while attempts < PackageHelper.MAX_RETRIES:
            try:
                SystemHelper.run_command("apt-get update", suppress_output=False)
                return
            except AptLockError as e:
                attempts += 1
                error = e
                sleep(PackageHelper.RETRY_DELAY)

        raise error

    @staticmethod
    def upgrade_system():
        """Upgrade system packages"""
        attempts = 0
        error = None
        while attempts < PackageHelper.MAX_RETRIES:
            try:
                SystemHelper.run_command(
                    'apt-get -y -o Dpkg::Options::="--force-confnew" upgrade', suppress_output=False
                )
                SystemHelper.run_command("apt-get -y autoremove", suppress_output=False)
                return
            except AptLockError as e:
                attempts += 1
                error = e

        raise error

    @staticmethod
    def is_package_installed(package: str) -> bool:
        """Check if package is installed"""
        try:
            result = SystemHelper.run_command(
                f"dpkg -l | grep '^ii  {package} '", check=False, capture=True
            )
            return result.returncode == 0
        except Exception:
            return False

    @staticmethod
    def install_packages(packages: list, description: str = None):
        """Install multiple packages if not already installed"""
        missing_packages = []
        for package in packages:
            if not PackageHelper.is_package_installed(package):
                missing_packages.append(package)

        if missing_packages:
            packages_str = " ".join(missing_packages)
            click.echo(
                f"   ⚡Starting installation at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            if description:
                click.echo(f"    > Installing {description}...")
            else:
                click.echo(f"    > Installing packages: {packages_str}...")

            attempts = 0
            error = None
            while attempts < PackageHelper.MAX_RETRIES:
                try:
                    SystemHelper.run_command(
                        f"apt-get -y install {packages_str}", suppress_output=False
                    )
                    return True
                except AptLockError as e:
                    attempts += 1
                    error = e
                    sleep(PackageHelper.RETRY_DELAY)

            raise error
        else:
            if description:
                click.echo(f"   ✓ {description} already installed")
            else:
                click.echo(f"   ✓ All packages ({', '.join(packages)}) already installed")
            return False


class SecretsManager:
    """Helper class for managing service secrets"""

    def __init__(self, user: str):
        """
        Initialize SecretsManager

        Args:
            user: The system user for ArPI (e.g., 'argus')
        """
        self.user = user
        self.secrets_file = f"/home/{user}/server/secrets.env"
        self._secrets = {}
        self._load_existing_secrets()

    def _load_existing_secrets(self):
        """Load existing secrets from secrets.env file if it exists"""
        if not os.path.exists(self.secrets_file):
            return

        try:
            with open(self.secrets_file, "r") as f:
                for line in f:
                    line = line.strip()
                    # Skip comments and empty lines
                    if not line or line.startswith("#"):
                        continue
                    # Parse KEY="value" or KEY=value format
                    if "=" in line:
                        key, value = line.split("=", 1)
                        # Remove quotes if present
                        value = value.strip().strip('"').strip("'")
                        self._secrets[key] = value
        except Exception as e:
            click.echo(f"   ⚠️ Warning: Could not read secrets file: {e}")

    def _get_or_generate_secret(self, key: str) -> str:
        """
        Get secret by key, generating if it doesn't exist

        Args:
            key: The secret key to retrieve

        Returns:
            str: The secret value
        """
        if key in self._secrets:
            return self._secrets[key]

        # generate new password
        password = SecurityHelper.generate_password()
        self._secrets[key] = password
        return password

    def get_mqtt_password(self) -> str:
        """
        Get MQTT password, generating if it doesn't exist

        Returns:
            str: The MQTT password
        """
        return self._get_or_generate_secret("ARGUS_MQTT_PASSWORD")

    def get_mqtt_reader_password(self) -> str:
        """
        Get MQTT reader password, generating if it doesn't exist

        Returns:
            str: The MQTT reader password
        """
        return self._get_or_generate_secret("ARGUS_READER_MQTT_PASSWORD")


class ServiceHelper:
    """Helper class for systemd service operations"""

    @staticmethod
    def start_service(service: str):
        """Start systemd service"""
        SystemHelper.run_command(f"systemctl start {service}")

    @staticmethod
    def enable_service(service: str):
        """Enable systemd service"""
        SystemHelper.run_command(f"systemctl enable {service}")

    @staticmethod
    def restart_service(service: str):
        """Restart systemd service"""
        SystemHelper.run_command(f"systemctl restart {service}")

    @staticmethod
    def stop_service(service: str, ignore_errors: bool = True):
        """Stop systemd service"""
        try:
            SystemHelper.run_command(f"systemctl stop {service}", check=not ignore_errors)
        except Exception:
            if not ignore_errors:
                raise

    @staticmethod
    def is_raspberry_pi() -> bool:
        """Check if the system is a Raspberry Pi"""
        try:
            with open("/proc/device-tree/model", "r") as f:
                model = f.read().lower()
                return "raspberry pi" in model
        except Exception:
            return False

    @staticmethod
    def disable_service(service: str, ignore_errors: bool = True):
        """Disable systemd service"""
        try:
            SystemHelper.run_command(f"systemctl disable {service}", check=not ignore_errors)
        except Exception:
            if not ignore_errors:
                raise
