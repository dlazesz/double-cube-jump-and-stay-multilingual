#!/bin/bash

if [ $# -ne 1 ]
then
  echo "1 paraméter kötelező: input fájl (processed conll = sentskel)"
  exit 1;
fi

INPUTFILE=$1
INPUTLANG=$(basename "$INPUTFILE")
# inputfile nevek kétbetűs nyelvazonosítók kellenek, hogy legyenek!

ODIR=json

OUTPUT=$(basename "$INPUTFILE")

# 20 esetén már pár magyar ige is akad... :)
FQTH=20

# Get verbs
sed "s/.*stem@@//;s/ .*//" "$INPUTFILE" | sort | uniq -c | sort -nr | \
  awk -v fqth="$FQTH" '$1 >= fqth' | sed "s/^ *[0-9]* *//" \
  > "$ODIR/${INPUTLANG}.verbs"

# For verbs above the threshold create a separate file with
# 1. All lines of the actual verb
# 2. {"fq": frequency
# 3. Delete anonymous slots
# 4. SLOT@@VAL -> , "SLOT": "VAL"
# 5. Close JSON }
# 6. Remove space between val and comma
# 7. Remove POSS
while read -r VERB; do
  grep -E "stem@@$VERB( |$)" "$INPUTFILE" | sed "s/stem@@$VERB *//" | \
    sed 's/^ *//;s/^\([0-9][0-9]*\)/{"fq": \1/;s/ @@[^ ][^ ]*//g;s/\([^ ][^ ]*\)@@\([^ ][^ ]*\)/, "\1": "\2"/g;s/$/}/;s/ *,/,/g;s/POSS//g' \
    > "$ODIR/${INPUTLANG}_${VERB}.test.json"
done < "$ODIR/${INPUTLANG}.verbs"

