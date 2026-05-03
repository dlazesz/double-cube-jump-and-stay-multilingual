"""
This module creates "functional annotation"
from a CoNLL(-like) treebank.
That is: creates a Mazsola-like database
from verbs and their direct exts.
(ext in {dependent, argument, complement, adjunct})
"""

import json
import sys
import logging
import argparse
import fileinput
from logging import Logger
from typing import Any

# CoNLL fields -- last two added by this module
(ID, FORM, LEMMA, UPOS, XPOS, FEATS, HEAD, DEPREL, DEPS, MISC,
 FEATS_DIC, SLOT) = range(12)

FEAT_ITEM_SEP = '|'
FEAT_VAL_SEP = '='  # UD v2.4: '=' <--> UD v2.0: '_'

NOSLOT = '_'

ROOT_UPOS = 'VERB'

# ----- language specific tricks to improve annotation

VERB_PARTICLE = {
    'compound:prt', 'compound:preverb',  # UD
    'PREVERB'  # e-magyar
}

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

PRON_LEMMAS = {  # based directly on lemma
    'navzájem',  # cs
    'sich', 'einander',  # de
    # en(each other) ??? XXX XXX XXX
    'birbiri',  # tr
    #'maga', 'egymás' # hu -- is this needed for e-magyar annotation?
}


# ----- end of tricks

# Helper to add a handler
def add_handler(logger, target, level, formatter, is_stream=True):
    if is_stream:
        handler = logging.StreamHandler(target)
    else:
        handler = logging.FileHandler(target)
    handler.setLevel(level)
    handler.setFormatter(formatter)
    logger.addHandler(handler)


def setup_logger(log_file):
    logger = logging.getLogger(__name__)
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
            add_handler(logger, log_file, logging.DEBUG, formatter, is_stream=False)
        else:
            # Only log INFO to STDOUT
            add_handler(logger, sys.stdout, logging.INFO, formatter)

    return logger


def determine_slot(deprel, feats_dic):
    # determine "slot" = the category of the word as an ext
    slot = NOSLOT

    # 0. basic arguments
    #    * UD: we need them here because 'Case' feature is mostly missing
    #    * e-magyar: this step is not needed as we always have 'Case' feature
    if deprel in {
        # 'NEG',
        'nsubj', 'obj', 'iobj', 'obl'
    }:
        slot = deprel

    # 1. if not present: take the 'Case' feature
    #    * UD: needed
    #    * e-magyar: this is the main info on category
    elif 'Case' in feats_dic:
        slot = feats_dic['Case']

    # 2. if not present: other deprel
    #    * UD: case, xcomp <- http://ud.org/u/dep
    #    * e-magyar: INF
    elif deprel in {
        'case', 'xcomp',
        'INF',
    }:
        slot = deprel

    # 3. if not present: Hungarian postposition
    #    * UD: not needed
    #    * e-magyar: needed
    elif deprel == '[/Post]':
        slot = 'NU'

    ## 4. if not present: maybe based on part of speech
    ## UPOS = 'ADV' -- omitted based on experiments on Hungarian

    return slot


class FeatsParseError(ValueError):
    pass


def parse_feats_dict(feats: str, row):
    """Feats -> feats_dic (specific format -> python data structure)"""

    if feats == '_':
        return {}

    feats_dic = {}

    try:
        for e in feats.split(FEAT_ITEM_SEP):
            x, y = e.split(FEAT_VAL_SEP, maxsplit=1)
            feats_dic[x] = y
    except ValueError as e:
        raise FeatsParseError(f"Invalid FEATS: {feats} | row={row}") from e

    return feats_dic


