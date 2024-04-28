#!/usr/bin/env python3

import argparse
import logging
import os
import subprocess
import sys

from dotenv import load_dotenv


load_dotenv()
load_dotenv("secrets.env")
sys.path.insert(0, os.getenv("PYTHONPATH"))

from constants import LOG_SC_ACCESS
from monitor.config_helper import load_ssh_config


AUTHORIZED_KEYS_PATH = "~/.ssh/authorized_keys"


class SSHKeyManager:

    def __init__(self) -> None:
        super(SSHKeyManager, self).__init__()
        self._logger = logging.getLogger(LOG_SC_ACCESS)
        self.authorized_keys_path = os.path.expanduser(AUTHORIZED_KEYS_PATH)
        self._ssh_config = load_ssh_config()
        if not self._ssh_config:
            self._logger.warning("Missing ssh settings!")

    def generate_ssh_keys(
        self, key_type: str, key_name: str, passphrase: str = ""
    ) -> tuple[str, str]:
        """
        Generate SSH keys
        """
        self._logger.info("Generating SSH keys")
        key_path = "/tmp/id_rsa"

        if os.path.exists(key_path):
            os.remove(key_path)
        if os.path.exists(f"{key_path}.pub"):
            os.remove(f"{key_path}.pub")

        if key_type == "ecdsa":
            os.system(
                f"ssh-keygen -q -t {key_type} -b 521 -f {key_path} -C {key_name} -N '{passphrase}'"
            )
        elif key_type == "rsa":
            os.system(
                f"ssh-keygen -q -t {key_type} -b 4096 -f {key_path} -C {key_name} -N '{passphrase}'"
            )
        elif key_type == "ed25519":
            os.system(
                f"ssh-keygen -q -t {key_type} -f {key_path} -C {key_name} -N '{passphrase}'"
            )
        self._logger.info("SSH keys generated")

        with open(key_path, "r", encoding="utf-8") as key_file:
            private_key = key_file.read()
        with open(f"{key_path}.pub", "r", encoding="utf-8") as key_file:
            public_key = key_file.read()

        return private_key, public_key

    def set_public_key(self, public_key: str, key_name: str):
        """
        Add public key to authorized_keys or replace existing key
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
            if not os.path.exists(os.path.expanduser("~/.ssh")):
                os.mkdir(os.path.expanduser("~/.ssh"))
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

        os.system(
            f'echo "{public_key}" >> {os.path.expanduser(self.authorized_keys_path)}'
        )

    def remove_public_key(self, key_name: str):
        """
        Remove public key from authorized_keys
        """
        self._logger.info("Removing public key with name %s", key_name)
        subprocess.run(
            ["sed", "-i", f"/{key_name}/d", self.authorized_keys_path], check=True
        )

    def check_key_exists(self, key_name: str):
        """
        Check if key exists in authorized_keys
        """
        self._logger.debug("Checking if key with name %s exists", key_name)
        with open(self.authorized_keys_path, "r", encoding="utf-8") as key_file:
            for line in key_file:
                if key_name in line:
                    self._logger.debug("Key with name %s exists", key_name)
                    return True

        self._logger.debug("Key with name %s does not exist", key_name)

    def update_password_authentication(self):
        """
        Update password authentication
        """
        self._logger.info("Updating password authentication")
        self._enable_password_authentication(self._ssh_config.password_authentication_enabled)

    def _enable_password_authentication(self, enable: bool):
        """
        Enable password authentication
        """
        if enable:
            self._logger.info("Enabling password authentication")
            os.system(
                'sed -i -E -e "s/.*PasswordAuthentication (yes|no)/PasswordAuthentication yes/g" /etc/ssh/sshd_config'
            )
        else:
            self._logger.info("Disabling password authentication")
            os.system(
                'sed -i -E -e "s/.*PasswordAuthentication (yes|no)/PasswordAuthentication no/g" /etc/ssh/sshd_config'
            )


def main():
    parser = argparse.ArgumentParser(description="Manage SSH keys.")
    parser.add_argument("--key_type", type=str, help="Type of the key to generate.")
    parser.add_argument("--key_name", type=str, help="Name of the key.")
    parser.add_argument(
        "--passphrase", type=str, default="", help="Passphrase for the key."
    )
    parser.add_argument("--public_key", type=str, help="Public key to set.")
    parser.add_argument("--remove_key", type=str, help="Remove key by 'key_name'.")
    parser.add_argument(
        "--enable_password", action="store_true", help="Enable password authentication."
    )
    parser.add_argument(
        "--disable_password", action="store_true", help="Disable password authentication."
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Increase output verbosity."
    )

    args = parser.parse_args()

    logging.basicConfig(
        format="%(asctime)-15s: %(message)s",
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    manager = SSHKeyManager()

    if args.key_type and args.key_name:
        private_key, public_key = manager.generate_ssh_keys(
            args.key_type, args.key_name, args.passphrase
        )
        logging.info("Generated private key:\n%s", private_key)
        logging.info("Generated public key:\n%s", public_key)

    if args.public_key and args.key_name:
        manager.set_public_key(args.public_key, args.key_name)

    if args.remove_key and args.key_name:
        manager.remove_public_key(args.key_name)

    if args.enable_password:
        manager._enable_password_authentication(True)
    elif args.disable_password:
        manager._enable_password_authentication(False)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
