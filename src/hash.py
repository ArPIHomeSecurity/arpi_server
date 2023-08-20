#!/usr/bin/env python

from dotenv import load_dotenv
load_dotenv()
load_dotenv("secrets.env")

import argparse
import logging
from logging import basicConfig

from models import hash_code

parser = argparse.ArgumentParser(description="Hash text to database format")
parser.add_argument("input", help="Input string to hash")

args = parser.parse_args()

basicConfig(level=logging.INFO, format="%(message)s")
logging.info(hash_code(args.input))
