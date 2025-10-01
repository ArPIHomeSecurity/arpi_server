#!/usr/bin/env python3
"""
Bump the version of the application
"""

import argparse
import re
import subprocess
from logging import INFO, basicConfig, info

VERSION_FILE = "src/server/version.py"

VERSION_TEMPLATE = '__version__="v%s.%s.%s%s:%s"\n'
VERSION_PARSER = re.compile(
    r"v(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)(?:_(?P<pre_release>[a-zA-Z]+)(?P<pre_release_num>\d{2}))?:(?P<commit>[a-z0-9]{7})"
)


def load_version() -> str:
    """Load the current version from the version file"""
    with open(VERSION_FILE, "r", encoding="utf-8") as f:
        raw_text = f.read()
        raw_version = (
            raw_text.replace("__version__=", "")
            .replace('"', "")
            .replace("'", "")
            .strip()
        )
        info("Previous raw version: %s", raw_version)
        return raw_version

def parse_version(raw_version: str) -> tuple:
    """Parse the version string"""
    match = VERSION_PARSER.match(raw_version)
    info("Parsed raw version: %s", match)

    if not match:
        raise ValueError(f"Invalid version string: {raw_version}")

    parts = match.groupdict()
    major = int(parts["major"])
    minor = int(parts["minor"])
    patch = int(parts["patch"])
    pre_release_name = parts.get("pre_release") or ""
    pre_release_num = parts.get("pre_release_num") or ""
    commit = parts["commit"]

    info(
        "Parsed version: Major: %s, Minor: %s, Patch: %s, Pre-release: %s, Pre-release num: %s, Commit: %s",
        major,
        minor,
        patch,
        pre_release_name,
        pre_release_num,
        commit,
    )

    return major, minor, patch, pre_release_name, pre_release_num, commit


def save_version(major: int, minor: int, patch: int, pre_release: str, commit: str):
    """Save the new version to the version file"""

    if pre_release:
        info("New version: %s.%s.%s_%s:%s", major, minor, patch, pre_release, commit)
    else:
        info("New version: %s.%s.%s:%s", major, minor, patch, commit)

    with open(VERSION_FILE, "w", encoding="utf-8") as f:
        f.write(
            VERSION_TEMPLATE
            % (major, minor, patch, f"_{pre_release}" if pre_release else "", commit)
        )


def get_git_commit() -> str:
    """Get the current git commit"""
    return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).strip().decode()


def bump_version(version: tuple, version_type: str, pre_release: str = None) -> tuple:
    """Bump the version based on the given version type"""
    major, minor, patch, old_pre_release_name, old_pre_release_num, commit = version

    if old_pre_release_name and old_pre_release_num:
        info("Current version: %s.%s.%s_%s%s:%s", major, minor, patch, old_pre_release_name, old_pre_release_num, commit)
    else:
        info("Current version: %s.%s.%s:%s", major, minor, patch, commit)

    if version_type == "major":
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
    elif pre_release == old_pre_release_name and old_pre_release_num:
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
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        basicConfig(level=INFO)

    if args.type is None and args.pre_release is None:
        parser.error("Either --type or --pre-release must be specified")
    
    if args.type is not None and args.pre_release is not None:
        parser.error("Only one of --type or --pre-release can be specified")

    info("Bumping version with type: %s and pre-release: %s", args.type, args.pre_release)

    raw_version = load_version()
    version = parse_version(raw_version)
    major, minor, patch, pre_release, commit = bump_version(version, args.type, args.pre_release)
    save_version(major, minor, patch, pre_release, commit)


# def test_load_version():
#     major, minor, patch, pre_release_name, pre_release_num, commit = parse_version("v1.2.3_alpha01:abcdef0")
#     assert major == 1
#     assert minor == 2
#     assert patch == 3
#     assert pre_release_name == "alpha"
#     assert pre_release_num == "01"
#     assert commit == "abcdef0"


# def test_bump_version():
#     version = parse_version("v1.2.3:abcdef0")
#     major, minor, patch, pre_release, commit = bump_version(version, "patch")
#     assert patch == 4, f"Got {patch} instead of 4"

#     major, minor, patch, pre_release, commit = bump_version(version, "minor")
#     assert minor == 3, f"Got {minor} instead of 3"

#     major, minor, patch, pre_release, commit = bump_version(version, "major")
#     assert major == 2, f"Got {major} instead of 2"

#     major, minor, patch, pre_release, commit = bump_version(version, None, "beta")
#     assert pre_release == "beta01", f"Got {pre_release} instead of beta01"

#     version = parse_version("v1.2.3_beta01:abcdef0")
#     major, minor, patch, pre_release, commit = bump_version(version, None, "beta")
#     assert pre_release == "beta02", f"Got {pre_release} instead of beta02"

if __name__ == "__main__":
    main()
