#!/usr/bin/env python3
"""This script is used to extract the contents of an S3 bucket, including
   verison info and files that have been deleted.
   Note that we're using subprocess, as it appears to be a replacement
   for os.system() and other functions, as per https://stackoverflow.com/a/4813571/196073"""


import argparse
import logging
import os
import subprocess
import sys
import tempfile


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s: %(levelname)s: %(message)s"
)
LOGGER = logging.getLogger()

#
# Parse our arguments.
#
PARSER = argparse.ArgumentParser(
    description="Extract all versions of files in an S3 bucket"
)
PARSER.add_argument("bucket")
PARSER.add_argument(
    "file",
    nargs="?",
    help="JSON file to write (default: output.json)",
    default="output.json",
)
# PARSER.add_argument("--filter", help = "Filename text to filter on")

ARGS = PARSER.parse_args()
LOGGER.info("Args: %s", ARGS)

OUTPUT = ARGS.file

BUCKET = ARGS.bucket
CMD = "aws s3api list-object-versions --bucket %s" % BUCKET
# CMD = "ls what" # Debugging

TMP_FD, TMPFILE = tempfile.mkstemp(dir=".", prefix="tmp-output")
LOGGER.info("Temp file '%s' created!", TMPFILE)

LOGGER.info("Executing command '%s'", CMD)
LOGGER.info("Note that this may take a long time, perhaps a minute or more!")
COMPLETED = subprocess.run(CMD, stdout=TMP_FD, shell=True)


if COMPLETED.returncode:
    LOGGER.error(
        "! Process '%s' exited with return code '%d'", CMD, COMPLETED.returncode
    )
    sys.exit(COMPLETED.returncode)

LOGGER.info("Renaming temp file '%s' to '%s'...", TMPFILE, OUTPUT)
os.rename(TMPFILE, OUTPUT)
