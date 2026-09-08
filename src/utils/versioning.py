"""
This module provides utilities for parsing and comparing version strings.
"""

import re
from dataclasses import dataclass

VERSION_PARSER = re.compile(
    r"v?(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)"
    r"(?:(?:[_-])?(?P<pre_release>[a-zA-Z]+)(?P<pre_release_num>\d+))?"
    r"(?::(?P<commit>[a-z0-9]{7}))?"
)


@dataclass
class VersionInfo:
    version: str
    major: int
    minor: int
    patch: int
    prerelease: str | None
    prerelease_num: int | None
    commit_id: str

    @classmethod
    def from_string(cls, version: str) -> "VersionInfo":
        match = VERSION_PARSER.match(version)
        if not match:
            raise ValueError("Invalid version string format.")

        parts = match.groupdict()
        return cls(
            version=version,
            major=int(parts["major"]),
            minor=int(parts["minor"]),
            patch=int(parts["patch"]),
            prerelease=parts["pre_release"],
            prerelease_num=(int(parts["pre_release_num"]) if parts["pre_release_num"] else None),
            commit_id=parts["commit"] or "",
        )

    def compare_version(self, other: "VersionInfo") -> int:
        for key in ["major", "minor", "patch"]:
            value = getattr(self, key)
            other_value = getattr(other, key)
            if value > other_value:
                return 1
            if value < other_value:
                return -1

        prerelease = self.prerelease.lower() if self.prerelease else None
        other_prerelease = other.prerelease.lower() if other.prerelease else None
        if prerelease != other_prerelease:
            if prerelease is None:
                return 1
            if other_prerelease is None:
                return -1
            return 1 if prerelease > other_prerelease else -1

        if self.prerelease_num != other.prerelease_num:
            if self.prerelease_num is None:
                return -1
            if other.prerelease_num is None:
                return 1
            return 1 if self.prerelease_num > other.prerelease_num else -1

        return 0
