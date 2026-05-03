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

# Output in JSON, group by to get freqs and collect span values for each entry
python3 ./process_conll.py --input-file "$INPUTFILE" --language "$INPUTLANG" --logfile "$ODIR/$O1" -f JSON | \
  jq -sc 'sort_by(del(.span)) | group_by(del(.span)) | map(.[0] + {freq: length}) | sort_by(-.freq) | .[]' | \
  python3 -c "import sys, json; [print(json.dumps(json.loads(line), indent=None, ensure_ascii=False)) for line in sys.stdin]" \
  > "$ODIR/$O2"
