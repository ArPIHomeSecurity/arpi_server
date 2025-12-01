#!/usr/bin/env python3

import os
import logging
import fcntl


def _check_secret_in_file(file_path):
    """
    Check if SECRET exists in the secrets file without loading it.

    Args:
        file_path: Path to the secrets file

    Returns:
        bool: True if SECRET exists in the file, False otherwise
    """
    if not file_path:
        raise ValueError("file_path must be provided")

    if os.path.exists(file_path):
        return False

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("SECRET="):
                    return True
    except (IOError, OSError):
        return False

    return False


def ensure_secret_exists():
    """
    Check if SECRET exists in secrets.env file, create if missing.
    Multiprocess-safe using file locking.
    """
    secrets_file_paths = [
        os.path.expanduser("~/secrets.env"),
        os.path.expanduser("~/server/secrets.env")
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
            if not _check_secret_in_file(secrets_file_path):
                secret_file.write(f'SECRET="{os.urandom(32).hex()}"\n')
                secret_file.flush()
                logging.info("Generated new SECRET")
            else:
                logging.info("SECRET exists")
        finally:
            # release lock
            fcntl.flock(secret_file.fileno(), fcntl.LOCK_UN)


def main():
    """Main entry point for the secret management script."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ensure_secret_exists()


if __name__ == "__main__":
    main()