def print_vcc(verb_lemma, exts, span, include_unknown_slots, output_format, logfile, logger):
    """Print out the verb centered construction = verb + exts (in alphabetical order)"""
    exts_out = ''
    ext_out_w_unknown = ''
    exts_sorted = sorted(exts)
    if len(exts) > 0:
        exts_out = f' {" ".join(exts_sorted)}'
        if not include_unknown_slots:
            exts_sorted_wo_unknown_slots = [ext for ext in exts_sorted if not ext.startswith('_@@')]
            if len(exts_sorted_wo_unknown_slots) > 0:
                ext_out_w_unknown = exts_out
                exts_out = f' {" ".join(exts_sorted_wo_unknown_slots)}'

    #     include_unknown_slots: info == debug -> log to info (appears in both)
    # not include_unknown_slots: info != debug -> log to both (debug includes unknown slots)
    # not include_unknown_slots and logfile == '-' -> Conflict, handled elsewhere!
    if not include_unknown_slots and logfile != '-':
        logger.debug(f'stem@@{verb_lemma}{ext_out_w_unknown}')

    if output_format == 'JSON':
        # Dummy freq for later
        out = {'freq': 0, 'stem': verb_lemma, 'span': span}
        # TODO this line kills double keys!
        # Space, literal qoute (\") and at sign (@) in value is handled incorrectly in the original code
        # TODO originally stem not in JSON (JSON is generated as a separate step)
        out.update(ext.replace('POSS', '').replace(' ', '_').split('@@', maxsplit=1)
                   for ext in exts_sorted if not ext.startswith('_@@'))
        for k, v in out.items():
            if v == 'NULL':
                out[k] = None
        logger.info(json.dumps(out, ensure_ascii=False))
    elif output_format == 'mazsola':
        logger.info(f'stem@@{verb_lemma}{exts_out}')
    else:
        raise NotImplementedError(f'Unknown output format: {output_format}')


def process_sentence(sentence, inputlang, include_unknown_slots, output_format, logfile, logger: Logger):
    xcomp_particle = XCOMP_PARTICLE.get(inputlang)
    span_ids = []
    for ri, root in enumerate(sentence, start=1):
        logger.debug(' '.join(root[ID:DEPS]))

        if root[UPOS] != ROOT_UPOS:
            continue

        span_ids.append(ri)  # Track root index
        verb_lemma = root[LEMMA]  # We have the root (=VERB) here

        exts = []

        # Add morphological info of root as separate slot
        #
        # -- VERB
        # if 'Mood' in root[FEATS_DIC] and root[FEATS_DIC]['Mood'] != 'Ind':
        #    exts.append('mood@@' + root[FEATS_DIC]['Mood'])
        #
        # -- ADJ
        # for feat, default_value in (('Case', 'Nom'), ('Degree', 'Pos'), ('Number', 'Sing')):
        #    if feat in root[FEATS_DIC] and root[FEATS_DIC][feat] != default_value:
        #        exts.append(f'{feat}@@{root[FEATS_DIC][feat]}')

        # Exts of the verb -- with simple loops (not slow)
        for ei, ext in enumerate(sentence, start=1):  # Direct exts
            if ext[HEAD] != root[ID]:
                continue

            span_ids.append(ei)  # Track ext index

            if ext[SLOT] != NOSLOT:
                slot = ext[SLOT]

                # Add morphological info of ext as separate slot
                # if 'Number' in ext[FEATS_DIC] and ext[FEATS_DIC]['Number'] != 'Sing':
                #    exts.append(slot + '/number@@' + ext[FEATS_DIC]['Number'])

                # Exts of the exts = amend slot with prepositions/postpositions
                for eei, extofext in enumerate(sentence, start=1):
                    if extofext[HEAD] != ext[ID]:
                        continue

                    if (extofext[UPOS] == 'ADP' or (
                            extofext[UPOS] == 'PART' and
                            xcomp_particle is not None and
                            extofext[LEMMA] == xcomp_particle
                    )):
                        span_ids.append(eei)  # Track child index
                        prep = extofext[LEMMA].lower()
                        # 'de': handle german contractions: am -> an
                        if inputlang == 'de' and prep in DE_CONTRACTIONS:
                            prep = DE_CONTRACTIONS[prep]
                        slot += f'={prep}'
                    # Handle e-magyar Hungarian postpositions which are annotated inversely -> should be inverted
                    if slot == 'NU':
                        slot = '='.join((extofext[FEATS_DIC].get('Case', 'notdef'), ext[LEMMA]))
                        ext[LEMMA] = extofext[LEMMA]
                    # Adjective as second level ext (in a multilevel setting!)
                    # if extofext[DEPREL] == 'ATT' and extofext[UPOS] == 'ADJ':
                    #    exts.append(slot + '+ATT' + '@@' + extofext[LEMMA])

                # Lemma
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

            # Add verb particle / preverb to the verb lemma
            # Verb particle / preverb must be a NOSLOT!
            elif ext[DEPREL] in VERB_PARTICLE:
                verb_lemma = ext[LEMMA] + verb_lemma

        # Handle special 'perverb+verb' format in UD/hu -> delete the '+'
        verb_lemma = verb_lemma.replace('+', '')

        span = []
        if len(span_ids) > 0:
            start = min(span_ids)
            end = max(span_ids)

            # TODO this makes sort impossible later
            span = ' '.join(t[FORM].replace(' ', '_') for t in sentence[start - 1:end])  # UD IDs are 1-based
            span_ids.clear()

        # TODO Find a better place for this
        # Adding subjects -- hack, because Hungarian is pro-drop
        # = if there is no subject_slot => add subject_slot:None
        if all(not e.startswith('Nom@@') for e in exts):
            exts.append('Nom@@NULL')
        print_vcc(verb_lemma, exts, span, include_unknown_slots, output_format, logfile, logger)


