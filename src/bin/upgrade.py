#!/usr/bin/python3
# explicitly run in system python3 to avoid issues with virtual environments
"""
ArPI Upgrade Script

Stable installation example:
curl -sSL https://app.arpi-security.info/install.py | /usr/bin/python3 -

Prerelease installation example:
curl -sSL https://app.arpi-security.info/install.py | /usr/bin/python3 - --prerelease

"""

import argparse
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass
from typing import Callable

import requests

GITHUB_API_SERVER = "https://api.github.com/repos/ArPIHomeSecurity/arpi_server/releases"
GITHUB_API_WEBAPP = "https://api.github.com/repos/ArPIHomeSecurity/arpi_webapplication/releases"

VERSION_PARSER = re.compile(
    r"v?(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)"
    r"(?:(?:[_-])?(?P<pre_release>[a-zA-Z]+)(?P<pre_release_num>\d+))?"
    r"(?::(?P<commit>[a-z0-9]{7}))?"
)


class AssetNotFoundError(Exception):
    pass


@dataclass
class VersionInfo:
    version: str
    major: int
    minor: int
    patch: int
    prerelease: str | None
    prerelease_num: int | None
    commit_id: str


def get_latest_release(api_url, prerelease=False) -> dict:
    """
    Fetch the latest release from the GitHub API.
    """
    resp = requests.get(api_url)
    resp.raise_for_status()
    releases = resp.json()
    for release in releases:
        if prerelease or not release["prerelease"]:
            return release

    raise Exception("No suitable release found.")


