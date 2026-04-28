import sys
import json
import argparse


def parse_args():
    parser = argparse.ArgumentParser(description="Configure jump/stay thresholds and subject slot.")

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


# from a vcc ('d') calculates vccs "shorter by 1" element ('e') recursively,
# and record the resulting edges and vertices
def build_dc_recursively(d: dict[str, str | None], fq, vertices_f, vertices_l, edges_back, edges_fwrd):
    slots = sorted(d.keys())
    dj = json.dumps(dict(sorted(d.items())), ensure_ascii=False)  # vcc: dict format -> string format (= key!)

    # "shorter by 1" elements = every slot is to be shortened by 1 respectively
    for sl in slots:
        e = d.copy()
        if e[sl] is None:  # if no filler -> omit the slot
            del e[sl]
        else:  # if filler -> omit the filler
            e[sl] = None
        ej = json.dumps(dict(sorted(e.items())), ensure_ascii=False)  # vcc: dict format -> string format (= key!)

        # point: process every vertex exactly _once_,
        #        plus every edge from the given vertex -- OK!
        #        during building of cl handle vertices and edges at the same time
        #        (=> thus the structure must be traversed only once)
        #        edge values should be read from vertices -- this is completely OK!

        # -- enumerating edges = all edges needed starting form the given vertex
        #    data structure: 2x dict = dict according to startpoints
        #                    endpoints in dict (value = '1' if exists)
        #    XXX maybe: should be better with a set -- but OK for now :)
        if dj not in edges_back:
            edges_back[dj] = {}
        edges_back[dj][ej] = 1
        if ej not in edges_fwrd:
            edges_fwrd[ej] = {}
        edges_fwrd[ej][dj] = 1

        # -- enumerating vertices = vertices are needed only if not processed yet
        if ej not in vertices_f:  # every vertex counted only once
            # => every build_dc_recursively() step gets to
            #    a given vertex only once!
            # -- this implements the metric on the poster
            vertices_f[ej] = fq
            vertices_l[ej] = len(e.keys()) + len(list(filter(lambda x: x is not None, e.values())))
            if len(e) > 0:
                build_dc_recursively(e, fq, vertices_f, vertices_l, edges_back, edges_fwrd)


def print_full(i, cl_vertices_f, cl_vertices_l, cl_edges_back, cl_edges_fwrd, stay, jump1):
    fq = cl_vertices_f[i]

    # forward edges -- for "stay"
    if i in cl_edges_fwrd:
        d = cl_edges_fwrd[i]
        # sort: according to fq value, then vcc string-format key
        for j in sorted(d.keys(), key=lambda x: (cl_vertices_f[x], x)):
            ratio = fq / cl_vertices_f[j]
            cl = '??'
            if ratio < stay:
                cl = '= !stay'
            if ratio > jump1:
                cl = '^'
            print(f'->  {cl_vertices_f[j]}  {ratio:2.2f}  {j}  {cl}')
    print('x')

    # backward edges -- for "jump"
    if i in cl_edges_back:
        d = cl_edges_back[i]
        # sort: according to fq value, then vcc string-format key
        for j in sorted(d.keys(), key=lambda x: (cl_vertices_f[x], x)):
            ratio = cl_vertices_f[j] / fq
            cl = '??'
            if ratio < stay:
                cl = '='
            if ratio > jump1:
                cl = '^ !jump'
            print(f'<-  {cl_vertices_f[j]}  {ratio:2.2f}  {j}  {cl}')
    print('x')

    fq1 = cl_vertices_f[i]
    l = cl_vertices_l[i]
    # Current vertex
    print(i, fq1, l, sep='\t')


