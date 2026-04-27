#!/bin/bash

if [ $# -ne 1 ]
then
  echo "1 paraméter kötelező: input fájl (processed conll = sentskel)"
  exit 1;
fi

INPUTFILE=$1
INPUTLANG=$(basename "$INPUTFILE")
# Inputfile nevek kétbetűs nyelvazonosítók kellenek, hogy legyenek!

ODIR=json

# 20 esetén már pár magyar ige is akad... :)  TODO 20 mi? Jelenleg frame type
FQTH=20

# Get verbs
sed 's/.*"stem": "\([^"]*\)".*/\1/' "$INPUTFILE" | sort | uniq -c | sort -nr | \
  awk -v fqth="$FQTH" '$1 >= fqth {print $2}' \
  > "$ODIR/${INPUTLANG}.verbs"

# For each verb above the threshold create a separate file
while read -r VERB; do
  grep -E "\"stem\": \"$VERB\"" "$INPUTFILE" \
    > "$ODIR/${INPUTLANG}_${VERB}.test.json"
done < "$ODIR/${INPUTLANG}.verbs"

