#!/usr/bin/env python3
#
# This script will read in the JSON generated by a ListObjectVersions
# call to Amazon S3, combine the Versions and DeleteMarkers arrays
# into a unified data structure, and print out statistics on disk usage,
# *especially* for things like deleted files.


import argparse
import json
import logging
import os
import sys

import humanize

logging.basicConfig(level=logging.INFO, format='%(asctime)s: %(levelname)s: %(message)s')
logger = logging.getLogger()

#
# Parse our arguments.
#
parser = argparse.ArgumentParser(description = "Get stats from files in an S3 bucket")
#
# This one was a bit tricky, but if I want an optional positional argument,
# I need to set nargs to "?".  Took me like 10 minutes of Googling to figure
# that one out.
#
parser.add_argument("file", nargs="?", help = "JSON file to load", default = "output.json")
parser.add_argument("--humanize", action = "store_true", help = "Humanize output")
#parser.add_argument("--filter", help = "Filename text to filter on")

args = parser.parse_args()
logger.info("Args: %s" % args)


#
# Go through our DeleteMarkers and return a data structure that's
# distilled to just the key and date
#
def processDeletes(data):

	retval = {}

	for row in data:

		ret = {}

		key = row["Key"]
		#is_latest = row["IsLatest"]
		date = row["LastModified"]

		if not key in retval:
			#
			# New marker, just drop in our data
			#
			#ret["is_latest"] = is_latest
			ret["latest_modified"] = date
			retval[key] = ret

		else:
			#
			# This file already has a delete marker, so
			# check the date.
			#
			if date > retval[key]["latest_modified"]:
				retval[key]["lastest_modified"] = date

		
	return(retval)


#
# Go through our Versions and return a data strucutre that's 
# distilled to just the key, date, total and average sizes, and number of versions.
#
def processVersions(data):

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
	# Now calulate average file size
	#
	for key, row in retval.items():
		size = row["total_size"]
		num = row["num_versions"]
		row["average_size"] = size / num

	return(retval)


#
# Any object that is a folder ends in a slash. Check for that.
#
def isFolder(filename):

	retval = False

	index = len(filename) - 1

	if filename[index] == "/":
		retval = True

	return(retval)


#
# Combine our Delete Markers and Versions into a single unified dictionary.
#
def combineDeletedAndVersions(delete_markers, versions):

	#
	# Start by copying our Delete Markers into the data structure
	#
	retval = delete_markers

	#
	# Now go through our Versions, and merge them in.
	#
	for key, row in versions.items():

		is_folder = isFolder(key)

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

		retval[key]["is_folder"] = is_folder


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
			row["is_folder"] = isFolder(key)
			row["total_size"] = 0
			row["num_versions"] = 0

	return(retval)


#
# Go through our files and get stats
#
def getFileStats(data):

	retval = {}
	retval["present"] = {}
	retval["present"]["num_files"] = 0
	retval["present"]["num_versions"] = 0
	retval["present"]["total_size"] = 0
	retval["present"]["average_size"] = 0
	retval["deleted"] = {}
	retval["deleted"]["num_files"] = 0
	retval["deleted"]["num_versions"] = 0
	retval["deleted"]["total_size"] = 0
	retval["deleted"]["average_size"] = 0

	for key, row in data.items():

		status = row["status"]

		is_folder = row["is_folder"]
		total_size = row["total_size"]
		num_versions = row["num_versions"]


		#
		# Folders are essentially metadata and don't take up
		# disk space, so don't bother with them.
		#
		if is_folder:
			continue

		if status == "present":
			#print("PRESENT", key) # Debugging
			retval["present"]["num_files"] += 1
			retval["present"]["num_versions"] += row["num_versions"]
			retval["present"]["total_size"] += row["total_size"]

		elif status == "deleted":
			#print("ABSENT", key) # Debugging
			retval["deleted"]["num_files"] += 1
			retval["deleted"]["num_versions"] += row["num_versions"]
			retval["deleted"]["total_size"] += row["total_size"]

		else:
			raise Exception("Unknown status: %s" % status)

	retval["present"]["average_size"] = retval["present"]["total_size"] / retval["present"]["num_versions"]
	retval["deleted"]["average_size"] = retval["deleted"]["total_size"] / retval["deleted"]["num_versions"]

	return(retval)


#
# Print up our file stats.
#
def printFileStats(stats):

	if not args.humanize:
		print(json.dumps(stats, indent=2)) 

	else:
		#
		# If we're humanizing, do that on our bytecounts and totals
		#
		for key, row in stats.items():
			for key2, row2 in row.items():

				if "_size" in key2:
					row2 = humanize.naturalsize(row2, binary = True, gnu = True)
					row[key2] = row2

				elif "num_" in key2:
					row2 = humanize.intcomma(row2)
					row[key2] = row2

		print()

		format = "%10s: %s: %s"
		for key, row in stats["present"].items():
			print(format % ("Present", key, row))

		print()

		for key, row in stats["deleted"].items():
			print(format % ("Deleted", key, row))

		print()



#
# Our main function, which reads from the input file, processes the data,
# and prints the results.
#
def main(input):

	with open(input) as f:
		data = json.load(f)

		delete_markers = processDeletes(data["DeleteMarkers"])
		#print(json.dumps(delete_markers, indent=2)) # Debugging

		versions = processVersions(data["Versions"])
		#print(json.dumps(versions, indent=2)) # Debugging

	data = combineDeletedAndVersions(delete_markers, versions)
	#print(json.dumps(data, indent=2)) # Debugging

	stats = getFileStats(data)
	printFileStats(stats)


main(args.file)



