#!/usr/bin/env python3
"""
ArPI Installation and Management Tool
A comprehensive Python-based replacement for bash installation scripts

Based on the original ArPI bash modules:
- System packages (zsh, oh-my-zsh, development tools)
- Hardware setup (RTC, GSM, WiringPi)  
- Database (PostgreSQL installation and configuration)
- NGINX (compilation from source with SSL)
- MQTT (Mosquitto broker with authentication)
- Certbot (SSL certificate management)
- Service setup (systemd services, secrets management)
"""

import click
import logging
import os

from install.helpers import SecurityHelper, SystemHelper
from install.installers import (
    BaseInstaller,
    SystemInstaller,
    HardwareInstaller,
    DatabaseInstaller,
    NginxInstaller,
    MqttInstaller,
    CertbotInstaller,
    ServiceInstaller
)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s: %(message)s')
logger = logging.getLogger(__name__)


class ArpiOrchestrator:
    """Main orchestrator for ArPI installation components"""
    
    def __init__(self):
        self.config = {
            "postgresql_version": os.getenv("POSTGRESQL_VERSION", "15"),
            "nginx_version": os.getenv("NGINX_VERSION", "1.24.0"),
            "db_username": os.getenv("ARGUS_DB_USERNAME", "argus"),
            "db_name": os.getenv("ARGUS_DB_NAME", "argus"),
            "dhparam_file": os.getenv("DHPARAM_FILE", ""),
            "db_password": os.getenv("ARGUS_DB_PASSWORD", ""),
            "salt": os.getenv("SALT", ""),
            "secret": os.getenv("SECRET", ""),
            "mqtt_password": os.getenv("ARGUS_MQTT_PASSWORD", ""),
            "user": os.getenv("ARGUS_USER", "argus")
        }

        click.echo("Installation Configuration:")
        for key, value in self.config.items():
            display_value = value
            if all(x in key.lower() for x in ["password", "secret", "salt"]) and value:
                if not value:
                    display_value = value
                else:
                    display_value = "****"
            click.echo(f"   {key}: {display_value}")

        # Initialize component installers
        self.system_installer = SystemInstaller(self.config)
        self.hardware_installer = HardwareInstaller(self.config)
        self.database_installer = DatabaseInstaller(self.config)
        self.nginx_installer = NginxInstaller(self.config)
        self.mqtt_installer = MqttInstaller(self.config)
        self.certbot_installer = CertbotInstaller(self.config)
        self.service_installer = ServiceInstaller(self.config)
    
    def get_installer(self, component: str) -> BaseInstaller:
        """Get installer for specific component"""
        installers = {
            "system": self.system_installer,
            "hardware": self.hardware_installer,
            "database": self.database_installer,
            "nginx": self.nginx_installer,
            "mqtt": self.mqtt_installer,
            "certbot": self.certbot_installer,
            "services": self.service_installer
        }
        return installers.get(component)
    
    def get_all_status(self) -> dict:
        """Get status of all components"""
        return {
            "system": self.system_installer.get_status(),
            "hardware": self.hardware_installer.get_status(),
            "database": self.database_installer.get_status(),
            "nginx": self.nginx_installer.get_status(),
            "mqtt": self.mqtt_installer.get_status(),
            "certbot": self.certbot_installer.get_status(),
            "services": self.service_installer.get_status()
        }
    
    def get_warnings(self) -> list:
        """Get all warnings from installers"""
        warnings = []
        for installer in [self.system_installer, self.hardware_installer, self.database_installer,
                          self.nginx_installer, self.mqtt_installer, self.certbot_installer,
                          self.service_installer]:
            warnings.extend(installer.warnings)
        return warnings

@click.group()
@click.pass_context
def cli(ctx):
    """ArPI Installation and Management Tool"""
    ctx.ensure_object(dict)
    ctx.obj['orchestrator'] = ArpiOrchestrator()

@cli.command()
@click.pass_context
def install_system(ctx):
    """Install and configure system packages"""
    orchestrator: ArpiOrchestrator = ctx.obj['orchestrator']
    
    click.echo("🔧 Installing system...")
    orchestrator.system_installer.install()
    click.echo("✅ System installation complete")

@cli.command()
@click.pass_context
def install_hardware(ctx):
    """Install and configure hardware components (RTC, GSM, WiringPi)"""
    orchestrator: ArpiOrchestrator = ctx.obj['orchestrator']
    
    click.echo("🔧 Installing hardware components...")
    orchestrator.hardware_installer.install()
    click.echo("✅ Hardware installation complete")

