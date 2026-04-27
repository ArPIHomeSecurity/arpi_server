"""Setup script to handle custom file transformations during package build."""

import os
import shutil
from distutils.command.build import build
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py
from setuptools.command.sdist import sdist


class PreBuild(build):
    """Custom build command that runs before creating the distribution."""

    def run(self):
        """Create config.env from .env.prod before building."""
        source = Path(f".env.{os.getenv('ENVIRONMENT', 'prod')}")
        print(f"Running pre-build transformations for {source}...")

        target = Path("config.env")

        if source.exists():
            print(f"Creating {target} from {source}")
            shutil.copy2(source, target)
        else:
            print(f"Warning: {source} not found, skipping config.env creation")

        # Run the normal build
        super().run()


class PreSDist(sdist):
    """Custom sdist command that prepares files before creating source distribution."""

    def run(self):
        """Create config.env from .env.prod before creating source distribution."""
        source = Path(".env.prod")
        print(f"Running pre-sdist transformations for {source}...")

        target = Path("config.env")

        if source.exists():
            print(f"Creating {target} from {source}")
            shutil.copy2(source, target)
        else:
            print(f"Warning: {source} not found, skipping config.env creation")

        # Run the normal sdist
        super().run()


if __name__ == "__main__":
    setup(
        cmdclass={
            "build": PreBuild,
            "sdist": PreSDist,
            "build_py": build_py,
        }
    )
