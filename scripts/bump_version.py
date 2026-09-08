#!/usr/bin/env python3
"""
Bump the version of the application
"""

import argparse
import json
import logging
import re
import subprocess
import sys
from logging import INFO, WARNING
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from utils.versioning import VersionInfo

VERSION_FILE = "src/server/version.json"


logger = logging.getLogger(__name__)


def load_version() -> dict:
    """Load the current version from the version file"""
    with open(VERSION_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        logger.info("Previous version data: %s", data)
        return data


def save_version(major: int, minor: int, patch: int, pre_release: str, commit: str):
    """Save the new version to the version file"""

    if pre_release:
        version_str = f"v{major}.{minor}.{patch}_{pre_release}:{commit}"
        logger.info("New version: %s", version_str)
    else:
        version_str = f"v{major}.{minor}.{patch}:{commit}"
        logger.info("New version: %s", version_str)

    # parse prerelease name and number
    prerelease_name = None
    prerelease_num = None
    if pre_release:
        m = re.match(r"([a-zA-Z]+)(\d{2})", pre_release)
        if m:
            prerelease_name = m.group(1)
            prerelease_num = m.group(2)
        else:
            prerelease_name = pre_release

    with open(VERSION_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {
                "version": version_str,
                "major": major,
                "minor": minor,
                "patch": patch,
                "prerelease": prerelease_name,
                "prerelease_num": prerelease_num,
                "commit_id": commit,
            },
            f,
            indent=2,
        )
        f.write("\n")


def get_git_commit() -> str:
    """Get the current git commit"""
    return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).strip().decode()


def bump_version(
    version: dict, version_type: str, pre_release: str = None, release: bool = False
) -> tuple:
    """Bump the version based on the given version type"""
    current_version = VersionInfo.from_string(version["version"])
    major = current_version.major
    minor = current_version.minor
    patch = current_version.patch
    old_pre_release_name = current_version.prerelease or ""
    old_pre_release_num = current_version.prerelease_num or 0
    commit = current_version.commit_id

    if old_pre_release_name and old_pre_release_num is not None:
        logger.info(
            "Current version: %s.%s.%s_%s%s:%s",
            major,
            minor,
            patch,
            old_pre_release_name,
            old_pre_release_num,
            commit,
        )
    else:
        logger.info("Current version: %s.%s.%s:%s", major, minor, patch, commit)

    if release:
        # Remove pre-release part, keep major.minor.patch unchanged
        pre_release = None
    elif version_type == "major":
        major += 1
        minor = 0
        patch = 0
    elif version_type == "minor":
        minor += 1
        patch = 0
    elif version_type == "patch":
        patch += 1
    elif pre_release is not None and pre_release != old_pre_release_name:
        pre_release = f"{pre_release}01"
    elif pre_release == old_pre_release_name and old_pre_release_num is not None:
        pre_release_num = int(old_pre_release_num) + 1
        pre_release = f"{pre_release}{pre_release_num:02}"
    else:
        raise ValueError("Invalid version type or pre-release")

    commit = get_git_commit()

    return (major, minor, patch, pre_release, commit)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-t", "--type", required=False, choices=["major", "minor", "patch"], help="Version type"
    )
    parser.add_argument("-p", "--pre-release", help="Pre-release identifier")
    parser.add_argument("-r", "--release", action="store_true", help="Remove pre-release part")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=INFO if args.verbose else WARNING,
        format="%(message)s",
    )

    if args.type is None and args.pre_release is None and not args.release:
        parser.error("Either --type, --pre-release, or --release must be specified")

    if sum([args.type is not None, args.pre_release is not None, args.release]) > 1:
        parser.error("Only one of --type, --pre-release, or --release can be specified")

    logger.info(
        "Bumping version with type: %s, pre-release: %s, release: %s",
        args.type,
        args.pre_release,
        args.release,
    )

    raw_version = load_version()
    major, minor, patch, pre_release, commit = bump_version(
        raw_version, args.type, args.pre_release, args.release
    )

    save_version(major, minor, patch, pre_release, commit)


if __name__ == "__main__":
    main()
