#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author: Gábor Kovács
# @Date:   2021-02-25 20:03:35
# @Last Modified by:   Gábor Kovács
# @Last Modified time: 2021-02-25 20:03:41
import argparse
import logging
from logging import basicConfig

from models import hash_code

parser = argparse.ArgumentParser(description="Hash text to database format")
parser.add_argument("input", help="Input string to hash")

args = parser.parse_args()

basicConfig(level=logging.INFO, format="%(message)s")
logging.info(hash_code(args.input))
