#!/usr/bin/env python3
"""
ArPI Certificate Management Tool
"""

import argparse
import logging

from tools.certbot import Certbot


def main():
    """
    Main function to update certificates
    """
    parser = argparse.ArgumentParser(
        description="Update the system using certificates, or manage the certificate"
    )
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument("-g", "--generate", action="store_true", help="generate the certificate")
    group.add_argument("-r", "--renew", action="store_true", help="renew the certificate")
    group.add_argument("-d", "--delete", action="store_true", help="delete the certificate")
    parser.add_argument("-v", "--verbose", action="store_true", help="increase output verbosity")
    args = parser.parse_args()

    logging.basicConfig(
        format="%(asctime)-15s: %(message)s", level=logging.DEBUG if args.verbose else logging.INFO
    )

    certbot = Certbot(logging.getLogger("argus_certbot"))
    if args.generate:
        certbot.generate_certificate()
        return
    if args.renew:
        certbot.renew_certificate()
        return
    if args.delete:
        certbot.delete_certificate()
        return

    certbot.update_certificate()


def cli_main():
    try:
        main()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    cli_main()