@cli.command()
@click.pass_context
def install_database(ctx):
    """Install and configure PostgreSQL database"""
    orchestrator: ArpiOrchestrator = ctx.obj['orchestrator']
    
    click.echo("🗄️ Installing database...")
    orchestrator.database_installer.install()
    click.echo("✅ Database installation complete")

@cli.command()
@click.pass_context
def install_nginx(ctx):
    """Install and configure NGINX web server"""
    orchestrator: ArpiOrchestrator = ctx.obj['orchestrator']
    
    click.echo("🌐 Installing NGINX...")
    orchestrator.nginx_installer.install()
    click.echo("✅ NGINX installation complete")

@cli.command()
@click.pass_context
def install_mqtt(ctx):
    """Install and configure MQTT broker"""
    orchestrator: ArpiOrchestrator = ctx.obj['orchestrator']
    
    click.echo("📡 Installing MQTT broker...")
    orchestrator.mqtt_installer.install()
    click.echo("✅ MQTT installation complete")

@cli.command()
@click.pass_context
def install_certbot(ctx):
    """Install Certbot for SSL certificate management"""
    orchestrator: ArpiOrchestrator = ctx.obj['orchestrator']
    
    click.echo("🔒 Installing Certbot...")
    orchestrator.certbot_installer.install()
    click.echo("✅ Certbot installation complete")

@cli.command()
@click.pass_context
def setup_services(ctx):
    """Setup ArPI services and configurations"""
    orchestrator: ArpiOrchestrator = ctx.obj['orchestrator']
    
    click.echo("⚙️ Setting up ArPI services...")
    orchestrator.service_installer.install()
    click.echo("✅ ArPI services setup complete")

@cli.command()
@click.pass_context
def full_install(ctx):
    """Run complete ArPI installation"""
    click.echo("🚀 Starting full ArPI installation...")

    current_user_process = SystemHelper.run_command("whoami", capture=True)
    click.echo(f"👤 Executing with user: {current_user_process.stdout}")
    ctx.invoke(install_system)
    ctx.invoke(install_hardware)
    ctx.invoke(install_database)
    ctx.invoke(install_nginx)
    ctx.invoke(install_mqtt)
    ctx.invoke(install_certbot)
    ctx.invoke(setup_services)

    warnings = ctx.obj['orchestrator'].get_warnings()
    if warnings:
        click.echo("\n⚠️ Installation completed with warnings:")
        for warning in warnings:
            click.echo(f"   - {warning}")
    
    click.echo("🎉 Full ArPI installation complete!")

@cli.command()
@click.pass_context
def status(ctx):
    """Check status of ArPI components"""
    orchestrator: ArpiOrchestrator = ctx.obj['orchestrator']
    
    click.echo("📊 ArPI System Status:")
    
    all_status = orchestrator.get_all_status()
    
    for component, status in all_status.items():
        click.echo(f"\n{component.upper()}:")
        for key, value in status.items():
            status_icon = "✅" if value else "❌"
            click.echo(f"   {status_icon} {key}")

@cli.command()
@click.option(
    "--restart",
    is_flag=True,
    default=False,
    help="Restart the argus_server service after installation."
)
def install_server_component(ctx, restart):
    """
    Install the server component from /tmp/server to /home/argus/server on the remote host.
    """
    orchestrator: ArpiOrchestrator = ctx.obj['orchestrator']
    src = "/tmp/server"
    dst = f"/home/{orchestrator.username}/server"

    click.echo(f"Copying {src} to {dst} ...")
    SystemHelper.copy_tree(src, dst)
    click.echo("Copy finished.")

    scripts_dir = os.path.join(dst, "scripts")
    if os.path.isdir(scripts_dir):
        for fname in os.listdir(scripts_dir):
            fpath = os.path.join(scripts_dir, fname)
            if os.path.isfile(fpath):
                os.chmod(fpath, 0o755)

    click.echo("Setting ownership to argus:argus ...")
    SecurityHelper.chown_recursive(dst, "argus", "argus")

    if restart:
        click.echo("Restarting argus_server service...")
        SystemHelper.run_command("systemctl restart argus_server.service", check=False)

    click.echo("Server component installation complete.")

if __name__ == "__main__":
    cli()
