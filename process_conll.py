"""
This module creates "functional annotation"
from a CoNLL(-like) treebank.
That is: creates a Mazsola-like database
from verbs and their direct exts.
(ext in {dependent, argument, complement, adjunct})
"""

import csv
import sys
import logging
import argparse
import fileinput

# CoNLL fields -- last two added by this module
(ID, FORM, LEMMA, UPOS, XPOS, FEATS, HEAD, DEPREL, DEPS, MISC,
 FEATS_DIC, SLOT) = range(12)

FEAT_ITEM_SEP = '|'
FEAT_VAL_SEP = '='  # UD v2.4: '=' <--> UD v2.0: '_'

NOSLOT = '_'

ROOT_UPOS = 'VERB'

# ----- language specific tricks to improve annotation

VERB_PARTICLE = [
    'compound:prt', 'compound:preverb',  # UD
    'PREVERB'  # e-magyar
]

# maybe not needed for other languages (surely not needed for cs and hu)
XCOMP_PARTICLE = {
    'de': 'zu',
    'en': 'to',
    'no': 'å'
}

# from http://fluentu.com/blog/german/german-contractions
DE_CONTRACTIONS = {
    'am': 'an', 'ans': 'an', 'aufs': 'auf', 'beim': 'bei',
    'durchs': 'durch', 'fürs': 'für', 'hinterm': 'hinter',
    'ins': 'in', 'im': 'in', 'übers': 'über', 'ums': 'um',
    'unters': 'unter', 'unterm': 'unter',
    'vom': 'von', 'vors': 'vor', 'vorm': 'vor', 'zum': 'zu', 'zur': 'zu'
}

PRON_LEMMAS = [  # based directly on lemma
    'navzájem',  # cs
    'sich', 'einander',  # de
    # en(each other) ??? XXX XXX XXX
    'birbiri',  # tr
    #'maga', 'egymás' # hu -- is this needed for e-magyar annotation?
]


# ----- end of tricks

# Helper to add a handler
def add_handler(logger, stream_or_file, level, formatter):
    if stream_or_file in {sys.stdout, sys.stderr}:
        handler = logging.StreamHandler(stream_or_file)
    else:
        handler = logging.FileHandler(stream_or_file)
    handler.setLevel(level)
    handler.setFormatter(formatter)
    logger.addHandler(handler)


def setup_logger(log_file):
    logger = logging.getLogger('process_conll')
    # Always capture everything; handlers will filter
    logger.setLevel(logging.DEBUG)
    # Prevent double logging from root
    logger.propagate = False

    # Avoid adding multiple handlers if already configured
    if len(logger.handlers) == 0:
        # Define common log format
        formatter = logging.Formatter('%(message)s')

        if log_file == '-':
            # Log everything to STDOUT at DEBUG level
            add_handler(logger, sys.stdout, logging.DEBUG, formatter)
        elif log_file is not None:
            # Log INFO to STDOUT
            add_handler(logger, sys.stdout, logging.INFO, formatter)
            # Log DEBUG to file
            add_handler(logger, log_file, logging.DEBUG, formatter)
        else:
            # Only log INFO to STDOUT
            add_handler(logger, sys.stdout, logging.INFO, formatter)

    return logger


