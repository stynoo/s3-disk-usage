#!/bin/bash
#
# Wrapper script to download a bucket's contents, cache
# the results, and then report on the contents of that bucket.
#

# Errors are fatal
set -e

#
# Print our syntax and exit.
#
function printSyntax() {

	echo "! "
	echo "! Syntax: $0 bucket"
	echo "! "
	exit 1

} # End of printSyntax()


#
# Parse our args
#
function parseArgs() {

	while test "$1"
	do
		ARG=$1
		shift

		if test "$ARG" == "-h" -o "$ARG" == "--help"
		then
			printSyntax

		else
			BUCKET=$ARG

		fi

	done

	if test ! "$BUCKET"
	then
		printSyntax
	fi

} # End of parseArgs()


parseArgs $@
OUTPUT="$BUCKET.json"


#
# If the output file already exists, skip re-fetching it.
#
if test -f "$OUTPUT"
then
	echo "# " 1>&2
	echo "# Output file '$OUTPUT' already exists, skipping!" 1>&2
	echo "# " 1>&2

else 
	./a_get_bucket_contents.py $BUCKET $OUTPUT

fi

./b_process_bucket_contents.py $OUTPUT --humanize
#./b_process_bucket_contents.py $OUTPUT 


