#!/usr/bin/env python3
import logging
import os
import re
import subprocess
from enum import Enum

from utils.constants import LOG_SC_ACCESS

SSH_PATH = "~/.ssh"
AUTHORIZED_KEYS_PATH = "~/.ssh/authorized_keys"


class KeyTypes(str, Enum):
    RSA = "rsa"
    ECDSA = "ecdsa"
    ED25519 = "ed25519"


class SSHKeyManager:
    def __init__(self) -> None:
        super(SSHKeyManager, self).__init__()
        self._logger = logging.getLogger(LOG_SC_ACCESS)
        self.authorized_keys_path = os.path.expanduser(AUTHORIZED_KEYS_PATH)

    def generate_ssh_keys(
        self, key_type: KeyTypes, key_name: str, passphrase: str = ""
    ) -> tuple[str, str]:
        """
        Generate SSH keys

        Arguments:
            key_type: The type of the key (rsa, ecdsa, ed25519)
            key_name: The name of the key
            passphrase: The passphrase for the key
        
        Returns:
            A tuple containing the private key and public key as strings
        """
        self._logger.info("Generating SSH keys %s with name %s", key_type, key_name)
        key_path = "/tmp/id_rsa"

        if os.path.exists(key_path):
            os.remove(key_path)
        if os.path.exists(f"{key_path}.pub"):
            os.remove(f"{key_path}.pub")

        if key_type == KeyTypes.RSA.value:
            os.system(
                f"ssh-keygen -q -t {key_type} -b 4096 -f {key_path} -C {key_name} -N '{passphrase}'"
            )
        elif key_type == KeyTypes.ED25519.value:
            os.system(f"ssh-keygen -q -t {key_type} -f {key_path} -C {key_name} -N '{passphrase}'")
        self._logger.info("SSH keys generated")

        with open(key_path, "r", encoding="utf-8") as key_file:
            private_key = key_file.read()
        with open(f"{key_path}.pub", "r", encoding="utf-8") as key_file:
            public_key = key_file.read()

        return private_key, public_key

    def set_public_key(self, public_key: str, key_name: str):
        """
        Add public key to authorized_keys or replace existing key

        Arguments:
            public_key: The public key string
            key_name: The name of the key to identify it in authorized_keys
        """
        if len(public_key.split(" ")) == 2:
            self._logger.debug(
                "Public key does not contain key name, using key name from argument: %s",
                key_name,
            )
            public_key = f"{public_key} {key_name}"

        if len(public_key.split(" ")) == 3:
            if key_name != public_key.split(" ")[2]:
                self._logger.warning(
                    "Key name does not match, %s != %s", key_name, public_key.split(" ")[2]
                )

            self._logger.debug("Updating key name in public key")
            public_key = f"{public_key.split(' ')[0]} {public_key.split(' ')[1]} {key_name}"

        # create authorized_keys if not exists
        if not os.path.exists(os.path.expanduser(self.authorized_keys_path)):
            if not os.path.exists(os.path.expanduser(SSH_PATH)):
                os.mkdir(os.path.expanduser(SSH_PATH))
            os.mknod(self.authorized_keys_path)

        if self.check_key_exists(key_name):
            self._logger.info(
                "Replacing public key (new) '%s...' with name %s",
                public_key.split(" ")[1][:10],
                key_name,
            )
            os.system(f'sed -i "/{key_name}/d" {self.authorized_keys_path}')
        else:
            self._logger.info(
                "Adding public key '%s...' with name %s",
                public_key.split(" ")[1][:10],
                key_name,
            )

        os.system(f'echo "{public_key}" >> {os.path.expanduser(self.authorized_keys_path)}')

    def remove_public_key(self, key_name: str):
        """
        Remove public key from authorized_keys

        Arguments:
            key_name: The name of the key to identify it in authorized_keys
        """
        self._logger.info("Removing public key with name %s", key_name)
        subprocess.run(["sed", "-i", f"/{key_name}/d", self.authorized_keys_path], check=True)

    def check_key_exists(self, key_name: str):
        """
        Check if key exists in authorized_keys
        """
        self._logger.debug("Checking if key with name %s exists", key_name)
        if not os.path.exists(self.authorized_keys_path):
            self._logger.debug("%s does not exist", self.authorized_keys_path)
            return False

        with open(self.authorized_keys_path, "r", encoding="utf-8") as key_file:
            for line in key_file:
                if key_name in line:
                    self._logger.debug("Key with name %s exists", key_name)
                    return True

        self._logger.debug("Key with name %s does not exist", key_name)
        return False

    @staticmethod
    def get_key_name(user_id: int, user_name: str):
        """
        Convert user name to key name
        """
        # Remove trailing and leading whitespace
        s = user_name.strip()

        # Remove non-word characters (everything except numbers and letters)
        s = re.sub(r"\W", "_", s)

        # Replace all runs of whitespace with a single underscore
        s = re.sub(r"\s+", "_", s)

        s += f"_{user_id}"

        # add hostname
        s += f"@{os.uname().nodename}"

        return s