def download_asset(release, extension=".tar.gz") -> str:
    """
    Download the tar.gz asset from the release.
    """
    for asset in release["assets"]:
        print(f"      🔎 Checking asset: {asset['name']}")
        if asset["name"].endswith(extension):
            url = asset["browser_download_url"]
            local_path = os.path.join(tempfile.gettempdir(), asset["name"])
            print(f"      ⬇️  Downloading asset: {asset['name']} from {url}")
            with requests.get(url, stream=True) as r:
                r.raise_for_status()
                with open(local_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            print(f"      ✅ Asset downloaded: {local_path}")
            return local_path

    if release["assets"]:
        # print all asset names for debugging
        print("      ⚠️  No .tar.gz asset found in release assets. Available assets:")
        for asset in release["assets"]:
            print(f"        - {asset['name']}")

    raise AssetNotFoundError(f"No tar.gz asset found in the release for {release['tag_name']}.")


def decompress_tar_gz(tar_path):
    """
    Extract the tar.gz archive to a temporary directory.
    """
    tmp_dir = tempfile.mkdtemp()
    with tarfile.open(tar_path, "r:gz") as tar:
        tar.extractall(tmp_dir)

    return tmp_dir


def get_server_version() -> VersionInfo | None:
    """
    Get the actual version of the server component.
    """
    try:
        import server.version as server_version

        m = VERSION_PARSER.match(server_version.__version__)
        if not m:
            raise ValueError(f"Invalid version string: {server_version.__version__}")

        p = m.groupdict()
        return VersionInfo(
            version=server_version.__version__,
            major=int(p["major"]),
            minor=int(p["minor"]),
            patch=int(p["patch"]),
            prerelease=p["pre_release"],
            prerelease_num=int(p["pre_release_num"]) if p["pre_release_num"] else None,
            commit_id=p["commit"] or "",
        )
    except ImportError:
        pass

    # fallback for old-style (non-package) installations
    try:
        with open("/home/argus/server/src/server/version.json", "r", encoding="utf-8") as f:
            version_info = json.load(f)
            return VersionInfo(**version_info)
    except FileNotFoundError:
        pass


def get_webapplication_version() -> VersionInfo | None:
    """
    Get the actual version of the webapplication component.
    """
    try:
        with open("/home/argus/webapplication/en/assets/version.json", "r", encoding="utf-8") as f:
            version_info = json.load(f)
            return VersionInfo(**version_info)
    except FileNotFoundError:
        print("⚠️  Warning: Webapplication version file not found")


def upgrade_server(tmp_dir: str, wheel_path: str, board_version: str, use_simulator: bool):
    """
    Execute install.py from the extracted server files.
    """
    install_config = {
        "PYTHONPATH": "src",
        "BOARD_VERSION": board_version,
        "USE_SIMULATOR": "true" if use_simulator else "false",
    }

    # deploy source code
    deploy_command = (
        f"cd {tmp_dir}; "
        f"sudo {' '.join(f'{key}={value}' for key, value in install_config.items())} "
        f"python3 ./src/installer/cli.py bootstrap"
    )
    subprocess.run(deploy_command, shell=True, check=True)

    # install wheel with "simulator" and "device" extras
    pip_install_command = (
        f"pip3 install --user --break-system-packages --upgrade {wheel_path}[device,simulator]"
    )
    subprocess.run(pip_install_command, shell=True, check=True)

    install_command = (
        f"cd {tmp_dir}; "
        f"sudo {' '.join(f'{key}={value}' for key, value in install_config.items())} "
        f"./src/installer/cli.py post-install"
    )
    subprocess.run(install_command, shell=True, check=True)


def upgrade_webapplication(tmp_dir):
    """
    Copy the extracted webapplication code to /home/argus/webapplication.
    """
    dst_dir = "/home/argus/webapplication"
    # remove old webapplication dir if exists
    if os.path.exists(dst_dir):
        shutil.rmtree(dst_dir)

    # find the root of the extracted webapplication
    entries = os.listdir(tmp_dir)
    if len(entries) == 1 and os.path.isdir(os.path.join(tmp_dir, entries[0])):
        src_dir = os.path.join(tmp_dir, entries[0])
    else:
        src_dir = tmp_dir

    shutil.copytree(src_dir, dst_dir)


def compare_versions(v1: str, v2: VersionInfo):
    """
    Compare two versions: v1 as string, v2 as VersionInfo.
    Returns 1 if v1 > v2, -1 if v1 < v2, 0 if equal.
    """
    v1_match = VERSION_PARSER.match(v1)
    if not v1_match:
        print(f"Version: {v1}")
        raise ValueError("Invalid version string format.")

    v1_parts = v1_match.groupdict()

    # compare major, minor, patch
    for key in ["major", "minor", "patch"]:
        n1 = int(v1_parts[key])
        n2 = getattr(v2, key)
        if n1 > n2:
            return 1
        elif n1 < n2:
            return -1

    # compare pre_release (None means stable, which is considered higher than any pre-release)
    # normalize to lowercase for case-insensitive comparison
    pre1 = v1_parts["pre_release"].lower() if v1_parts["pre_release"] else None
    pre2 = v2.prerelease.lower() if v2.prerelease else None
    if pre1 != pre2:
        if pre1 is None:
            return 1
        if pre2 is None:
            return -1
        if pre1 > pre2:
            return 1
        elif pre1 < pre2:
            return -1

    # compare pre_release_num (None is considered lower)
    num1 = v1_parts["pre_release_num"]
    num2 = v2.prerelease_num
    if num1 != (f"{num2:02}" if num2 is not None else None):
        if num1 is None:
            return -1
        if num2 is None:
            return 1
        n1 = int(num1)
        n2 = num2
        if n1 > n2:
            return 1
        elif n1 < n2:
            return -1

    return 0


def check_and_upgrade(
    api_url: str,
    get_version_func: Callable[[], str],
    project_name: str,
    prerelease: bool,
    board_version: str,
    use_simulator: bool,
) -> bool:
    """
    Check for updates and upgrade the specified project if a newer version is available.

    Returns True if an upgrade was performed, False otherwise.
    """
    print(f"  🔍 Checking for {project_name} updates...")
    latest_release = get_latest_release(api_url, prerelease=prerelease)
    actual_version = get_version_func()

    print(f"    - Latest release: {latest_release['tag_name']}")
    print(f"    - Current version: {actual_version.version if actual_version else 'unknown'}")
    # if we cannot determine the actual version, assume upgrade/reinstall is needed
    result = compare_versions(latest_release["tag_name"], actual_version) if actual_version else 1
    if result < 1:
        print(
            f"    ✅ No newer version, skipping {project_name} "
            f"{actual_version} < {latest_release['tag_name']}"
        )
    elif result == 1:
        print(f"    ⬆️  New version {latest_release['tag_name']} available for {project_name}")
        upgrade_project(latest_release, project_name, board_version, use_simulator)
        return True

    return False


def upgrade_project(release: dict, project: str, board_version: str, use_simulator: bool):
    """
    Upgrade the specified project using the latest release.
    """
    print(f"    🚀 Upgrading {project}...")
    print(f"      🏷️  Found release: {release['tag_name']}")
    tar_path = download_asset(release)
    print(f"      📦 Downloaded to: {tar_path}")
    tmp_dir = decompress_tar_gz(tar_path)
    print(f"      📂 Decompressed to: {tmp_dir}")

    if project == "server":
        wheel_path = download_asset(release, extension=".whl")
        print(f"      📦 Downloaded wheel to: {wheel_path}")

        print("      ⚙️  Upgrading server files...")
        upgrade_server(tmp_dir, wheel_path, board_version, use_simulator)
    elif project == "webapplication":
        print("      ⚙️  Upgrading webapplication files...")
        upgrade_webapplication(tmp_dir)
    else:
        raise Exception("Unknown project type.")

    print(f"    ✅ {project} upgrade complete.")


def install_packages(packages):
    """
    Install the specified packages using apt-get.
    """
    # check if packages are already installed
    missing_packages = []
    for pkg in packages:
        result = subprocess.run(
            ["dpkg", "-s", pkg], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False
        )
        if result.returncode != 0:
            missing_packages.append(pkg)

    if missing_packages:
        print(f"  📦 Installing required packages: {', '.join(missing_packages)}")
        subprocess.run(["sudo", "apt-get", "update"], check=True)
        subprocess.run(["sudo", "apt-get", "install", "-y"] + missing_packages, check=True)
        print("  ✅ Packages installed.")
    else:
        print("  ✅ All required packages are already installed.")


def main():
    """
    Main entry point for the upgrade script.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--prerelease", action="store_true", help="Use latest prerelease")
    parser.add_argument("--board-version", type=str, default="2", help="Board version (2 or 3)")
    parser.add_argument("--use-simulator", action="store_true", default=False, help="Use simulator")
    args = parser.parse_args()

    print("🔧 Starting ArPI upgrade process...")

    # ensure required packages are installed
    install_packages(["python3-click"])

    server_upgraded = check_and_upgrade(
        GITHUB_API_SERVER,
        get_server_version,
        "server",
        args.prerelease,
        args.board_version,
        args.use_simulator,
    )
    webapplication_upgraded = check_and_upgrade(
        GITHUB_API_WEBAPP,
        get_webapplication_version,
        "webapplication",
        args.prerelease,
        args.board_version,
        args.use_simulator,
    )

    if server_upgraded or webapplication_upgraded:
        print("  🔄 Restarting services: argus_server, argus_mcp, argus_monitor, nginx ...")
        os.system("sudo systemctl restart argus_server argus_mcp argus_monitor nginx")  # noqa: F821
        print("  ✅ Services restarted successfully")

    print("🎉 Upgrade process finished.")


def cli_main():
    try:
        main()
        exit(0)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"  ❌ Something went wrong: {e}")
        exit(1)


if __name__ == "__main__":
    cli_main()
