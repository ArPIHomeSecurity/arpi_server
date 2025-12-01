from abc import ABC, abstractmethod
from dataclasses import dataclass
import os

import click

from installer.helpers import SecretsManager

@dataclass
class InstallerConfig:
    python_version: str
    postgresql_version: str
    nginx_version: str
    db_name: str
    data_set_name: str
    user: str
    board_version: int
    secrets_manager: SecretsManager
    verbose: bool = False


class BaseInstaller(ABC):
    """Base class for all component installers"""

    shared_directory: str | None = None
    config_directory: str | None = None

    def __init__(self, config: InstallerConfig):
        self.warnings = []
        self.infos = []
        self.needs_reboot = False
        if BaseInstaller.shared_directory is None:
            BaseInstaller.shared_directory = self.get_shared_directory(config.user)
        if BaseInstaller.config_directory is None:
            BaseInstaller.config_directory = self.get_config_directory(config.user)

    @abstractmethod
    def install(self):
        """Install the component"""
        pass

    @abstractmethod
    def get_status(self) -> dict:
        """Get component status information"""
        pass

    @staticmethod
    def get_shared_directory(username) -> str | None:
        """
        Find the installed shared directory
        """
        if username:
            possible_paths = [
                os.path.expanduser(f"~{username}/.local/share/arpi-server/"),
                "/usr/local/share/arpi-server/",
                "/usr/share/arpi-server/",
            ]
        else:
            possible_paths = [
                os.path.expanduser("~/.local/share/arpi-server/"),
                "/usr/local/share/arpi-server/",
                "/usr/share/arpi-server/",
            ]
        
        for path in possible_paths:
            click.echo(f"Checking for shared directory at: {path}")
            if os.path.exists(path):
                return path
        
        return None

    @staticmethod
    def get_config_directory(username) -> str | None:
        """
        Find the installed config directory
        """
        if username:
            possible_paths = [
                os.path.expanduser(f"~{username}/.local/etc/arpi-server/"),
                "/etc/arpi-server/",
            ]
        else:
            possible_paths = [
                os.path.expanduser("~/.local/etc/arpi-server/"),
                "/etc/arpi-server/",
            ]
        
        for path in possible_paths:
            click.echo(f"Checking for config directory at: {path}")
            if os.path.exists(path):
                return path
        
        return None