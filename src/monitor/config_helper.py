
import json

from dataclasses import dataclass

from models import Option
from monitor.database import Session


@dataclass
class DyndnsConfig:
    username: str
    password: str
    hostname: str
    provider: str
    restrict_host: str


def load_dyndns_config() -> DyndnsConfig:
    dyndns_data = Session().query(Option).filter_by(name="network", section="dyndns").first()
    if dyndns_data:
        noip_config = json.loads(dyndns_data.value)
        return DyndnsConfig(**noip_config)


@dataclass
class SshConfig:
    ssh: bool
    ssh_from_router: bool


def load_ssh_config() -> SshConfig:
    ssh_config = Session().query(Option).filter_by(name="network", section="access").first()

    if ssh_config:
        ssh_config = json.loads(ssh_config.value)
        return SshConfig(**ssh_config)
