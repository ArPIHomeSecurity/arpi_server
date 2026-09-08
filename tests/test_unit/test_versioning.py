import pytest

from scripts.bump_version import bump_version
from utils.versioning import VersionInfo


def compare(version1: str, version2: str):
    return VersionInfo.from_string(version1).compare_version(VersionInfo.from_string(version2))


LESS = -1
EQUAL = 0
GREATER = 1


@pytest.mark.parametrize(
    ("version1", "version2", "expected"),
    [
        ("1.0.0:12345", "1.0.1:12345", LESS),
        ("1.0.1:12345", "1.0.0:12345", GREATER),
        ("1.0.0:12345", "1.0.0:12345", EQUAL),
        ("1.0.0:12345", "1.1.0:12345", LESS),
        ("1.1.0:12345", "1.0.0:12345", GREATER),
        ("1.0.0:12345", "2.0.0:12345", LESS),
        ("2.0.0:12345", "1.0.0:12345", GREATER),
        ("2.0.0:12345", "2.0.0:12345", EQUAL),
        ("1.0.0_RC00:12345", "1.0.0_RC01:12345", LESS),
        ("1.0.0_RC01:12345", "1.0.0_RC00:12345", GREATER),
        ("1.0.0_RC00:12345", "1.0.0_RC00:12345", EQUAL),
        ("1.0.0_AB01:12345", "1.0.0_CD02:12345", LESS),
        ("1.0.0_RC01:12345", "1.0.1:12345", LESS),
        ("1.0.0:12345", "1.0.0_RC01:12345", GREATER),
    ],
)
def test_compare_version(version1: str, version2: str, expected: int):
    assert compare(version1, version2) == expected


@pytest.mark.parametrize(
    ("version", "version_type", "pre_release", "expected"),
    [
        ("v1.2.3:abcdef0", "patch", None, (1, 2, 4, None)),
        ("v1.2.3:abcdef0", "minor", None, (1, 3, 0, None)),
        ("v1.2.3:abcdef0", "major", None, (2, 0, 0, None)),
        ("v1.2.3:abcdef0", None, "beta", (1, 2, 3, "beta01")),
        ("v1.2.3_beta01:abcdef0", None, "beta", (1, 2, 3, "beta02")),
    ],
)
def test_bump_version(monkeypatch, version, version_type, pre_release, expected):
    monkeypatch.setattr("scripts.bump_version.get_git_commit", lambda: "abcdef0")
    version_data = {"version": version}

    result = bump_version(version_data, version_type, pre_release)

    assert result[:4] == expected
