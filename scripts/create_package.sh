#!/bin/bash
set -e

# navigate to project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

pipenv run python3 -m build --wheel --outdir "$PROJECT_ROOT/dist"
