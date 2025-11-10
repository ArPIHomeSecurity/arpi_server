#!/usr/bin/env python3
"""
ArPI Installation and Management Tool - CLI Module

This module contains all the CLI logic for the ArPI installation tool.
It can be imported and used from multiple entry points.
"""

import json
import logging
import os
import traceback
from datetime import datetime

import click

from installer.helpers import SecurityHelper, SystemHelper, SecretsManager
from installer.installers import (
    BaseInstaller,
    CertbotInstaller,
    DatabaseInstaller,
    HardwareInstaller,
    MqttInstaller,
    NginxInstaller,
    ServerInstaller,
    SystemInstaller,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

INSTALLERS = {
    "system": SystemInstaller,
    "hardware": HardwareInstaller,
    "database": DatabaseInstaller,
    "nginx": NginxInstaller,
    "mqtt": MqttInstaller,
    "certbot": CertbotInstaller,
    "services": ServerInstaller,
}

COMPONENTS = INSTALLERS.keys()


class ArpiOrchestrator:
    """Main orchestrator for ArPI installation components"""

    def __init__(self):
        self.config = {
            "python_version": os.getenv("PYTHON_VERSION", "3.11"),
            "postgresql_version": os.getenv("POSTGRESQL_VERSION", "15"),
            "nginx_version": os.getenv("NGINX_VERSION", "1.28.0"),
            "db_name": os.getenv("ARGUS_DB_NAME", "argus"),
            "data_set_name": os.getenv("DATA_SET_NAME", "prod"),
            "dhparam_file": os.getenv("DHPARAM_FILE", "arpi_dhparam.pem"),
            "deploy_simulator": os.getenv("DEPLOY_SIMULATOR", "false"),
            "user": os.getenv("ARGUS_USER", "argus"),
            "install_source": os.getenv("INSTALL_SOURCE", "/tmp/server"),
            "board_version": int(os.getenv("BOARD_VERSION", "3")),
            "secrets_manager": SecretsManager(os.getenv("ARGUS_USER", "argus")),
        }
        self._installer_cache = {}

    def get_installer(self, component: str) -> BaseInstaller:
        """Factory method to get the appropriate installer, with caching"""
        if component in self._installer_cache:
            return self._installer_cache[component]

        installer_class = INSTALLERS.get(component)
        if not installer_class:
            raise ValueError(f"Unknown component: {component}")

        try:
            self._installer_cache[component] = installer_class(self.config)
        except ValueError as e:
            click.echo(f"⚠️ Could not initialize installer for {component}: {e}")
            return None

        return self._installer_cache[component]


# --- Helper Functions ---
def get_selected_components(selected):
    """
    Determine which components to install/status based on user input
    """
    if not selected:
        return COMPONENTS

    return list(selected)


class JsonEncoder(json.JSONEncoder):
    """Custom JSON encoder to handle non-serializable objects"""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return str(obj)


# --- CLI Implementation ---
@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output (debug logging)")
@click.option("--board-version", type=int, default=None, help="Hardware board version (2 or 3)")
@click.pass_context
def cli(ctx, verbose, board_version):
    """ArPI Installation and Management Tool"""
    ctx.ensure_object(dict)

    # Set logging level based on verbose flag
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Verbose logging enabled")

    ctx.obj["orchestrator"] = ArpiOrchestrator()
    ctx.obj["verbose"] = verbose

    # cli argument has priority over environment variable
    if board_version is not None:
        ctx.obj["orchestrator"].config["board_version"] = board_version

    if ctx.obj["orchestrator"].config["board_version"] not in [2, 3]:
        # read board version from input
        click.echo("Please specify a valid board version (2 or 3):")
        while True:
            try:
                version = int(input("Board version (2 or 3): ").strip())
                if version in [2, 3]:
                    ctx.obj["orchestrator"].config["board_version"] = version
                    ctx.obj["board_version"] = version
                    break
                else:
                    click.echo("Invalid input. Please enter 2 or 3.")
            except ValueError:
                click.echo("Invalid input. Please enter a number (2 or 3).")


@cli.command()
@click.argument("component", nargs=-1, type=click.Choice(COMPONENTS), required=False)
@click.pass_context
def install(ctx, component):
    """
    Install the full environment for the server or a specific component
    """
    ctx.ensure_object(dict)
    start_time = datetime.now()
    click.echo("🚀 Starting ArPI installation...")
    click.echo(f"Installation started at {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    components = get_selected_components(component)
    orchestrator: ArpiOrchestrator = ctx.obj["orchestrator"]
    click.echo("Configurations: \n%s" % json.dumps(orchestrator.config, indent=4, cls=JsonEncoder))
    for comp in components:
        installer = orchestrator.get_installer(comp)
        if not installer:
            continue

        click.echo("=====================================")
        click.echo(f"Installing {comp}...")
        try:
            installer.install()
            click.echo(f"✓ {comp} installed successfully.")
        except Exception as e:
            click.echo(f"⚠️ Failed to install {comp}: {e}")
            installer.warnings.append(f"Installation failed: {e}")

    click.echo(f"Installation completed in {datetime.now() - start_time}")

    if any(
        orchestrator.get_installer(comp).warnings
        for comp in components
        if orchestrator.get_installer(comp)
    ):
        click.echo("=====================================")
        click.echo("Installation completed with warnings:")
        for comp in components:
            installer = orchestrator.get_installer(comp)
            for warning in installer.warnings:
                click.echo(f"⚠️ Warning during {comp} installation: {warning}")

            for info in installer.infos:
                click.echo(f"ℹ️ Info during {comp} installation: {info}")

    if any(
        orchestrator.get_installer(comp).needs_reboot
        for comp in components
        if orchestrator.get_installer(comp)
    ):
        click.echo("=====================================")
        click.echo("🔄 A system reboot is required to apply all changes.")
        click.echo("Please reboot the system at your earliest convenience.")


@cli.command()
@click.argument("component", nargs=-1, type=click.Choice(COMPONENTS), required=False)
@click.pass_context
def status(ctx, component):
    """
    Display the status of the full environment for the server or a specific component
    """
    ctx.ensure_object(dict)
    components = get_selected_components(component)
    orchestrator = ctx.obj["orchestrator"]
    for comp in components:
        installer = orchestrator.get_installer(comp)
        if not installer:
            continue

        click.echo(f"\nStatus for {comp}:")
        try:
            status = installer.get_status()
            for k, v in status.items():
                status_emoji = {None: "❓", True: "✅", False: "❌"}.get(v, "❓")
                click.echo(f"  {k}: {status_emoji}")
        except Exception as e:
            click.echo(f"⚠️ Failed to get status for {comp}: {e}")
            if ctx.obj["verbose"]:
                traceback.print_exc()


@cli.command()
@click.option("--restart", is_flag=True, help="Restart argus_server service after installation")
@click.option(
    "--backup", is_flag=True, help="Create a backup of the existing server code before installation"
)
@click.pass_context
def deploy_code(ctx, restart, backup):
    """
    Deploy source code of the server component from the specified source directory to the destination directory.
    """
    orchestrator: ArpiOrchestrator = ctx.obj["orchestrator"]
    src = orchestrator.config["install_source"]
    dst = f"/home/{orchestrator.config['user']}/server"

    # create diff report
    click.echo("Creating diff report...")
    excludes = ["__pycache__", "*.pyc", "secrets.env", "status.json"]
    exclude_args = " ".join([f"--exclude='{e}'" for e in excludes])
    diff_report = SystemHelper.run_command(
        f"diff -urN {exclude_args} --brief {src} {dst}", check=False, capture=True
    )
    if diff_report.stdout:
        click.echo(
            f"📝 Differences between source and destination (with excludes: {', '.join(excludes)})"
        )
        [click.echo(f"  | {line}") for line in diff_report.stdout.splitlines()]
    else:
        click.echo("No differences found between source and destination.")

    if backup:
        click.echo("Creating backup of existing server code...")
        backup_file = f"/home/{orchestrator.config['user']}/server_backup_{datetime.now().strftime('%Y%m%d_%H%M')}.tar.gz"
        # Create a compressed archive of the current server directory, but do not move or remove any files
        SystemHelper.run_command(f"tar -czf {backup_file} -C {dst} .", check=False)
        click.echo(f"Backup created at {backup_file}")

    click.echo("Cleanup server folder except secrets.env...")
    # remove all files and folders in dst except secrets.env at the top level
    SystemHelper.run_command(
        f"find '{dst}' -mindepth 1 -maxdepth 1 ! -name 'secrets.env' -exec rm -rf -- '{{}}' +",
        check=False,
    )

    click.echo(f"Copying {src} to {dst} (without overwriting existing files)...")
    SystemHelper.run_command(f"cp -an '{src}/.' '{dst}/'", check=False)
    click.echo("Copy finished.")

    user = orchestrator.config["user"]
    click.echo(f"Setting ownership to {user}:{user} ...")
    SecurityHelper.set_file_permissions(dst, f"{user}:{user}", 755, recursive=True)

    # configure board version in .env
    if ctx.obj["orchestrator"].config["board_version"] not in [2, 3]:
        raise ValueError(
            f"Invalid board version={ctx.obj['orchestrator'].config['board_version']}. Must be 2 or 3."
        )

    env_file = os.path.join(dst, ".env")
    if os.path.exists(env_file):
        SystemHelper.run_command(
            f"sed -i 's/^BOARD_VERSION=.*/BOARD_VERSION={ctx.obj['orchestrator'].config['board_version']}/' '{env_file}'",
            check=False,
        )
        click.echo(
            f"Set BOARD_VERSION={ctx.obj['orchestrator'].config['board_version']} in {env_file}"
        )
    else:
        click.echo(f"   ⚠️ {env_file} not found")

    if restart:
        click.echo("Restarting argus_server service...")
        SystemHelper.run_command("systemctl restart argus_server.service", check=False)

    click.echo("✅ Server component installation complete.")
