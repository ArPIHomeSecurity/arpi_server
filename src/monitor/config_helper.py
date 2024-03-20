
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
    session = Session()
    dyndns_data = session.query(Option).filter_by(name="network", section="dyndns").first()
    session.close()

    if dyndns_data:
        noip_config = json.loads(dyndns_data.value)
        return DyndnsConfig(**noip_config)


@dataclass
class SshConfig:
    ssh: bool
    ssh_restrict_local_network: bool


def load_ssh_config() -> SshConfig:
    session = Session()
    ssh_config = session.query(Option).filter_by(name="network", section="access").first()
    session.close()

    if ssh_config:
        ssh_config = json.loads(ssh_config.value)
        return SshConfig(**ssh_config)
