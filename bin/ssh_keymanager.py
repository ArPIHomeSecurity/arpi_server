#!/usr/bin/env python3
"""
ArPI SSH Key Manager Tool
"""

import argparse
import logging

from tools.ssh_keymanager import SSHKeyManager


def main():
    parser = argparse.ArgumentParser(description="Manage SSH keys.")
    parser.add_argument("--key_type", type=str, help="Type of the key to generate.")
    parser.add_argument("--key_name", type=str, help="Name of the key.")
    parser.add_argument("--passphrase", type=str, default="", help="Passphrase for the key.")
    parser.add_argument("--public_key", type=str, help="Public key to set.")
    parser.add_argument("--remove_key", type=str, help="Remove key by 'key_name'.")
    parser.add_argument(
        "--enable_password", action="store_true", help="Enable password authentication."
    )
    parser.add_argument(
        "--disable_password", action="store_true", help="Disable password authentication."
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Increase output verbosity.")

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


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
