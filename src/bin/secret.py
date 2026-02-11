#!/usr/bin/env python3

import os
import logging
import fcntl
import argparse


def _is_secret_defined(file_path: str, key: str) -> bool:
    """
    Check if the specified key exists in the secrets file without loading it.

    Args:
        file_path: Path to the secrets file
        key: The key to check for

    Returns:
        bool: True if the key exists in the file, False otherwise
    """
    if not file_path:
        raise ValueError("file_path must be provided")

    if not os.path.exists(file_path):
        return False

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith(f"{key}="):
                    return True
    except (IOError, OSError):
        logging.error("Error reading %s", file_path)
        return False

    return False


def ensure_secret_exists(secret_type: str) -> None:
    """
    Check if the appropriate secret exists in secrets.env file, create if missing.
    Multiprocess-safe using file locking.

    Args:
        secret_type: Type of secret ('rest' or 'mcp')
    """
    key = "SECRET" if secret_type == "rest" else "MCP_SECRET"

    secrets_file_paths = [
        os.path.expanduser("~/secrets.env"),
        os.path.expanduser("~/server/secrets.env"),  # for backward compatibility
    ]

    secrets_file_path = None
    for path in secrets_file_paths:
        if os.path.exists(path):
            secrets_file_path = path
            break

    if not secrets_file_path:
        # default to user home if none exist
        secrets_file_path = secrets_file_paths[0]

    # acquire lock first before any checks
    with open(secrets_file_path, "a+", encoding="utf-8") as secret_file:
        try:
            # acquire exclusive lock
            fcntl.flock(secret_file.fileno(), fcntl.LOCK_EX)

            # check if secret exists after acquiring lock
            if not _is_secret_defined(secrets_file_path, key):
                secret_file.write(f'{key}="{os.urandom(32).hex()}"\n')
                secret_file.flush()
                logging.info("Generated new %s", key)
            else:
                logging.info("%s exists", key)
        finally:
            # release lock
            fcntl.flock(secret_file.fileno(), fcntl.LOCK_UN)


def cli_main():
    """
    Command-line interface for managing secrets.
    Ensures the appropriate secret exists in secrets.env file.
    """
    try:
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        parser = argparse.ArgumentParser(description="Manage secrets for ArPI server.")
        parser.add_argument(
            "--type",
            choices=["rest", "mcp"],
            default="rest",
            help="Type of secret to manage: rest for REST API, mcp for MCP Server",
        )
        args = parser.parse_args()
        ensure_secret_exists(args.type)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    cli_main()
