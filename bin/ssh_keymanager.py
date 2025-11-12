#!/usr/bin/env python3
"""
ArPI SSH Key Manager Tool
"""

import argparse
import logging

from tools.ssh_keymanager import SSHKeyManager


def main():
    parser = argparse.ArgumentParser(description="Manage SSH keys.")
    parser.add_argument("command", type=str, choices=["generate", "set", "remove"], help="Command to execute.")
    parser.add_argument("--key_type", type=str, help="Type of the key to generate (rsa, ecdsa, ed25519).")
    parser.add_argument("--key_name", type=str, required=True, help="Name of the key.")
    parser.add_argument("--passphrase", type=str, default="", help="Passphrase for the key.")
    parser.add_argument("--public_key", type=str, help="Public key string to set")
    parser.add_argument("-v", "--verbose", action="store_true", help="Increase output verbosity.")

    args = parser.parse_args()

    logging.basicConfig(
        format="%(asctime)-15s: %(message)s",
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    manager = SSHKeyManager()

    if args.command == "generate" and args.key_type and args.key_name:
        private_key, public_key = manager.generate_ssh_keys(
            args.key_type, args.key_name, args.passphrase
        )
        logging.info("Generated private key:\n%s", private_key)
        logging.info("Generated public key:\n%s", public_key)
    elif args.command == "generate":
        logging.error("Key type and key name are required to generate keys.")

    if args.command == "set" and args.public_key and args.key_name:
        manager.set_public_key(args.public_key, args.key_name)
        logging.info("Public key %s set successfully.", args.key_name)
    elif args.command == "set":
        logging.error("Public key and key name are required to set a public key.")

    if args.command == "remove" and args.key_name:
        manager.remove_public_key(args.key_name)
        logging.info("Public key %s removed successfully.", args.key_name)
    elif args.command == "remove":
        logging.error("Key name is required to remove a public key.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
