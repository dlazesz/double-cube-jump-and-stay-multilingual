import sys
import json
import argparse


def parse_args():
    parser = argparse.ArgumentParser(description="Configure jump/stay thresholds and subject slot")

    # 3. "full-free jump and stay" = 4,4,inf -> this is in the paper!
    # 4. "refined jump and stay" = 4,9,100

    parser.add_argument(
        "--stay",
        type=float,
        default=1.7,
        help="Below this value: forward=stay (default: 1.7)"
    )

    parser.add_argument(
        "--jump1",
        type=float,
        default=4,
        help="Above this value: backward=jump (if keeping a filler) (default: 4)"
    )

    parser.add_argument(
        "--jump2",
        type=float,
        default=4,
        help="Above this value: backward=jump (if no filler) (default: 4)"
    )

    parser.add_argument(
        "--jump3",
        type=float,
        default=1e8,
        help="Above this value: backward=jump (if omitting last filler) (default: 1e8)"
    )

    parser.add_argument(
        "--subject_slot",
        type=str,
        required=True,
        help="Subject slot"
    )

    return parser.parse_args()


# From a vcc ('d') calculates vccs "shorter by 1" element ('e') recursively, and record the resulting edges and vertices
def build_dc_recursively(d: dict[str, str | None], freq, vertices_freq, vertices_len, edges_backward, edges_forward):
    slots = sorted(d.keys())
    d_json = json.dumps(dict(sorted(d.items())), ensure_ascii=False)  # vcc: dict format -> string format (= key!)

    # "shorter by 1" elements = every slot is to be shortened by 1 respectively
    for slot in slots:
        e = d.copy()
        if e[slot] is None:  # If no filler -> omit the slot
            del e[slot]
        else:  # If filler -> omit the filler
            e[slot] = None
        e_json = json.dumps(dict(sorted(e.items())), ensure_ascii=False)  # vcc: dict format -> string format (= key!)

        # Point: process every vertex exactly _once_,
        #        plus every edge from the given vertex -- OK!
        #        during building of corpus lattice handle vertices and edges at the same time
        #        (=> thus the structure must be traversed only once)
        #        edge values should be read from vertices -- this is completely OK!

        # -- enumerating edges = all edges needed starting form the given vertex
        #    data structure: 2x dict = dict according to startpoints
        #                    endpoints in dict (value = '1' if exists)
        #    XXX maybe: should be better with a set -- but OK for now :)
        if d_json not in edges_backward:
            edges_backward[d_json] = {}
        edges_backward[d_json][e_json] = 1
        if e_json not in edges_forward:
            edges_forward[e_json] = {}
        edges_forward[e_json][d_json] = 1

        # -- Enumerating vertices = vertices are needed only if not processed yet
        if e_json not in vertices_freq:  # every vertex counted only once
            # => every build_dc_recursively() step gets to
            #    a given vertex only once!
            # -- this implements the metric on the poster
            vertices_freq[e_json] = freq
            vertices_len[e_json] = len(e.keys()) + len(list(filter(lambda x: x is not None, e.values())))
            if len(e) > 0:
                build_dc_recursively(e, freq, vertices_freq, vertices_len, edges_backward, edges_forward)


def print_full(i, corpus_lattice_vertices_freq, corpus_lattice_vertices_len, corpus_lattice_edges_backward,
               corpus_lattice_edges_forward, stay, jump1):
    freq = corpus_lattice_vertices_freq[i]

    # Forward edges -- for "stay"
    if i in corpus_lattice_edges_forward:
        d = corpus_lattice_edges_forward[i]
        # sort: according to freq value, then vcc string-format key
        for j in sorted(d.keys(), key=lambda x: (corpus_lattice_vertices_freq[x], x)):
            ratio = freq / corpus_lattice_vertices_freq[j]
            corpus_lattice = '??'
            if ratio < stay:
                corpus_lattice = '= !stay'
            if ratio > jump1:
                corpus_lattice = '^'
            print(f'->  {corpus_lattice_vertices_freq[j]}  {ratio:2.2f}  {j}  {corpus_lattice}')
    print('x')

    # Backward edges -- for "jump"
    if i in corpus_lattice_edges_backward:
        d = corpus_lattice_edges_backward[i]
        # Sort: according to freq value, then vcc string-format key
        for j in sorted(d.keys(), key=lambda x: (corpus_lattice_vertices_freq[x], x)):
            ratio = corpus_lattice_vertices_freq[j] / freq
            corpus_lattice = '??'
            if ratio < stay:
                corpus_lattice = '='
            if ratio > jump1:
                corpus_lattice = '^ !jump'
            print(f'<-  {corpus_lattice_vertices_freq[j]}  {ratio:2.2f}  {j}  {corpus_lattice}')
    print('x')

    # Current vertex
    print(i, corpus_lattice_vertices_freq[i], corpus_lattice_vertices_len[i], sep='\t')


