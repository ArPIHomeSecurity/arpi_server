
import os
import tempfile
import click

from install.helpers import SystemHelper, PackageHelper, ServiceHelper, SecurityHelper
from install.installers.base import BaseInstaller


class MqttInstaller(BaseInstaller):
    """Installer for MQTT broker"""
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.mqtt_password = config.get("mqtt_password", "")
        self.dhparam_file = config.get("dhparam_file", "")
    
    def setup_mosquitto_repository(self):
        """Setup Mosquitto repository for installation"""
        click.echo("   📡 Setting up Mosquitto repository...")
        
        # Check if repository is already configured
        sources_file = "/etc/apt/sources.list.d/mosquitto.list"
        if os.path.exists(sources_file):
            with open(sources_file, "r") as f:
                if "repo.mosquitto.org" in f.read():
                    click.echo("   ✓ Mosquitto repository already configured")
                    return
        
        # Download and add repository key
        with tempfile.TemporaryDirectory() as temp_dir:
            key_file = os.path.join(temp_dir, "mosquitto-repo.gpg")
            
            try:
                SystemHelper.run_command(f"wget -O {key_file} http://repo.mosquitto.org/debian/mosquitto-repo.gpg", cwd="/tmp")
                SystemHelper.run_command(f"apt-key add {key_file}")
            except Exception as e:
                click.echo(f"    ⚠️ WARNING: Could not add repository key: {e}")
                self.warnings.append(f"Could not add repository key: {e}")
        
        # Add repository to sources list
        SystemHelper.write_file(sources_file, "deb https://repo.mosquitto.org/debian bookworm main\n")
        
        click.echo("   ✓ Mosquitto repository configured")
    
    def install_mosquitto(self):
        """Install Mosquitto MQTT broker"""
        click.echo("   🦟 Installing Mosquitto MQTT broker...")
        
        # Setup repository first
        self.setup_mosquitto_repository()
        
        # Update package list
        PackageHelper.update_package_cache()
        
        # Install Mosquitto
        if PackageHelper.install_packages(["mosquitto"], "Mosquitto MQTT broker"):
            ServiceHelper.enable_service("mosquitto")
        
        # Ensure service is running
        if not SystemHelper.is_service_running("mosquitto"):
            ServiceHelper.start_service("mosquitto")
    
    def configure_mqtt_ssl_certificates(self):
        """Configure SSL certificates for MQTT"""
        click.echo("   🔐 Configuring MQTT SSL certificates...")
        
        # Create certs directory and copy certificates
        SystemHelper.run_command("mkdir -p /etc/mosquitto/certs")
        
        # Copy dhparam file
        SystemHelper.run_command(f"cp {self.dhparam_file} /etc/mosquitto/certs/")
        click.echo("   ✓ Copied dhparam file")
        
        # Copy SSL certificates from nginx config
        ssl_files = [
            "/tmp/server/etc/nginx/ssl/arpi_app.crt",
            "/tmp/server/etc/nginx/ssl/arpi_app.key", 
            "/tmp/server/etc/nginx/ssl/arpi_ca.crt"
        ]
        
        for ssl_file in ssl_files:
            SystemHelper.run_command(f"cp {ssl_file} /etc/mosquitto/certs/")
        
        # Set proper ownership for certs directory
        SecurityHelper.set_file_permissions("/etc/mosquitto/certs", "mosquitto:mosquitto", "755", recursive=True)
        
        click.echo("   ✓ MQTT SSL certificates configured")
    
    def configure_mqtt_configs(self):
        """Configure MQTT configuration files"""
        click.echo("   ⚙️ Configuring MQTT configuration files...")
        
        # Copy auth and logging configurations
        SystemHelper.run_command("cp /tmp/server/etc/mosquitto/auth.conf /etc/mosquitto/conf.d/")
        SystemHelper.run_command("cp /tmp/server/etc/mosquitto/logging.conf /etc/mosquitto/conf.d/")

        # Create configs-available directory and copy SSL configs
        SystemHelper.run_command("mkdir -p /etc/mosquitto/configs-available/")
        SystemHelper.run_command("cp /tmp/server/etc/mosquitto/ssl*.conf /etc/mosquitto/configs-available/")
        
        # Create symlink for SSL configuration
        SystemHelper.run_command("ln -sf /etc/mosquitto/configs-available/ssl-self-signed.conf /etc/mosquitto/conf.d/ssl.conf")
        
        click.echo("   ✓ MQTT configuration files setup complete")
    
    def configure_mqtt_authentication(self):
        """Configure MQTT authentication"""
        click.echo("   🔐 Configuring MQTT authentication...")
        
        # Generate MQTT password if not set
        if not self.mqtt_password:
            self.mqtt_password = SecurityHelper.generate_password()
            click.echo("   ✓ Generated MQTT password")
        
        # Create password file
        try:
            SystemHelper.run_command(f"mosquitto_passwd -b -c /etc/mosquitto/.passwd argus {self.mqtt_password}")
            SecurityHelper.set_file_permissions("/etc/mosquitto/.passwd", "mosquitto:mosquitto", "644")
            click.echo("   ✓ MQTT authentication configured")
        except Exception as e:
            click.echo(f"    ⚠️ WARNING: MQTT authentication setup failed: {e}")
            self.warnings.append(f"MQTT authentication setup failed: {e}")
    
    def install(self):
        """Install MQTT components"""
        self.install_mosquitto()
        self.configure_mqtt_ssl_certificates() 
        self.configure_mqtt_configs()
        self.configure_mqtt_authentication()
    
    def is_installed(self) -> bool:
        """Check if MQTT is installed"""
        return (PackageHelper.is_package_installed("mosquitto") and
                SystemHelper.is_service_running("mosquitto"))
    
    def get_status(self) -> dict:
        """Get MQTT status"""
        return {
            "mosquitto_installed": PackageHelper.is_package_installed("mosquitto"),
            "mosquitto_running": SystemHelper.is_service_running("mosquitto"),
            "mosquitto_enabled": SystemHelper.is_service_enabled("mosquitto")
        }
