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
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import networkx as nx
from v7b.tools.netlist.flowgraph import Wg, build_flow_graph
from v7b.tools.netlist.nxgraph import _InternalConnection

_MUA = re.compile(r"^pucmua\d+(_|$)")
"""Leaf token of an MUA PUC instance, e.g. ``pucmua72_6403363_10209644_A270``."""

State = tuple[tuple[str, float], ...]
"""PUC states along a route, in traversal order: ``((instance, puc_k), ...)``."""


def generate_states(
    netlist: dict[str, Any],
    *,
    print_errors: bool = False,
    reverse_inputs: bool = False,
    reverse_outputs: bool = False,
) -> dict[str, Any]:
    """Add ``__states__`` to the netlist from a topolux states file.

    Args:
        netlist: flat netlist with ``connections``, ``instances``, ``ports`` and
            ``__pic_to_topolux_ids__``.  Mutated: ``__states__`` is added as its
            last key, which ``netlist_test._read_body`` relies on.
        print_errors: print every route that could not be resolved, and why.
        reverse_inputs: topolux numbers inputs opposite to the netlist, so
            topolux ``In<j>`` is walked from netlist port ``In<N - j>`` for N
            netlist inputs, instead of ``In<j + 1>``.  Only the walk changes:
            the entry is still labelled ``In<j + 1>``.
        reverse_outputs: the same for outputs.

    Returns:
        The same netlist.  ``__states__`` is a list of
        ``[[in_label, out_label], [{"te": states, "tm": states}, ...]]`` in the
        states file's key order, labelled as the file numbers its ports plus
        one (``In0|Out0`` -> ``["In1", "Out1"]``) whatever the reversal flags,
        with one dict per topolux route, where ``states`` maps instance
        name to ``puc_k`` along the route, MUAs first.  A polarization that
        cannot be resolved is None, independently of the other one.
    """
    ic_path = Path(Path(__file__).parents[0] / "utils/internal_connections.json")
    internal = {
        comp: [_InternalConnection(**c) for c in chans]
        for comp, chans in json.loads(ic_path.read_text()).items()
    }
    g, report = build_flow_graph(netlist, internal, metrics_fn=lambda *_: {})
    topolux: Mapping[str, Mapping[str, str]] = netlist["__pic_to_topolux_ids__"]
    routes: Mapping[str, Sequence[Sequence[str]]] = json.loads(
        Path(
            Path(__file__).parents[0]
            / "utils/log2scaler_72_2_6_2-stage-simple_puc_states.json"
        ).read_text()
    )

    out_of: dict[str, list[Wg]] = defaultdict(list)
    into: dict[str, list[Wg]] = defaultdict(list)
    for n in g:
        out_of[n[0]].append(n)
        into[n[1]].append(n)

    errors = [
        f"component {comp!r} ({count} instances) is not in internal connections: "
        "every route through it is blocked"
        for comp, count in report["unknown_components"].items()
    ]
    reach_memo: dict[tuple[Wg, bool], list[tuple[Wg, Wg, State]]] = {}
    feeder_memo: dict[str, frozenset[Wg]] = {}

    n_in = sum(1 for p in netlist["ports"] if re.fullmatch(r"In\d+", p))
    n_out = sum(1 for p in netlist["ports"] if re.fullmatch(r"Out\d+", p))
    states = []
    for key, paths in routes.items():
        i, o = (int(s) for s in re.fullmatch(r"In(\d+)\|Out(\d+)", key).groups())
        # labels follow the states file; ports are what the walk uses
        in_label, out_label = f"In{i + 1}", f"Out{o + 1}"
        in_port = f"In{n_in - i if reverse_inputs else i + 1}"
        out_port = f"Out{n_out - o if reverse_outputs else o + 1}"

        sources = _port_waveguides(netlist, internal, in_port, out_of)
        if out_port not in feeder_memo:
            feeder_memo[out_port] = _feeders(
                g, _port_waveguides(netlist, internal, out_port, into)
            )
        feeders = feeder_memo[out_port]
        walked = (
            f" (netlist {in_port}|{out_port})"
            if (in_port, out_port) != (in_label, out_label)
            else ""
        )

        options = []
        for p, ids in enumerate(paths):
            option: dict[str, dict[str, float] | None] = {}
            for pol in ("te", "tm"):
                where = f"{in_label}|{out_label}{walked} path {p} {pol.upper()}"
                missing = [t for t in ids if t not in topolux]
                if not sources or not feeders:
                    side = in_port if not sources else out_port
                    error = f"{side} is not a port of the netlist flow graph"
                elif missing:
                    error = f"topolux ids not in __pic_to_topolux_ids__: {missing}"
                else:
                    resolved, error = _walk(
                        g,
                        sources,
                        feeders,
                        [topolux[t][pol] for t in ids],
                        ids,
                        reach_memo,
                    )
                if error is None:
                    option[pol] = dict(resolved)
                else:
                    option[pol] = None
                    errors.append(f"{where}: {error}")
            options.append(option)
        states.append([[in_label, out_label], options])

    if print_errors:
        for e in errors:
            print(e)
        print(f"generate_states: {len(errors)} errors")

    netlist.pop("__states__", None)
    netlist["__states__"] = states
    return netlist


