#!/bin/bash

if [ $# -ne 1 ]
then
  echo "1 paraméter kötelező: input fájl (conll treebank)"
  exit 1;
fi

INPUTFILE=$1
INPUTLANG=$(basename "$INPUTFILE")
# Inputfile nevek kétbetűs nyelvazonosítók kellenek, hogy legyenek!

ODIR=mazsdb

BASE=$(basename "$INPUTFILE")

O1=${BASE}.verbose
O2=${BASE}

# Output in JSON, make a freqlist, and put freq value into the JSON
python3 ./process_conll.py --input-file "$INPUTFILE" --language "$INPUTLANG" --logfile "$ODIR/$O1" -f JSON \
 | sort | uniq -c | sort -nr | awk '{$3 = $1","; for (i = 1; i < NF; i++) {$i = $(i+1)}; print}' > "$ODIR/$O2"

