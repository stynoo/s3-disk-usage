#!/usr/bin/env python3
"""This script will read in the JSON generated by a ListObjectVersions call to Amazon S3,
   combine the Versions and DeleteMarkers arrays into a unified data structure,
   and print out statistics on disk usage, *especially* for things like deleted files."""

import argparse
import json
import logging
import os
import humanize

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s: %(levelname)s: %(message)s"
)
LOGGER = logging.getLogger()

#
# Parse our arguments.
#
PARSER = argparse.ArgumentParser(description="Get stats from files in an S3 bucket")
#
# This one was a bit tricky, but if I want an optional positional argument,
# I need to set nargs to "?".  Took me like 10 minutes of Googling to figure
# that one out.
#
PARSER.add_argument("file", nargs="?", help="JSON file to load", default="output.json")
PARSER.add_argument("--humanize", action="store_true", help="Humanize output")
# PARSER.add_argument("--filter", help = "Filename text to filter on")

ARGS = PARSER.parse_args()
LOGGER.info("Args: %s", ARGS)


def process_deletes(data):
    """Go through our DeleteMarkers and return a data structure that's
       distilled to just the key and date"""
    retval = {}
    for row in data:
        ret = {}
        key = row["Key"]
        # is_latest = row["IsLatest"]
        date = row["LastModified"]

        if not key in retval:
            #
            # New marker, just drop in our data
            #
            # ret["is_latest"] = is_latest
            ret["latest_modified"] = date
            retval[key] = ret

        else:
            #
            # This file already has a delete marker, so
            # check the date.
            #
            if date > retval[key]["latest_modified"]:
                retval[key]["lastest_modified"] = date

    return retval


def process_versions(data):
    """Go through our Versions and return a data strucutre that's distilled to just
       the key, date, total and average sizes, and number of versions."""

    retval = {}

    for row in data:
        ret = {}

        key = row["Key"]
        date = row["LastModified"]
        size = row["Size"]

        if not key in retval:
            #
            # New file, just drop in our data.
            #
            ret["latest_modified"] = date
            ret["total_size"] = size
            ret["num_versions"] = 1
            retval[key] = ret

        else:
            #
            # We already saw this filename, so update
            # what we have with this version and check the date.
            #
            retval[key]["total_size"] += size
            retval[key]["num_versions"] += 1

            if date > retval[key]["latest_modified"]:
                retval[key]["lastest_modified"] = date

                #
                # If this the latest version, this means this file
                # is "showing", and let's note the size.
                #
        if row["IsLatest"]:
            if not is_folder(key):
                retval[key]["latest_size"] = size

                #
                # Now calculate average file size
                #
    for key, row in retval.items():
        size = row["total_size"]
        num = row["num_versions"]
        row["average_size"] = size / num

    return retval


def is_folder(filename):
    """Any object that is a folder ends in a slash. Check for that."""

    retval = False

    index = len(filename) - 1

    if filename[index] == "/":
        retval = True

    return retval


def combine_deleted_and_versions(delete_markers, versions):
    """Combine our Delete Markers and Versions into a single unified dictionary."""

    #
    # Start by copying our Delete Markers into the data structure
    #
    retval = delete_markers

    #
    # Now go through our Versions, and merge them in.
    #
    for key, row in versions.items():

        if not key in retval:
            #
            # If the key wasn't in delete_markers, then
            # the object must be prejsent.
            #
            retval[key] = row
            retval[key]["status"] = "present"

        else:
            #
            # Otherwise, we have to determine state by checking
            # the most recently modified dates.  If the date
            # deleted is more recently, then the current
            # state is deleted, otherwise it's present.
            #
            date_deleted = delete_markers[key]["latest_modified"]
            date_version = row["latest_modified"]
            retval[key] = row

            retval[key]["status"] = "present"

            if date_deleted > date_version:
                retval[key]["status"] = "deleted"
                retval[key]["last_modified"] = date_deleted

        retval[key]["is_folder"] = is_folder(key)

        #
        # Finally, go through our combined list of items, and if not found in
        # versions, then only a delete marker was present.
        #
        # As it turns out, that's totally possible, such as if the
        # original version has aged out by policy or been deleted by hand.
        #
        # So anyway, when that's the case, we'll need to manually set
        # status, number of versions (1), size (0), etc.
        #
    for key, row in retval.items():
        if key not in versions:
            row["status"] = "deleted"
            row["is_folder"] = is_folder(key)
            row["total_size"] = 0
            row["num_versions"] = 0
            # print(key, row.get("latest_size"))

    return retval