def main():
    """
    Process sentences.
    Take verbs and output them together with info on their direct exts.
    """
    args = get_args()
    filename = args.input_file
    inputlang = args.language
    logfile = args.logfile
    include_unknown_slots = args.include_unknown_slots
    if logfile == '-' and not include_unknown_slots:
        print('--logfile - and --no-include-unknown-slots are mutually exclusive to prevent duplications!',
              file=sys.stderr)
        exit(1)

    logger = setup_logger(logfile)

    with fileinput.input(filename, encoding='UTF-8') as fd:
        rd = csv.reader(fd, delimiter='\t', quoting=csv.QUOTE_NONE)  # no quoting
        sentence = []
        for row in rd:
            if len(row) == 1 and row[0][0] == '#':  # comment line
                continue
            if len(row) > 0:  # line is not empty => process this token

                # feats -> feats_dic (specific format -> python data structure)
                feats = row[FEATS]
                feats_dic = {}
                if feats != '_':
                    try:
                        for e in feats.split(FEAT_ITEM_SEP):
                            x, y = e.split(FEAT_VAL_SEP, maxsplit=1)
                            feats_dic[x] = y
                    except ValueError:
                        logger.critical(f'FATAL: {feats} :: {{{"}{".join(row)}}}')
                        exit(1)
                logger.debug(sorted(feats_dic))

                # determine "slot" = the category of the word as an ext
                slot = NOSLOT

                # 0. basic arguments
                #    * UD: we need them here because 'Case' feature is mostly missing
                #    * e-magyar: this step is not needed as we always have 'Case' feature
                if row[DEPREL] in {
                    #'NEG',
                    'nsubj', 'obj', 'iobj', 'obl'
                }:
                    slot = row[DEPREL]

                # 1. if not present: take the 'Case' feature
                #    * UD: needed
                #    * e-magyar: this is the main info on category
                elif 'Case' in feats_dic:
                    slot = feats_dic['Case']

                # 2. if not present: other deprel
                #    * UD: case, xcomp <- http://ud.org/u/dep
                #    * e-magyar: INF
                elif row[DEPREL] in {
                    'case', 'xcomp',
                    'INF',
                }:
                    slot = row[DEPREL]

                # 3. if not present: Hungarian postposition
                #    * UD: not needed
                #    * e-magyar: needed
                elif row[XPOS] == '[/Post]':
                    slot = 'NU'

                ## 4. if not present: maybe based on part of speech
                ## UPOS = 'ADV' -- omitted based on experiments on Hungarian

                row.append(feats_dic)  # 11th field
                row.append(slot)  # 12th field

                sentence.append(row)

            else:  # empty line = end of sentence => process the whole sentence

                for root in sentence:
                    logger.debug(' '.join(root[ID:DEPS]))

                    if root[UPOS] != ROOT_UPOS:
                        continue

                    # we have the root (=VERB) here
                    verb_lemma = root[LEMMA]

                    exts = []

                    # add morphological info of root as separate slot
                    #
                    # -- VERB
                    #if 'Mood' in root[FEATS_DIC] and root[FEATS_DIC]['Mood'] != 'Ind':
                    #    exts.append('mood@@' + root[FEATS_DIC]['Mood'])
                    #
                    # -- ADJ
                    #for feat, default_value in (('Case', 'Nom'), ('Degree', 'Pos'), ('Number', 'Sing')):
                    #    if feat in root[FEATS_DIC] and root[FEATS_DIC][feat] != default_value:
                    #        exts.append(f'{feat}@@{root[FEATS_DIC][feat]}')

                    # exts of the verb -- with simple loops (not slow)
                    for ext in sentence:  # direct exts
                        if ext[HEAD] != root[ID]:
                            continue
                        if ext[SLOT] != NOSLOT:
                            slot = ext[SLOT]

                            # add morphological info of ext as separate slot
                            #if 'Number' in ext[FEATS_DIC] and ext[FEATS_DIC]['Number'] != 'Sing':
                            #    exts.append(slot + '/number@@' + ext[FEATS_DIC]['Number'])

                            # exts of the exts = amend slot with prepositions/postpositions
                            for extofext in sentence:
                                if extofext[HEAD] != ext[ID]:
                                    continue
                                if (extofext[UPOS] == 'ADP' or (
                                        extofext[UPOS] == 'PART' and
                                        inputlang in XCOMP_PARTICLE and
                                        extofext[LEMMA] == XCOMP_PARTICLE[inputlang]
                                )):
                                    prep = extofext[LEMMA].lower()
                                    # 'de': handle german contractions: am -> an
                                    if inputlang == 'de' and prep in DE_CONTRACTIONS:
                                        prep = DE_CONTRACTIONS[prep]
                                    slot += f'={prep}'
                                # handle e-magyar Hungarian postpositions
                                # which are annotated inversely -> should be inverted
                                if slot == 'NU':
                                    slot = '='.join((extofext[FEATS_DIC].get('Case', 'notdef'), ext[LEMMA]))
                                    ext[LEMMA] = extofext[LEMMA]
                                # adjective as second level ext (in a multilevel setting!)
                                #if extofext[DEPREL] == 'ATT' and extofext[UPOS] == 'ADJ':
                                #    exts.append(slot + '+ATT' + '@@' + extofext[LEMMA])

                            # lemma
                            lemma = ext[LEMMA].lower()
                            # lemma / handle pronouns
                            # -- only reflexive and rcp are needed as lemma
                            if (ext[UPOS] == 'PRON' and
                                    ext[FEATS_DIC].get('Reflex', 'notdef') != 'Yes' and  # 'itself'
                                    ext[FEATS_DIC].get('PronType', 'notdef') != 'Rcp' and  # 'each other'
                                    ext[LEMMA] not in PRON_LEMMAS
                            ):
                                lemma = 'NULL'

                            exts.append(f'{slot}@@{lemma}')

                        # add verb particle / preverb to the verb lemma
                        # verb particle / preverb must be a NOSLOT!
                        elif ext[DEPREL] in VERB_PARTICLE:
                            verb_lemma = ext[LEMMA] + verb_lemma

                    # handle special 'perverb+verb' format in UD/hu -> delete the '+'
                    verb_lemma = verb_lemma.replace('+', '')

                    # print out the verb centered construction
                    # = verb + exts (in alphabetical order)
                    exts_out = ''
                    if len(exts) > 0:
                        exts_sorted = sorted(exts)
                        exts_out = f' {" ".join(exts_sorted)}'
                        if not include_unknown_slots:
                            exts_sorted_wo_unknown_slots = [ext for ext in exts_sorted if not ext.startwith('_@@')]
                            if len(exts_sorted_wo_unknown_slots) > 0:
                                ext_out_w_unknown = exts_out
                                exts_out = f' {" ".join(exts_sorted_wo_unknown_slots)}'

                    #     include_unknown_slots: info == debug -> log to info (appears in both)
                    # not include_unknown_slots: info != debug -> log to both (debug includes unknown slots)
                    # not include_unknown_slots and logfile == '-' -> Conflict, handled elsewhere!
                    if not include_unknown_slots and logfile != '-':
                        logger.debug(f'stem@@{verb_lemma}{ext_out_w_unknown}')

                    logger.info(f'stem@@{verb_lemma}{exts_out}')

                logger.debug('\n-----\n')
                sentence = []


def get_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    # string-valued argument
    parser.add_argument(
        '-i', '--input-file',
        help='CoNLL(-like) input file or STDIN (default)',
        type=str,
        default='-'
    )
    # string-valued argument
    parser.add_argument(
        '-l', '--language',
        help='2-letter language code for language specific tricks',
        required=True,
        type=str,
        default=argparse.SUPPRESS
    )
    # string-valued argument
    parser.add_argument(
        '--logfile',
        help="A logfile to write debug information ('-' for verbose mode on STDOUT)",
        type=str,
        default=None
    )
    # bool-valued argument
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        '--include-unknown-slots',
        dest='include_unknown_slots',
        action='store_true',
        default=True,
        help='Include unknown slots (_@@) for debuging purposes')
    group.add_argument(
        '--no-include-unknown-slots',
        dest='include_unknown_slots',
        action='store_false',
        help='Don not include unknown slots (_@@) for debuging purposes')

    return parser.parse_args()


if __name__ == '__main__':
    main()
