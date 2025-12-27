#!/bin/bash 

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

echo "$VERSION"