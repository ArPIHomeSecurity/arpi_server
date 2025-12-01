#!/bin/bash

# Script to create a compressed tar.gz for the installers package

set -e

# navigate to project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# extract version from version.json and format it like Python package version
MAJOR=$(jq -r '.major' "$PROJECT_ROOT/src/server/version.json")
MINOR=$(jq -r '.minor' "$PROJECT_ROOT/src/server/version.json")
PATCH=$(jq -r '.patch' "$PROJECT_ROOT/src/server/version.json")
PRERELEASE=$(jq -r '.prerelease // empty' "$PROJECT_ROOT/src/server/version.json" | tr '[:upper:]' '[:lower:]')
PRERELEASE_NUM=$(jq -r '.prerelease_num // empty' "$PROJECT_ROOT/src/server/version.json" | sed 's/^0*//')

VERSION="${MAJOR}.${MINOR}.${PATCH}${PRERELEASE}${PRERELEASE_NUM}"

if [ ! -d "$PROJECT_ROOT/src/installer" ]; then
    echo "Error: Directory 'src/installer' does not exist."
    exit 1
fi

echo "Get dhparam from Mozilla..."
curl https://ssl-config.mozilla.org/ffdhe2048.txt -sSLo "$PROJECT_ROOT/src/installer/installers/etc/arpi_dhparam.pem"

echo "Creating bootstrap package version $VERSION..."
mkdir -p "$PROJECT_ROOT/dist"

# Create tar from project root to avoid absolute path warnings
OUTPUT_PACKAGE="arpi_server-bootstrap-$VERSION.tar.gz"
tar -czf "dist/$OUTPUT_PACKAGE" src/installer

echo "Package created: $OUTPUT_PACKAGE"
