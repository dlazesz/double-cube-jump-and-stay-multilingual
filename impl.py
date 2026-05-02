import sys
import json
import argparse
from collections import defaultdict, Counter


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
        type=int,
        default=100_000_000,
        help="Above this value: backward=jump (if omitting last filler) (default: 1e8)"
    )

    parser.add_argument(
        "--subject_slot",
        type=str,
        required=True,
        help="Subject slot"
    )

    return parser.parse_args()


def process_input(inp_fh, subject_slot):
    for line in inp_fh:
        try:
            d: dict[str, str | None] = json.loads(line)
        except ValueError as err:
            print(f"ValueError: {err}{{{line}}}", file=sys.stderr)
            exit(1)

        d.pop('stem', None)  # Input is is already grouped by the verb stem
        freq = d.pop('freq', None)

        # Adding subjects -- hack, because Hungarian is pro-drop
        # = if there is no subject_slot => add subject_slot:None
        # if 'nsubj' not in d or 'Nom' not in d: TODO which?
        if subject_slot not in d:  # TODO move to CoNLL processing
            d[subject_slot] = None

        yield d, freq


def build_dc_recursively(d, d_json, freq, vertices_freq, vertices_len, edges_backward, edges_forward, visited=None):
    """From a vcc ('d') calculates vccs "shorter by 1" element ('e') recursively, and record the edges and vertices"""
    if visited is None:
        visited = set()  # Visited in this sentence (during the recursion)

    # "shorter by 1" elements = every slot is to be shortened by 1 respectively
    for slot in d:
        e = d.copy()
        if e[slot] is None:  # If no filler -> omit the slot
            del e[slot]
        else:  # If filler -> omit the filler
            e[slot] = None
        e_json = json.dumps(e, ensure_ascii=False)  # vcc: dict format -> string format (= key!)

        # -- enumerating edges = all edges needed starting form the given vertex
        edges_backward[d_json].add(e_json)
        edges_forward[e_json].add(d_json)

        # -- Enumerating vertices = vertices are needed only if not processed yet
        if e_json not in visited:
            visited.add(e_json)
            vertices_freq[e_json] += freq
            vertices_len[e_json] = sum(1 if v is None else 2 for v in e.values())  # = count of slots + count of fillers
            build_dc_recursively(e, e_json, freq, vertices_freq, vertices_len, edges_backward, edges_forward, visited)


def build_corpus_lattice(subject_slot) -> tuple[dict[str, int], dict[str, int], dict[str, set], dict[str, set]]:
    # Corpus lattice
    cl_vertices_freq = Counter()  # Freq of vertices
    cl_vertices_len = {}  # Length of VCCs at vertices
    cl_edges_backward = defaultdict(set)  # Backward edges (= "in"-edges) down in corpus lattice
    cl_edges_forward = defaultdict(set)  # Forward edges (= "out"-edges) up in corpus lattice

    for line, freq in process_input(sys.stdin, subject_slot):
        d = dict(sorted(line.items()))
        d_json = json.dumps(d, ensure_ascii=False)  # vcc: dict format -> string format (= key!)

        # Put in the sentence skeleton
        # Add the root vertex (code repetition from the recursion)
        cl_vertices_freq[d_json] += freq
        cl_vertices_len[d_json] = sum(1 if v is None else 2 for v in d.values())  # = count of slots + count of fillers

        build_dc_recursively(d, d_json, freq, cl_vertices_freq, cl_vertices_len, cl_edges_backward, cl_edges_forward)

    return cl_vertices_freq, cl_vertices_len, cl_edges_backward, cl_edges_forward


def main():
    args = parse_args()
    stay = args.stay
    jump1 = args.jump1
    jump2 = args.jump2
    jump3 = args.jump3

    # -- Build the corpus lattice
    cl_vertices_freq, cl_vertices_len, cl_edges_backward, cl_edges_forward = build_corpus_lattice(args.subject_slot)

    # Take all vertices and filter out which is not needed

    # Process in a king of "good" order:
    # sort: according to length, then reverse freq (by '-' trick), then alphabetical order
    for n, i in enumerate(sorted(cl_vertices_freq, key=lambda x: (cl_vertices_len[x], -cl_vertices_freq[x], x)),
                          start=1):

        print(f'#{n}')

        print_full(i, cl_vertices_freq, cl_vertices_len, cl_edges_backward, cl_edges_forward, stay, jump1)

        # Preliminary filter conditions
        if i not in cl_edges_forward:
            print(' No out-edge, skip.')
        elif cl_vertices_freq[i] < 3:
            print(' Too rare (<3), skip.')
        elif cl_vertices_len[i] > 8:
            print(' Too long (>8), skip.')
        else:
            print(' Processing.')
            process(i, cl_vertices_freq, cl_vertices_len, cl_edges_backward, cl_edges_forward,
                    stay, jump1, jump2, jump3)
        print()


