#!/usr/bin/env python3
"""Create the standalone install.py upgrade script."""

import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
UPGRADE_SOURCE = PROJECT_ROOT / "src/bin/upgrade.py"
VERSIONING_SOURCE = PROJECT_ROOT / "src/utils/versioning.py"
IMPORT_LINE = "from utils.versioning import VersionInfo\n"


def create_upgrade_script(destination: Path) -> Path:
    if not destination.is_dir():
        raise ValueError(f"Destination is not an existing directory: {destination}")

    upgrade_source = UPGRADE_SOURCE.read_text(encoding="utf-8")
    versioning_source = VERSIONING_SOURCE.read_text(encoding="utf-8")
    if upgrade_source.count(IMPORT_LINE) != 1:
        raise ValueError(f"Expected exactly one shared versioning import in {UPGRADE_SOURCE}")

    output_path = destination / "install.py"
    output_path.write_text(
        upgrade_source.replace(IMPORT_LINE, versioning_source + "\n", 1), encoding="utf-8"
    )
    output_path.chmod(UPGRADE_SOURCE.stat().st_mode)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()

    output_path = create_upgrade_script(args.destination)
    print(f"Created {output_path}")


if __name__ == "__main__":
    main()