def main():
    """
    Process sentences.
    Take verbs and output them together with info on their direct exts.
    """
    args = get_args()
    inputlang = args.language
    logfile = args.logfile
    include_unknown_slots = args.include_unknown_slots
    output_format = args.output_format
    if logfile == '-' and not include_unknown_slots:
        print('--logfile - and --no-include-unknown-slots are mutually exclusive to prevent duplications!',
              file=sys.stderr)
        exit(1)

    logger = setup_logger(logfile)

    with fileinput.input(args.input_file, encoding='UTF-8') as fd:
        sentence = []
        for row in fd:
            row: Any = row.strip()
            if row.startswith('# '):  # Comment line (starts with hashmark and space)
                continue
            if len(row) > 0:  # Line is not empty => process this token
                row = row.split('\t')

                feats_dic = parse_feats_dict(row[FEATS], row)
                logger.debug(sorted(feats_dic))
                slot = determine_slot(row[DEPREL], feats_dic)

                row.append(feats_dic)  # 11th field
                row.append(slot)  # 12th field

                sentence.append(row)

            elif len(row) == 0:  # Empty line = end of sentence => process the whole sentence
                process_sentence(sentence, inputlang, include_unknown_slots, output_format, logfile, logger)
                logger.debug('\n-----\n')
                sentence.clear()
            else:
                raise NotImplementedError('This should not happen!')

        if len(sentence) > 0:  # Final sentence if there is no empty line at the end of file
            process_sentence(sentence, inputlang, include_unknown_slots, output_format, logfile, logger)
            logger.debug('\n-----\n')


def get_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        '-i', '--input-file',
        help='CoNLL(-like) input file or STDIN (default)',
        type=str,
        default='-'
    )
    parser.add_argument(
        '-l', '--language',
        help='2-letter language code for language specific tricks',
        required=True,
        type=str
    )
    parser.add_argument(
        "-f", "--output_format",
        choices=["JSON", "mazsola"],
        default="mazsola",
        help="Output format: JSON or mazsola (default: mazsola)"
    )
    parser.add_argument(
        '--logfile',
        help="Log file path ('-' for STDOUT, default: no verbose logging)",
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
        help='Include unknown slots (_@@) for debugging purposes')
    group.add_argument(
        '--no-include-unknown-slots',
        dest='include_unknown_slots',
        action='store_false',
        help='Do not include unknown slots (_@@) for debugging purposes')

    return parser.parse_args()


if __name__ == '__main__':
    main()
