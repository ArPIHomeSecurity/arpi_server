import os
import tempfile
import click

from install.helpers import SystemHelper, PackageHelper, ServiceHelper
from install.installers.base import BaseInstaller

class HardwareInstaller(BaseInstaller):
    """Installer for hardware components (RTC, GSM, WiringPi)"""
    
    def install_rtc_hardware(self):
        """Install and configure RTC (DS1307) hardware"""
        click.echo("   🕐 Setting up RTC hardware...")
        
        # Install i2c-tools
        PackageHelper.install_packages(["i2c-tools"])
        
        # Configure RTC device
        try:
            SystemHelper.run_command("echo ds1307 0x68 > /sys/class/i2c-adapter/i2c-1/new_device")
            click.echo("   ✓ RTC device configured")
        except Exception as e:
            click.echo(f"    ⚠️ WARNING: Could not configure RTC device: {e}")
            self.warnings.append(f"Could not configure RTC device: {e}")
        
        # Configure device tree overlay
        config_txt = "/boot/firmware/config.txt"
        if os.path.exists(config_txt) and not SystemHelper.file_contains_text(config_txt, "dtoverlay=i2c-rtc,ds1307"):
            SystemHelper.append_to_file(config_txt, "\ndtoverlay=i2c-rtc,ds1307\n")
            click.echo("   ✓ RTC overlay configured")
        
        # Configure kernel module
        modules_file = "/etc/modules"
        if os.path.exists(modules_file) and not SystemHelper.file_contains_text(modules_file, "rtc-ds1307"):
            SystemHelper.append_to_file(modules_file, "rtc-ds1307\n")
            click.echo("   ✓ RTC module configured")
        
        # Copy RTC cron job (matching bash script)
        if os.path.exists("/tmp/server/etc/cron/hwclock"):
            SystemHelper.run_command("cp /tmp/server/etc/cron/hwclock /etc/cron.d/")
            SystemHelper.run_command("chmod 644 /etc/cron.d/hwclock")
            click.echo("   ✓ RTC cron job configured")
        else:
            click.echo("   ⚠️ RTC cron job file not found at /tmp/server/etc/cron/hwclock")

    def install_gsm_hardware(self):
        """Install and configure GSM module"""
        click.echo("   📱 Setting up GSM hardware...")
        
        # Disable serial getty services
        services = ["serial-getty@ttyAMA0.service", "serial-getty@ttyS0.service"]
        for service in services:
            ServiceHelper.stop_service(service)
            ServiceHelper.disable_service(service)
        
        # Configure boot command line
        cmdline_file = "/boot/cmdline.txt"
        if os.path.exists(cmdline_file) and SystemHelper.file_contains_text(cmdline_file, "console=serial0,115200"):
            with open(cmdline_file, "r") as f:
                content = f.read()
            content = content.replace("console=serial0,115200 ", "")
            SystemHelper.write_file(cmdline_file, content)
            click.echo("   ✓ Console removed from boot command line")
        
        # Configure UART and Bluetooth settings
        config_txt = "/boot/firmware/config.txt"
        if os.path.exists(config_txt):
            additions = []
            if not SystemHelper.file_contains_text(config_txt, "enable_uart=1"):
                additions.extend(["\n# Enable UART", "enable_uart=1", "dtoverlay=uart0"])
            
            if not SystemHelper.file_contains_text(config_txt, "dtoverlay=disable-bt"):
                additions.extend(["dtoverlay=disable-bt", "dtoverlay=miniuart-bt"])
            
            if additions:
                SystemHelper.append_to_file(config_txt, "\n".join(additions) + "\n")
                click.echo("   ✓ UART and Bluetooth configured")
        
        # Disable hciuart service
        ServiceHelper.stop_service("hciuart")
        ServiceHelper.disable_service("hciuart")
    
    def install_wiringpi(self):
        """Install WiringPi library"""
        click.echo("   🔌 Installing WiringPi...")
        
        # Check if WiringPi is already installed
        try:
            result = SystemHelper.run_command("gpio -v", check=False, capture=True)
            if result.returncode != 0:
                click.echo("   ✓ WiringPi already installed")
                return
        except Exception:
            pass
        
        # Clone and build WiringPi
        with tempfile.TemporaryDirectory() as temp_dir:
            wiringpi_dir = os.path.join(temp_dir, "wiringpi")
            
            try:
                SystemHelper.run_command(f"git clone https://github.com/WiringPi/WiringPi.git {wiringpi_dir}")
                SystemHelper.run_command("./build", cwd=wiringpi_dir)
                SystemHelper.run_command("ldconfig")
                click.echo("   ✓ WiringPi installed successfully")
            except Exception as e:
                click.echo(f"    ⚠️ WARNING: WiringPi installation failed: {e}")
                self.warnings.append(f"WiringPi installation failed: {e}")
    
    def install(self):
        """Install hardware components"""
        self.install_rtc_hardware()
        self.install_gsm_hardware()
        self.install_wiringpi()
    
    def is_installed(self) -> bool:
        """Check if hardware components are installed"""
        return PackageHelper.is_package_installed("i2c-tools")
    
    def get_status(self) -> dict:
        """Get hardware component status"""
        return {
            "i2c_tools_installed": PackageHelper.is_package_installed("i2c-tools"),
            "rtc_configured": os.path.exists("/sys/class/i2c-adapter/i2c-1/1-0068"),
            "wiringpi_available": os.system("gpio -v > /dev/null 2>&1") == 0
        }