def print_full(i, cl_vertices_freq, cl_vertices_len, cl_edges_backward, cl_edges_forward, stay, jump1):
    freq = cl_vertices_freq[i]

    # Forward edges -- for "stay"
    # Sort: according to freq value, then vcc string-format key
    for j in sorted(cl_edges_forward.get(i, set()), key=lambda x: (cl_vertices_freq[x], x)):
        j_freq = cl_vertices_freq[j]
        ratio = freq / j_freq
        if ratio < stay:
            corpus_lattice = '= !stay'
        elif ratio > jump1:
            corpus_lattice = '^'
        else:
            corpus_lattice = '??'
        print(f'->  {j_freq}  {ratio:2.2f}  {j}  {corpus_lattice}')
    print('x')

    # Backward edges -- for "jump"
    # Sort: according to freq value, then vcc string-format key
    for j in sorted(cl_edges_backward.get(i, set()), key=lambda x: (cl_vertices_freq[x], x)):
        j_freq = cl_vertices_freq[j]
        ratio = j_freq / freq
        if ratio < stay:
            corpus_lattice = '='
        elif ratio > jump1:
            corpus_lattice = '^ !jump'
        else:
            corpus_lattice = '??'
        print(f'<-  {j_freq}  {ratio:2.2f}  {j}  {corpus_lattice}')
    print('x')

    # Current vertex
    print(i, freq, cl_vertices_len[i], sep='\t')


def process(act, cl_vertices_freq, cl_vertices_len, cl_edges_backward, cl_edges_forward, stay, jump1, jump2, jump3):
    """How does it work
        * Is there a stay? -> Perform the step defined by the smallest-ratio stay

        * If no stay, is there a jump? -> Perform the step defined by the largest-ratio jump
            iff there is a filler and there is a filler after the jump as well (jump1)
                or there is no filler at all in the current vertex (jump2)

        * Repeat if a step was made

       So it performs necessary amount of jumps and stays mixed
    """

    path = []  # = Log of jumps and stays

    while True:
        stay_found = True
        jump_found = True

        # Is there a stay?
        # There are always one except at a sentence skeleton
        # Forward vertices
        max_out: str | None = max(cl_edges_forward.get(act, set()), key=lambda x: (cl_vertices_freq[x], x),
                                  default=None)

        freq_act = cl_vertices_freq[act]
        freq_max_out = cl_vertices_freq.get(max_out, 0)
        # Whether 'max_out' stays compared to 'act' (there must be an act..max_out edge!)
        # Freq-ratio on act..max_out edge (there must be an act..max_out edge!)
        if max_out is not None and freq_act / freq_max_out < stay:
            print(' A stay found, we follow.')
            path.append('v')
            # Current vertex
            print(max_out, freq_max_out, cl_vertices_len[max_out], sep='\t')
            act = max_out

        else:
            # Freq-ratio on act..max_out edge (there must be an act..max_out edge!)
            if max_out is not None:
                r1 = freq_act / freq_max_out
            else:
                r1 = 0  # TODO here 0 do not satisfy the gt relation should be inf?

            print(f' No stay (ratio={r1:2.2f} > {stay}), we stop.')
            stay_found = False

            # If no stay, is there a(n appropriate) jump?
            # There are always one except at root
            # Backward vertices
            max_inn: str | None = max(cl_edges_backward.get(act, set()), key=lambda x: (cl_vertices_freq[x], x),
                                      default=None)

            freq_max_inn = cl_vertices_freq[max_inn]
            if max_inn is not None:  # This exists except at root :)
                # Freq-ratio on max_inn..act edge (there must be an max_inn..act edge!)
                r = freq_max_inn / freq_act

                # Whether there is a filler in max_inn or act
                # Need to look at values, whether there is a not-None
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
                if freq_max_inn / freq_act > jump:
                    print(f' An appropriate jump ({info_msg}, {jump}<) found, we follow.')
                    path.append(jump_type)
                    # Current vertex
                    print(max_inn, freq_max_inn, cl_vertices_len[max_inn], sep='\t')
                    act = max_inn
                else:
                    print(f' No appropriate jump ({info_msg}, {r:2.2f} < {jump}), we stop.')
                    jump_found = False

            else:
                print(' No backward edge -- no jump, we stop.')
                jump_found = False

        # Quit the loop when no step was made
        if not stay_found and not jump_found:
            break

    # What to do when we are at an sentence skeleton
    # Current implementation: no sentence skeleton can be a pVCC because there are pVCCS like 'shine sun'
    # Whether 'act' is a sentence skeleton
    # XXX is this condition OK? "it has no forward edge" -- THINK ABOUT IT!
    if act not in cl_edges_forward:
        print(' Concrete sentence skeleton.')
    else:
        # pathstr = '0' if not path else ''.join(path)
        # print(act,freq_act, cl_vertices_len[act], f'[{pathstr}]', pVCC, sep='\t')
        print(act, freq_act, cl_vertices_len[act], 'pVCC', sep='\t')


if __name__ == '__main__':
    main()
