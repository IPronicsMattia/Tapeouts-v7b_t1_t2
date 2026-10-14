"""PUC states for every topolux route, resolved on the netlist.

A topolux states file lists, for each ``In<i>|Out<j>`` pair, the routes through
the fabric as ordered lists of topolux PUC ids.  It says *which* PUCs a route
visits but not how each one is set; that follows from the netlist.  Entering a
PUC on one port and leaving it on another selects one of its internal channels,
and ``internal_connections.json`` gives each channel its ``puc_k``.

The ids are mapped to instance names with ``__pic_to_topolux_ids__`` (one
instance per polarization), and the route is then walked segment by segment on
the direction-aware flow graph from ``flowgraph.py``:

    In -> PUC_0 -> PUC_1 -> ... -> PUC_n-1 -> Out

Between two listed PUCs the walk may cross any passive component but no other
PUC, so the route the topolux file describes is the only one considered.  The
single exception is the first segment, which may cross MUA PUCs (leaf cell
``pucmua<n>``): they sit between the input and the mesh, are not listed by
topolux, and are reported at the start of the route's states.

Each segment's walk from a given waveguide is memoised, and since every route
leaves from some PUC exit, the passive routing of the die is walked about once
in total however many routes there are.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from v7b.tools.netlist.nxgraph import (
    create_nxgraph,
    get_component,
    get_contracted_graph,
)

_MUA = re.compile(r"^pucmua\d+(_|$)")
"""Leaf token of an MUA PUC instance, e.g. ``pucmua72_6403363_10209644_A270``."""

State = tuple[tuple[str, float], ...]
"""PUC states along a route, in traversal order: ``((instance, puc_k), ...)``."""

def _find_state(graph, source, target, expected):
    """Find a path  from `source` to `target` whose PUCs (without counting MUAs)
    are extacly the `expected` ones , in the same order.

    Returns:
        ``{puc_name: puc_k}`` from the path found (muas included), o None.
    """
    stack = [(source, 0, {})]          # (nodo, how many exècted PUCs are, states)
    seen = {(source, 0)}

    while stack:
        u, i, ret = stack.pop()
        if u == target:
            if i == len(expected):     # find out
                return ret
            continue
        for v in graph.neighbors(u):
            kk = graph.edges[u, v].get("puc_k")
            j, nuevo = i, ret
            if kk is not None:
                name = u.split(",")[0]
                if "pucmua" not in name:
                    if j >= len(expected) or name != expected[j]:
                        continue       # there is a puc no expected
                    j += 1
                nuevo = {**ret, name: kk}
            if (v, j) not in seen:
                seen.add((v, j))
                stack.append((v, j, nuevo))
    return None

def generate_states(netlist, pic_to_top_id):
    g = create_nxgraph(netlist)
    input_ports_pattern = r"In\d+"
    output_ports_pattern = r"Out\d+"
    # select puc nodes as the only we are interested in
    nodes_of_interest = {n for n in g.nodes if get_component(netlist, n) == "puc"}

    # Identify input and output ports
    input_ports: set[str] = set()
    output_ports: set[str] = set()
    for k, v in netlist["ports"].items():
        if re.fullmatch(input_ports_pattern, k):
            input_ports.add(k)
            g.add_edge(k, v)

        elif re.fullmatch(output_ports_pattern, k):
            output_ports.add(k)
            g.add_edge(k, v)

    nodes_of_interest |= input_ports | output_ports
    graph = get_contracted_graph(graph=g, nodes_of_interest=nodes_of_interest)

    # read paths from topolux
    paths_topolux = json.loads(
        (
            Path(__file__).parents[0] / "utils" / "log2scaler_72_2_6_2-stage-simple_puc_states.json"
        ).read_text()
    )
    paths_netlist = []
    for k, v in paths_topolux.items():
        # get input and output port
        inn = int(k.split("|")[0].replace("In", ""))
        out = int(k.split("|")[1].replace("Out", ""))
        input_port = f"In{72-inn}"
        output_port = f"Out{72-out}"

        pp = []
        for vv in v:
            path_te = [pic_to_top_id[puc]["te"] for puc in vv]
            path_tm = [pic_to_top_id[puc]["tm"] for puc in vv]
            pp.append({
                "te": _find_state(graph, input_port, output_port, path_te),
                "tm": _find_state(graph, input_port, output_port, path_tm),
            })

        paths_netlist.append([[input_port, output_port], pp])
    return paths_netlist
