#!/bin/bash
set -e


PACKAGE_NAME="arpi-server"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION=$(grep -o 'v[0-9]\+\.[0-9]\+\.[0-9]\+[^" ]*' "$SCRIPT_DIR/src/server/version.py" | head -1 | sed 's/:.*//')
OUTFILE="${2:-${PACKAGE_NAME}-${VERSION}}.tar.gz"

echo "Get dhparam from Mozilla..."
curl https://ssl-config.mozilla.org/ffdhe2048.txt -o "${SCRIPT_DIR}/arpi_dhparam.pem"

echo "Packaging server as $OUTFILE ..."
tar -czf "$SCRIPT_DIR/$OUTFILE" \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='*.sock' \
    -C "$SCRIPT_DIR" \
    src/ \
    etc/ \
    migrations/ \
    Pipfile \
    Pipfile.lock \
    README.md \
    LICENSE \
    arpi_dhparam.pem \
    --transform="s|${1:-prod}.env|.env|" \
    "${1:-prod}.env"

echo "Package created: $OUTFILE"
