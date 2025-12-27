import json
import os


version_file = os.path.join(os.path.dirname(__file__), "version.json")
with open(version_file, "r", encoding="utf-8") as f:
    version = json.load(f)

__version__ = version["version"]
__package_version__ = f"{version['major']}.{version['minor']}.{version['patch']}{'-' + version['prerelease'] + version['prerelease_num'] if version['prerelease'] else ''}"