def main():
    args = parse_args()
    stay = args.stay
    jump1 = args.jump1
    jump2 = args.jump2
    jump3 = args.jump3
    subject_slot = args.subject_slot

    # -- Build the corpus lattice

    # Idea #3: "jump and stay from root vertex"

    # Corpus lattice
    corpus_lattice_vertices_freq = {}  # freq of vertices
    corpus_lattice_vertices_len = {}  # length of VCCs at vertices
    corpus_lattice_edges_backward = {}  # backward edges (= "in"-edges) down in corpus lattice
    corpus_lattice_edges_forward = {}  # forward edges (= "out"-edges) up in corpus lattice

    for line in sys.stdin:
        try:
            d: dict[str, str | None] = json.loads(line)
        except ValueError as err:
            print(f"ValueError: {err}{{{line}}}", file=sys.stderr)
            exit(1)

        freq = d.pop('freq', None)
        d.pop('stem', None)

        # Adding subjects -- hack, because Hungarian is pro-drop
        # = if there is no subject_slot => add subject_slot:None
        # if 'nsubj' not in d or 'Nom' not in d: TODO which?
        if subject_slot not in d:  # TODO move to CoNLL processing
            d[subject_slot] = None

        # Data for the given sentence skeleton:
        vertex_data_freq = {}  # vertex-data: freqs
        vertex_data_len = {}  # vertex-data: lengths
        edge_data = {}  # edge-data
        edge_data_backwards = {}  # edge-data -- backwards!

        d_json = json.dumps(dict(sorted(d.items())), ensure_ascii=False)  # vcc: dict format -> string format (= key!)
        # XXX maybe: d_json = line -- there would be no need for converting forth and back

        # Put in the sentence skeleton
        # XXX ugly: code repetition from build_dc_recursively()
        length = len(d.keys()) + len(list(filter(lambda x: x is not None, d.values())))
        vertex_data_freq[d_json] = freq
        vertex_data_len[d_json] = length  # = count of slots + count of fillers

        build_dc_recursively(d, freq, vertex_data_freq, vertex_data_len, edge_data, edge_data_backwards)
        # algo: edges and vertices for each sentence skeleton
        # plus: put together afterwards below -- THAT IS OK!

        # Transfer vertices of the given sentence skeleton into main 'corpus_lattice_vertices_freq': freqs
        for k in vertex_data_freq:
            if k not in corpus_lattice_vertices_freq:
                corpus_lattice_vertices_freq[k] = vertex_data_freq[k]
            else:
                corpus_lattice_vertices_freq[k] += vertex_data_freq[k]
        # Transfer vertices of the given sentence skeleton into main 'corpus_lattice_vertices_len': vcc lengths
        for k in vertex_data_len:
            if k not in corpus_lattice_vertices_len:
                corpus_lattice_vertices_len[k] = vertex_data_len[k]
        # Transfer edges of the given sentence skeleton into main 'corpus_lattice_edges_backward'
        for i in edge_data:
            for j in edge_data[i]:
                if i not in corpus_lattice_edges_backward:
                    corpus_lattice_edges_backward[i] = {}
                corpus_lattice_edges_backward[i][j] = 1
        # Transfer edges of the given sentence skeleton into main 'corpus_lattice_edges_forward'
        for i in edge_data_backwards:
            for j in edge_data_backwards[i]:
                if i not in corpus_lattice_edges_forward:
                    corpus_lattice_edges_forward[i] = {}
                corpus_lattice_edges_forward[i][j] = 1

    # Take all vertices and filter out which is not needed
    # point: not to miss any which is needed! :)

    # Process in a king of "good" order:
    # According to length, then reverse freq (by '-' trick), then alphabetical order
    for n, i in enumerate(sorted(corpus_lattice_vertices_freq,
                                 key=lambda x: (corpus_lattice_vertices_len[x],
                                                -corpus_lattice_vertices_freq[x], x)), start=1):

        print(f'#{n}')

        print_full(i, corpus_lattice_vertices_freq, corpus_lattice_vertices_len, corpus_lattice_edges_backward,
                   corpus_lattice_edges_forward, stay, jump1)

        # Preliminary filter conditions -- THINK ABOUT IT!
        #  -- only if has out-edge
        #  -- only if freq >= 3
        #  -- only if l <= 8
        if i not in corpus_lattice_edges_forward:
            print(' No out-edge, skip.')
        elif corpus_lattice_vertices_freq[i] < 3:
            print(' Too rare (<3), skip.')
        elif corpus_lattice_vertices_len[i] > 8:
            print(' Too long (>8), skip.')
        else:
            print(' Processing.')

            # How does it work
            #
            #  * Is there a stay?
            #    -> perform the step defined by the smallest-ratio stay
            #
            #  * If no stay, is there a jump?
            #    -> perform the step defined by the largest-ratio jump
            #       iff there is a filler and there is a filler after the jump as well (jump1)
            #           or there is no filler at all in the current vertex (jump2)
            #
            #  * Do it again if a step was made
            #
            # So it performs necessary amount of jumps and stays mixed

            act = i

            path = []  # = log of jumps and stays

            while True:
                stay_found = True
                jump_found = True

                # Is there a stay?
                max_out = None
                d = corpus_lattice_edges_forward.get(act, {})  # Forward vertices
                # There are always one except at a sentence skeleton

                if d:
                    max_out = max(d.keys(), key=lambda x: (corpus_lattice_vertices_freq[x], x))

                # Whether 'max_out' stays compared to 'act' (there must be an act..max_out edge!)
                # freq-ratio on act..max_out edge (there must be an act..max_out edge!)
                if max_out and corpus_lattice_vertices_freq[act] / corpus_lattice_vertices_freq[max_out] < stay:
                    print(' A stay found, we follow.')
                    path.append('v')
                    # Current vertex
                    print(max_out, corpus_lattice_vertices_freq[max_out],
                          corpus_lattice_vertices_len[max_out], sep='\t')
                    act = max_out

                else:
                    # freq-ratio on act..max_out edge (there must be an act..max_out edge!)
                    # TODO bug in the oroginal program ratio() returns only one value
                    r1, r2 = ((corpus_lattice_vertices_freq[act] / corpus_lattice_vertices_freq[max_out], 0)
                              if max_out else float('inf'), stay)
                    print(f' No stay (ratio={r1:2.2f} > {r2}), we stop.')
                    stay_found = False

                    # If no stay, is there a(n appropriate) jump?
                    max_inn = None
                    d = corpus_lattice_edges_backward.get(act, {})  # Backward vertices
                    # There are always one except at root

                    if d:
                        max_inn = max(d.keys(), key=lambda x: (corpus_lattice_vertices_freq[x], x))

                    if max_inn:  # This exists except at root :)
                        # Freq-ratio on max_inn..act edge (there must be an max_inn..act edge!)
                        r = corpus_lattice_vertices_freq[max_inn] / corpus_lattice_vertices_freq[act]
                        jump = None
                        info_msg = None
                        jump_type = None

                        # Whether there is a filler in max_inn or act
                        # Meed to look at values, whether there is a not-None
                        # There is a not-False (None is False)
                        has_filler_max_inn = any(json.loads(max_inn).values())
                        has_filler_act = any(json.loads(act).values())
                        # 3 different cases which covers all possibilities
                        # XOR: There is a filler and there is a filler after the jump as well
                        if has_filler_max_inn:
                            jump = jump1
                            info_msg = 'keeping a filler'
                            jump_type = 't(k)'
                        # XOR: There is no filler at all in the current vertex
                        elif not has_filler_act:
                            jump = jump2
                            info_msg = 'no filler'
                            jump_type = 't(n)'
                        # XOR: There is one filler and the jump omits it
                        elif has_filler_act and not has_filler_max_inn:
                            jump = jump3
                            info_msg = 'omitting last filler'
                            jump_type = 't(o)'
                        else:
                            print(' impossible outcome')
                            exit(1)

                        # Check whether the jump is OK
                        # Is jump? Whether 'max_inn' jumps compared to 'act' (there must be a max_inn..act edge!)
                        # Freq-ratio on max_inn..act edge (there must be an max_inn..act edge!)
                        if corpus_lattice_vertices_freq[max_inn] / corpus_lattice_vertices_freq[act] > jump:
                            print(f' An appropriate jump ({info_msg}, {jump}<) found, we follow.')
                            path.append(jump_type)
                            # Current vertex
                            print(max_inn, corpus_lattice_vertices_freq[max_inn],
                                  corpus_lattice_vertices_len[max_inn], sep='\t')
                            act = max_inn
                        else:
                            print(f' No appropriate jump ({info_msg}, {r:2.2f} < {jump}), we stop.')
                            jump_found = False

                    else:
                        print(' No backward edge -- no jump, we stop.')
                        jump_found = False

                # Quit the loop when no step was made
                if not stay_found and not jump_found: break

            # What to do when we are at an sentence skeleton
            # Current implementation: no sentence skeleton can be a pVCC -- THINK ABOUT IT!
            # Because there are pVCCS like 'shine sun'
            # Whether 'act' is a sentence skeleton
            # XXX is this condition OK? "it has no forward edge" -- THINK ABOUT IT!
            if act not in corpus_lattice_edges_forward:
                print(' Concrete sentence skeleton.')
            else:
                # pathstr = '0' if not path else ''.join(path)
                # print(act,corpus_lattice_vertices_freq[act], corpus_lattice_vertices_len[act],
                #       f'[{pathstr}]', pVCC, sep='\t')
                print(act, corpus_lattice_vertices_freq[act], corpus_lattice_vertices_len[act], 'pVCC', sep='\t')
        print()


if __name__ == '__main__':
    main()