def main():
    args = parse_args()
    stay = args.stay
    jump1 = args.jump1
    jump2 = args.jump2
    jump3 = args.jump3
    subject_slot = args.subject_slot

    # -- Build the corpus lattice

    # idea #3: "jump and stay from root vertex"

    # corpus lattice
    cl_vertices_f = {}  # freq of vertices
    cl_vertices_l = {}  # length of VCCs at vertices
    cl_edges_back = {}  # backward edges (= "in"-edges) down in cl
    cl_edges_fwrd = {}  # forward edges (= "out"-edges) up in cl

    for line in sys.stdin:
        try:
            d: dict[str, str | None] = json.loads(line)
        except ValueError as err:
            print(f"ValueError: {err}{{{line}}}", file=sys.stderr)
            exit(1)

        fq = d.pop('fq', None)

        # Adding subjects -- hack, because Hungarian is pro-drop
        # = if there is no subject_slot => add subject_slot:None
        if subject_slot not in d:
            d[subject_slot] = None

        # Data for the given sentence skeleton (ss):
        dvfq = {}  # vertex-data: freqs
        dvl = {}  # vertex-data: lengths
        de = {}  # edge-data
        deb = {}  # edge-data -- backwards!

        dj = json.dumps(dict(sorted(d.items())), ensure_ascii=False)  # vcc: dict format -> string format (= key!)
        # XXX maybe: dj = line -- there would be no need for converting forth and back

        # put in the ss
        # XXX ugly: code repetition from build_dc_recursively()
        length = len(d.keys()) + len(list(filter(lambda x: x is not None, d.values())))
        dvfq[dj] = fq
        dvl[dj] = length  # = cnt of slots + cnt of fillers

        build_dc_recursively(d, fq, dvfq, dvl, de, deb)
        # algo: edges and vertices for each ss
        # plus: put together afterwards below -- THAT IS OK!

        # transfer vertices of the given ss into main 'cl_vertices_f': freqs
        for k in dvfq:
            if k not in cl_vertices_f:
                cl_vertices_f[k] = dvfq[k]
            else:
                cl_vertices_f[k] += dvfq[k]
        # transfer vertices of the given ss into main 'cl_vertices_l': vcc lengths
        for k in dvl:
            if k not in cl_vertices_l:
                cl_vertices_l[k] = dvl[k]
        # transfer edges of the given ss into main 'cl_edges_back'
        for i in de:
            for j in de[i]:
                if i not in cl_edges_back:
                    cl_edges_back[i] = {}
                cl_edges_back[i][j] = 1
        # transfer edges of the given ss into main 'cl_edges_fwrd'
        for i in deb:
            for j in deb[i]:
                if i not in cl_edges_fwrd:
                    cl_edges_fwrd[i] = {}
                cl_edges_fwrd[i][j] = 1

    # take all vertices and filter out which is not needed
    # point: not to miss any which is needed! :)

    # process in a king of "good" order:
    # according to length, then reverse fq (by '-' trick), then alphabetical order
    for n, i in enumerate(sorted(cl_vertices_f, key=lambda x: (cl_vertices_l[x], -cl_vertices_f[x], x)), start=1):

        print(f'#{n}')

        print_full(i, cl_vertices_f, cl_vertices_l, cl_edges_back, cl_edges_fwrd, stay, jump1)

        # preliminary filter conditions -- THINK ABOUT IT!
        #  -- only if has out-edge
        #  -- only if fq >= 3
        #  -- only if l <= 8
        if i not in cl_edges_fwrd:
            print(' No out-edge, skip.')
        elif cl_vertices_f[i] < 3:
            print(' Too rare (<3), skip.')
        elif cl_vertices_l[i] > 8:
            print(' Too long (>8), skip.')
        else:
            print(' Processing.')

            # how does it work
            #
            #  * is there a stay?
            #    -> perform the step defined by the smallest-ratio stay
            #
            #  * if no stay, is there a jump?
            #    -> perform the step defined by the largest-ratio jump
            #       iff there is a filler and there is a filler after the jump as well (jump1)
            #           or there is no filler at all in the current vertex (jump2)
            #
            #  * do it again if a step was made
            #
            # so it performs necessary amount of jumps and stays mixed

            act = i

            path = []  # = log of jumps and stays

            while True:
                stay_found = True
                jump_found = True

                # is there a stay?
                max_out = None
                d = cl_edges_fwrd.get(act, {})  # forward vertices
                # there are always one except at a ss

                if d:
                    max_out = max(d.keys(), key=lambda x: (cl_vertices_f[x], x))

                # Whether 'max_out' stays compared to 'act' (there must be an act..max_out edge!)
                # fq-ratio on act..max_out edge (there must be an act..max_out edge!)
                if max_out and cl_vertices_f[act] / cl_vertices_f[max_out] < stay:
                    print(' A stay found, we follow.')
                    path.append('v')
                    # Current vertex
                    print(max_out, cl_vertices_f[max_out], cl_vertices_l[max_out], sep='\t')
                    act = max_out

                else:
                    # fq-ratio on act..max_out edge (there must be an act..max_out edge!)
                    # TODO bug in the oroginal program ratio() returns only one value
                    r1, r2 = (cl_vertices_f[act] / cl_vertices_f[max_out], 0) if max_out else float('inf'), stay
                    print(f' No stay (ratio={r1:2.2f} > {r2}), we stop.')
                    stay_found = False

                    # if no stay, is there a(n appropriate) jump?
                    max_inn = None
                    d = cl_edges_back.get(act, {})  # backward vertices
                    # there are always one except at root

                    if d:
                        max_inn = max(d.keys(), key=lambda x: (cl_vertices_f[x], x))

                    if max_inn:  # this exists except at root :)
                        # fq-ratio on max_inn..act edge (there must be an max_inn..act edge!)
                        r = cl_vertices_f[max_inn] / cl_vertices_f[act]
                        jump = None
                        info_msg = None
                        jump_type = None

                        # Whether there is a filler in max_inn or act
                        # Meed to look at values, whether there is a not-None
                        # There is a not-False (None is False)
                        has_filler_max_inn = any(json.loads(max_inn).values())
                        has_filler_act = any(json.loads(act).values())
                        # 3 different cases which covers all possibilities
                        # xor: there is a filler and there is a filler after the jump as well
                        if has_filler_max_inn:
                            jump = jump1
                            info_msg = 'keeping a filler'
                            jump_type = 't(k)'
                        # xor: there is no filler at all in the current vertex
                        elif not has_filler_act:
                            jump = jump2
                            info_msg = 'no filler'
                            jump_type = 't(n)'
                        # xor: there is one filler and the jump omits it
                        elif has_filler_act and not has_filler_max_inn:
                            jump = jump3
                            info_msg = 'omitting last filler'
                            jump_type = 't(o)'
                        else:
                            print(' impossible outcome')
                            exit(1)

                        # Check whether the jump is OK
                        # Is jump? Whether 'max_inn' jumps compared to 'act' (there must be a max_inn..act edge!)
                        # fq-ratio on max_inn..act edge (there must be an max_inn..act edge!)
                        if cl_vertices_f[max_inn] / cl_vertices_f[act] > jump:
                            print(f' An appropriate jump ({info_msg}, {jump}<) found, we follow.')
                            path.append(jump_type)
                            # Current vertex
                            print(max_inn, cl_vertices_f[max_inn], cl_vertices_l[max_inn], sep='\t')
                            act = max_inn
                        else:
                            print(f' No appropriate jump ({info_msg}, {r:2.2f} < {jump}), we stop.')
                            jump_found = False

                    else:
                        print(' No backward edge -- no jump, we stop.')
                        jump_found = False

                # quit the loop when no step was made
                if not stay_found and not jump_found: break

            # what to do when we are at an ss
            # current implementation: no ss can be a pVCC -- THINK ABOUT IT!
            # because there are pVCCS like 'shine sun'
            # whether 'act' is a ss
            # XXX is this condition OK? "it has no forward edge" -- THINK ABOUT IT!
            if act not in cl_edges_fwrd:
                print(' Concrete sentence skeleton.')
            else:
                #pathstr = '0' if not path else ''.join( path )
                #print(act,cl_vertices_f[act], cl_vertices_l[act], f'[{pathstr}]', pVCC, sep='\t')
                print(act, cl_vertices_f[act], cl_vertices_l[act], 'pVCC', sep='\t')
        print()


if __name__ == '__main__':
    main()
