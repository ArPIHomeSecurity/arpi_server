import os
import tempfile
import click

from installer.helpers import SystemHelper, PackageHelper, ServiceHelper
from installer.installers.base import BaseInstaller, InstallerConfig

ETC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "etc")


class HardwareInstaller(BaseInstaller):
    """Installer for hardware components (RTC, GSM, WiringPi)"""

    def __init__(self, config: InstallerConfig):
        super().__init__(config)
        self._board_version = config.board_version
        self._config_txt = "/boot/firmware/config.txt"

    def setup_rtc_hardware(self):
        """Install and configure RTC (DS1307) hardware"""
        click.echo("   🕐 Setting up RTC hardware...")

        # Install i2c-tools
        PackageHelper.install_packages(["i2c-tools"])

        # Configure device tree overlay
        if os.path.exists(self._config_txt) and not SystemHelper.file_contains_text(
            self._config_txt, "dtoverlay=i2c-rtc,ds1307"
        ):
            SystemHelper.append_to_file(self._config_txt, "\ndtoverlay=i2c-rtc,ds1307\n")
            click.echo("   ✓ RTC overlay configured")

        # Copy RTC cron job (matching bash script)
        rtc_cron_source = f"{ETC_DIR}/cron/hwclock"
        if os.path.exists(rtc_cron_source):
            SystemHelper.run_command(f"cp {rtc_cron_source} /etc/cron.d/")
            SystemHelper.run_command("chmod 644 /etc/cron.d/hwclock")
            click.echo("   ✓ RTC cron job configured")
        else:
            click.echo(f"   ⚠️ RTC cron job file not found at {rtc_cron_source}")

    def setup_gsm_hardware(self):
        """Install and configure GSM module"""
        click.echo("   📱 Setting up GSM hardware...")

        # Disable serial getty services
        services = ["serial-getty@ttyAMA0.service", "serial-getty@ttyS0.service"]
        for service in services:
            ServiceHelper.stop_service(service)
            ServiceHelper.disable_service(service)

        # Configure boot command line
        cmdline_file = "/boot/firmware/cmdline.txt"
        if os.path.exists(cmdline_file) and SystemHelper.file_contains_text(
            cmdline_file, "console=serial0,115200"
        ):
            with open(cmdline_file, "r") as f:
                content = f.read().replace("console=serial0,115200 ", "")

            SystemHelper.write_file(cmdline_file, content)
            click.echo("   ✓ Console removed from boot command line")

        # Configure UART and Bluetooth settings
        if os.path.exists(self._config_txt):
            additions = []
            if not SystemHelper.file_contains_text(self._config_txt, "enable_uart=1"):
                additions.extend(["\n# Enable UART", "enable_uart=1", "dtoverlay=uart0"])
            else:
                click.echo("   ✓ UART already enabled")

            if not SystemHelper.file_contains_text(self._config_txt, "dtoverlay=disable-bt"):
                additions.extend(["dtoverlay=disable-bt", "dtoverlay=miniuart-bt"])
            else:
                click.echo("   ✓ Bluetooth already disabled")

            if additions:
                SystemHelper.append_to_file(self._config_txt, "\n".join(additions) + "\n")
                click.echo("   ✓ UART and Bluetooth configured")
                self.infos.append("config.txt changed, reboot required!")
                self.needs_reboot = True

        # Disable hciuart service
        ServiceHelper.stop_service("hciuart")
        ServiceHelper.disable_service("hciuart")

    def setup_spi(self):
        """Enable SPI interface"""
        click.echo("   🔧 Enabling SPI interface...")

        if self._board_version == 3:
            # enable SPI for board version 3
            if os.path.exists(self._config_txt) and not SystemHelper.file_contains_text(
                self._config_txt, r"^dtparam=spi=on$", regex=True
            ):
                SystemHelper.append_to_file(self._config_txt, "\ndtparam=spi=on\n")
                self.needs_reboot = True
                click.echo("   ✓ SPI interface enabled")
        elif self._board_version == 2:
            # disable SPI for board version 2
            if os.path.exists(self._config_txt) and SystemHelper.file_contains_text(
                self._config_txt, "dtparam=spi=on"
            ):
                SystemHelper.remove_from_file(self._config_txt, "dtparam=spi=on")
                self.needs_reboot = True
                click.echo("   ✓ SPI interface disabled")
        else:
            click.echo(f"   ⚠️ Unknown board version: {self._board_version}")
            self.warnings.append(f"Unknown board version: {self._board_version}")

    def install_wiringpi(self):
        """Install WiringPi library"""
        click.echo("   🔌 Installing WiringPi...")

        # Check if WiringPi is already installed
        try:
            result = SystemHelper.run_command("gpio -v", check=False, capture=True)
            if result.returncode == 0:
                click.echo("   ✓ WiringPi already installed")
                return
        except Exception:
            pass

        # Clone and build WiringPi
        with tempfile.TemporaryDirectory() as temp_dir:
            wiringpi_dir = os.path.join(temp_dir, "wiringpi")

            try:
                SystemHelper.run_command(
                    f"git clone https://github.com/WiringPi/WiringPi.git {wiringpi_dir}"
                )
                SystemHelper.run_command("./build", cwd=wiringpi_dir)
                SystemHelper.run_command("ldconfig")
                click.echo("   ✓ WiringPi installed successfully")
            except Exception as e:
                click.echo(f"    ⚠️ WARNING: WiringPi installation failed: {e}")
                self.warnings.append(f"WiringPi installation failed: {e}")

    def install(self):
        """Install hardware components"""
        self.setup_rtc_hardware()
        self.setup_gsm_hardware()
        self.setup_spi()
        self.install_wiringpi()

    def get_status(self) -> dict:
        """Get hardware component status"""
        return {
            "i2c_tools installed": PackageHelper.is_package_installed("i2c-tools"),
            "SPI enabled": SystemHelper.file_contains_text(
                "/boot/firmware/config.txt", r"^dtparam=spi=on$", regex=True
            ),
            "RTC configured": SystemHelper.file_contains_text(
                "/boot/firmware/config.txt", "dtoverlay=i2c-rtc,ds1307"
            ),
            "GSM UART configured": SystemHelper.file_contains_text(
                "/boot/firmware/config.txt", "enable_uart=1"
            ),
            "WiringPi available": SystemHelper.run_command("gpio -v", check=False).returncode == 0,
        }
