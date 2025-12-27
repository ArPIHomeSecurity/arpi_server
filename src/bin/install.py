#!/usr/bin/env python3
"""
ArPI Installation and Management Tool - Standalone Wrapper

This is a standalone wrapper that makes the install module callable
without using python -m syntax.

Usage:
    ./bin/install.py install [component...]
    ./bin/install.py status [component...]
    ./bin/install.py deploy_code [options]
    ./bin/install.py --help

Examples:
    # Install all components
    ./bin/install.py install
    
    # Install specific components
    ./bin/install.py install system hardware database
    
    # Check status of all components
    ./bin/install.py status
    
    # Deploy server code with backup
    ./bin/install.py deploy_code --backup --restart
    
    # Verbose mode with board version
    ./bin/install.py -v --board-version 3 install services
"""

from installer.cli import cli

if __name__ == "__main__":
    cli()