def _port_waveguides(
    netlist: Mapping[str, Any],
    internal: Mapping[str, Sequence[_InternalConnection]],
    label: str,
    index: Mapping[str, list[Wg]],
) -> list[Wg]:
    """Waveguides at the inner side of the component behind a netlist port.

    The netlist port is the outward face of an edge coupler (``ec,o2``), which
    connects to nothing; light crosses the coupler to its inner port, and the
    route starts or ends on the waveguide there.

    Args:
        netlist: the flat netlist.
        internal: channel definitions per component.
        label: netlist port label, e.g. ``In1``.
        index: inner port -> waveguides, leaving it for an input, arriving at it
            for an output.

    Returns:
        The waveguides, empty if the port is unknown or connected to nothing.
    """
    port = netlist["ports"].get(label)
    if port is None:
        return []
    inst, face = port.rsplit(",", 1)
    comp = netlist["instances"][inst]["component"]
    inner = {
        c.p2 if c.p1 == face else c.p1
        for c in internal.get(comp, [])
        if face in (c.p1, c.p2)
    }
    return [w for q in sorted(inner) for w in index.get(f"{inst},{q}", [])]


def _feeders(g: nx.DiGraph, targets: Sequence[Wg]) -> frozenset[Wg]:
    """Waveguides that reach one of `targets` through passive components only.

    Args:
        g: the flow graph.
        targets: waveguides arriving at an output.

    Returns:
        The waveguides, `targets` included.
    """
    seen = set(targets)
    stack = list(targets)
    while stack:
        v = stack.pop()
        for u, _, d in g.in_edges(v, data=True):
            if d["component"] != "puc" and u not in seen:
                seen.add(u)
                stack.append(u)
    return frozenset(seen)


def _reach(
    g: nx.DiGraph,
    start: Wg,
    through_mua: bool,
    memo: dict[tuple[Wg, bool], list[tuple[Wg, Wg, State]]],
) -> list[tuple[Wg, Wg, State]]:
    """Every PUC traversal reachable from `start` through passive components.

    Args:
        g: the flow graph.
        start: the waveguide to walk from.
        through_mua: also walk through MUA PUCs, recording their states.
        memo: shared cache, keyed by ``(start, through_mua)``.

    Returns:
        ``(u, v, states)`` per reachable traversal edge ``u -> v``, where
        ``states`` are the MUAs crossed before it.
    """
    key = (start, through_mua)
    if key in memo:
        return memo[key]
    found: set[tuple[Wg, Wg, State]] = set()
    seen: set[tuple[Wg, State]] = {(start, ())}
    stack: list[tuple[Wg, State]] = [(start, ())]
    while stack:
        u, crossed = stack.pop()
        for _, v, d in g.out_edges(u, data=True):
            if d["component"] == "puc":
                found.add((u, v, crossed))
                if not (through_mua and _MUA.match(d["instance"].rsplit("~", 1)[-1])):
                    continue
                nxt = (v, (*crossed, (d["instance"], d["puc_k"])))
            else:
                nxt = (v, crossed)
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    memo[key] = sorted(found)
    return memo[key]


def _walk(
    g: nx.DiGraph,
    sources: Sequence[Wg],
    feeders: frozenset[Wg],
    instances: Sequence[str],
    ids: Sequence[str],
    memo: dict[tuple[Wg, bool], list[tuple[Wg, Wg, State]]],
) -> tuple[State | None, str | None]:
    """Resolve one route on one polarization.

    Args:
        g: the flow graph.
        sources: waveguides leaving the input.
        feeders: waveguides that reach the output passively.
        instances: the route's PUC instances, in order.
        ids: their topolux ids, for messages.
        memo: shared :func:`_reach` cache.

    Returns:
        ``(states, None)``, or ``(None, reason)`` when no assignment, or more
        than one, fits the route.
    """
    frontier = {(s, ()) for s in sources}
    for k, inst in enumerate(instances):
        nxt = set()
        for w, states in frontier:
            for u, v, crossed in _reach(g, w, k == 0, memo):
                d = g.edges[u, v]
                if d["instance"] == inst:
                    nxt.add((v, (*states, *crossed, (inst, d["puc_k"]))))
        if not nxt:
            origin = "the input" if k == 0 else f"PUC {ids[k - 1]!r}"
            return None, (
                f"PUC {ids[k]!r} ({inst}) not reachable from {origin} "
                "without crossing another PUC"
            )
        frontier = nxt
    done = {states for w, states in frontier if w in feeders}
    if not done:
        last = f"PUC {ids[-1]!r}" if ids else "the input"
        return None, f"output not reachable from {last} without crossing another PUC"
    if len(done) > 1:
        return None, f"{len(done)} different state assignments fit this route"
    return done.pop(), None
