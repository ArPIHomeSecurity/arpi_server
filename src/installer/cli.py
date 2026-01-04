#!/usr/bin/env python3
"""
ArPI Installation and Management Tool - CLI Module

This module contains all the CLI logic for the ArPI installation tool.
It can be imported and used from multiple entry points.
"""

import json
import logging
import os
import sys
import traceback
from datetime import datetime

import click

from installer.helpers import SecretsManager
from installer.installers import (
    InstallerConfig,
    BaseInstaller,
    CertbotInstaller,
    DatabaseInstaller,
    HardwareInstaller,
    MqttInstaller,
    NginxInstaller,
    ServiceInstaller,
    SystemInstaller,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# installers in execution order
INSTALLERS = {
    "system": SystemInstaller,
    "hardware": HardwareInstaller,
    "database": DatabaseInstaller,
    "nginx": NginxInstaller,
    "mqtt": MqttInstaller,
    "certbot": CertbotInstaller,
    "service": ServiceInstaller,
}

COMPONENTS = INSTALLERS.keys()


class ArpiOrchestrator:
    """Main orchestrator for ArPI installation components"""

    def __init__(self):
        self.config = InstallerConfig(
            postgresql_version=os.getenv("POSTGRESQL_VERSION"),
            nginx_version=os.getenv("NGINX_VERSION", "1.28.0"),
            db_name=os.getenv("ARGUS_DB_NAME", "argus"),
            data_set_name=os.getenv("DATA_SET_NAME", ""),
            user=os.getenv("ARGUS_USER", "argus"),
            board_version=int(os.getenv("BOARD_VERSION", "3")),
            secrets_manager=SecretsManager(os.getenv("ARGUS_USER", "argus")),
            use_simulator=os.getenv("USE_SIMULATOR", "false").lower() == "true",
            verbose=False,
        )
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
def get_selected_installers(selected):
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
    ctx.obj["orchestrator"].config.verbose = verbose

    # cli argument has priority over environment variable
    if board_version is not None:
        ctx.obj["orchestrator"].config.board_version = board_version

    if ctx.obj["orchestrator"].config.board_version not in [2, 3]:
        # read board version from input
        click.echo("Please specify a valid board version (2 or 3):")
        while True:
            try:
                version = int(input("Board version (2 or 3): ").strip())
                if version in [2, 3]:
                    ctx.obj["orchestrator"].config.board_version = version
                    break
                else:
                    click.echo("Invalid input. Please enter 2 or 3.")
            except ValueError:
                click.echo("Invalid input. Please enter a number (2 or 3).")


@cli.command()
@click.argument("component", nargs=-1, type=click.Choice(COMPONENTS), required=False)
@click.pass_context
def bootstrap(ctx, component):
    """
    Install the full environment for the server or a specific component
    """
    ctx.ensure_object(dict)
    start_time = datetime.now()
    click.echo("🚀 Starting ArPI bootstrap...")
    click.echo(f"Bootstrap started at {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    components = get_selected_installers(component)
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
            click.echo(f"✓ '{comp}' installed successfully.")
        except Exception as e:
            click.echo(f"⚠️ Failed to install '{comp}': {type(e).__name__}: {str(e)}")
            click.echo(traceback.format_exc())
            installer.warnings.append(f"Installation failed: {type(e).__name__}: {str(e)}")

    click.echo(f"Bootstrap completed in {datetime.now() - start_time}")

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
                click.echo(f"⚠️ Warning during {comp} bootstrap: {warning}")

            for info in installer.infos:
                click.echo(f"ℹ️ Info during {comp} bootstrap: {info}")

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
def post_install(ctx, component):
    """
    Run post-installation tasks such as database migrations
    """
    ctx.ensure_object(dict)
    start_time = datetime.now()
    click.echo("🚀 Starting ArPI post-installation...")
    click.echo(f"Post-installation started at {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    components = get_selected_installers(component)
    orchestrator: ArpiOrchestrator = ctx.obj["orchestrator"]
    click.echo("Configurations: \n%s" % json.dumps(orchestrator.config, indent=4, cls=JsonEncoder))
    for comp in components:
        installer = orchestrator.get_installer(comp)
        if not installer:
            continue

        try:
            if hasattr(installer, "post_install"):
                click.echo("=====================================")
                click.echo(f"Installing {comp}...")
                installer.post_install()
                click.echo(f"✓ '{comp}' post-installation completed successfully.")
            else:
                click.echo(f"'{comp}' installer does not have post-installation steps, skipping.")
        except Exception as e:
            click.echo(f"⚠️ Failed to install '{comp}': {type(e).__name__}: {str(e)}")
            click.echo(traceback.format_exc())
            installer.warnings.append(f"Installation failed: {type(e).__name__}: {str(e)}")

    click.echo(f"Post-installation completed in {datetime.now() - start_time}")

    if any(
        orchestrator.get_installer(comp).warnings
        for comp in components
        if orchestrator.get_installer(comp)
    ):
        click.echo("=====================================")
        click.echo("Post-installation completed with warnings:")
        for comp in components:
            installer = orchestrator.get_installer(comp)
            for warning in installer.warnings:
                click.echo(f"⚠️ Warning during {comp} post-installation: {warning}")
            for info in installer.infos:
                click.echo(f"ℹ️ Info during {comp} post-installation: {info}")

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
    components = get_selected_installers(component)
    orchestrator: ArpiOrchestrator = ctx.obj["orchestrator"]
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
            if ctx.obj["orchestrator"].config.verbose:
                traceback.print_exc()


def status_standalone():
    """
    Standalone entry point for argus-status command.
    This wraps the status command with proper CLI context initialization.
    """
    # check root privileges
    if os.geteuid() != 0:
        click.echo("⚠️ This command must be run as root. Please rerun with sudo or as root user.")
        sys.exit(1)

    cli(["status"] + sys.argv[1:], standalone_mode=True)


if __name__ == "__main__":
    cli()