def get_file_stats(data):
    """Go through our files and get stats"""

    retval = {}
    retval["present"] = {}
    retval["present"]["num_files"] = 0
    retval["present"]["num_versions"] = 0
    retval["present"]["total_size"] = 0
    retval["present"]["average_size"] = 0
    retval["present"]["latest_size"] = 0
    retval["deleted"] = {}
    retval["deleted"]["num_files"] = 0
    retval["deleted"]["num_versions"] = 0
    retval["deleted"]["total_size"] = 0
    retval["deleted"]["average_size"] = 0

    for key, row in data.items():
        #
        # Folders are essentially metadata and don't take up
        # disk space, so don't bother with them.
        #
        if row["is_folder"]:
            continue

        if row["status"] == "present":
            # print("PRESENT", key) # Debugging
            retval["present"]["num_files"] += 1
            retval["present"]["num_versions"] += row["num_versions"]
            retval["present"]["total_size"] += row["total_size"]
            retval["present"]["latest_size"] += row.get("latest_size")

        elif row["status"] == "deleted":
            # print("ABSENT", key) # Debugging
            retval["deleted"]["num_files"] += 1
            retval["deleted"]["num_versions"] += row["num_versions"]
            retval["deleted"]["total_size"] += row["total_size"]

        else:
            raise Exception("Unknown status: %s" % row["status"])

    retval["present"]["average_size"] = 0
    if retval["present"]["num_versions"]:
        retval["present"]["average_size"] = (
            retval["present"]["total_size"] / retval["present"]["num_versions"]
        )

    retval["deleted"]["average_size"] = 0
    if retval["deleted"]["num_versions"]:
        retval["deleted"]["average_size"] = (
            retval["deleted"]["total_size"] / retval["deleted"]["num_versions"]
        )

    return retval


def print_file_stats(stats):
    """Print up our file stats."""

    present = stats["present"]
    present["pct_used_by_latest"] = "0"
    if present["total_size"]:
        present["pct_used_by_latest"] = str(
            round(present["latest_size"] / present["total_size"] * 100, 2)
        )

        #
        # Go through our stats and make human-readable verions of all numerical values
        # and byte counts.
        #
    output_format = "%10s: %20s: %s"

    for key, row in stats.items():

        row_new = {}

        for key2, row2 in row.items():

            if "_size" in key2:
                row_new[key2] = row2
                row2 = humanize.naturalsize(row2, binary=True, gnu=True)
                row_new[key2 + "_human"] = row2
            elif "num_" in key2:
                row_new[key2] = row2
                row2 = humanize.intcomma(row2)
                row_new[key2 + "_human"] = row2
            elif "pct_" in key2:
                row_new[key2] = row2
                row2 = row2 + "%"
                row_new[key2 + "_human"] = row2
            else:
                row_new[key2] = row2

        stats[key] = row_new

        #
        # Get the name of the bucket from the filename add it into the stats.
        #
    bucket = os.path.splitext(ARGS.file)[0]
    stats["bucket"] = bucket

    if not ARGS.humanize:
        print(json.dumps(stats, indent=2, sort_keys=True))

    else:
        #
        # If we're humanizing, do that on our bytecounts and totals
        #
        fields = (
            "num_files",
            "num_versions",
            "average_size",
            "latest_size",
            "total_size",
            "pct_used_by_latest",
        )

        print()

        for key in fields:
            human_key = key + "_human"
            print(output_format % ("Present", key, stats["present"][human_key]))

        print()

        for key in fields:
            if key in stats["deleted"]:
                human_key = key + "_human"
                print(output_format % ("Deleted", key, stats["deleted"][human_key]))

        print()


def main(input_file):
    """Our main function, which reads from the input file, processes the data,
       and prints the results."""
    with open(input_file) as json_file:
        data = json.load(json_file)
        # print("Debug Data:", json.dumps(data, indent = 4, sort_keys = True)) # Debugging

        delete_markers = {}
        if "DeleteMarkers" in data:
            delete_markers = process_deletes(data["DeleteMarkers"])
            # print("Debug delete markers:", json.dumps(delete_markers, indent=2)) # Debugging

        versions = process_versions(data["Versions"])
        # print(json.dumps(versions, indent=2)) # Debugging

    data = combine_deleted_and_versions(delete_markers, versions)
    # print(json.dumps(data, indent=2)) # Debugging

    stats = get_file_stats(data)
    print_file_stats(stats)


main(ARGS.file)
