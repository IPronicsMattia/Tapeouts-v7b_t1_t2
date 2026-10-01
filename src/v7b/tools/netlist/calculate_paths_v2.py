"""Enumerate every route from each input to each output and write them to Excel.

Replacement for calculate_paths.py. Three structural changes:

*   Routes are enumerated on the direction-aware flow graph (``flowgraph.py``),
    so only physical routes are visited.  The old port-node graph let the DFS
    wander through each PUC's internal 4-cycle, which is why finding 16 routes
    took hours: the answer is small, but the *walk space* it was searching was
    enormous.

*   One DFS per input, harvesting all outputs at once, instead of one DFS per
    (input, output) pair.  In a selector fabric a single input fans out to
    2**(stages-1) complete routes total; splitting that by target and
    re-running it per target repeats the same traversal N times.

*   No multiprocessing.  The old code pickled the entire graph and instances
    dict once per task, serially, in the parent.  With the walk space fixed the
    whole sweep is seconds, so the pool was paying setup costs to parallelise
    work that no longer exists.  If it ever does need parallelism, fork with
    the graph as a module global rather than passing it through ``imap``.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path
from time import perf_counter
from typing import Any

import networkx as nx
import pandas as pd
from v7b.tools.netlist.flowgraph import (
    Wg,
    build_flow_graph,
    contract_chains,
    enumerate_paths,
    path_metrics,
    path_pucs,
    path_traversal_count,
    reachable_subgraph,
)
from v7b.tools.netlist.nxgraph import INTERNAL_CONNECTIONS

EXCEL_MAX_ROWS = 1_048_576

# metric key -> output column, keeping the original spreadsheet's headers
COLUMNS: dict[str, str] = {
    "n_rib_taper": "tapers",
    "bends_90": "bends",
    "bends_45": "bends 45",
    "n_crossing": "crossing",
    "n_crossing_anwg_si": "crossing3d",
    "crossings_sin2": "crossings_sin2",
    "crossings_si": "crossings_si",
    "n_puc": "Number pucs",
    "n_transition_si_sin2": "vertical transitions",
    "length_041": "Lenght 0.41um",
    "length_093": "Lenght 0.93um",
    "length_156": "Lenght 1.56um",
    "length_200": "Lenght SiN2 2um",
}
""" Metric key -> spreadsheet column.

Anything a route accumulates lives in the ``m`` dict on each traversal edge and
is summed along the route; this maps those keys to the original spreadsheet's
headers, typos included, so existing downstream sheets keep working.  Add a
metric by emitting the key from ``flowgraph.traversal_metrics`` and naming it
here -- nothing in between needs to change.

Two columns are not in this table.  ``traversals`` is every component on the
route, passives included (see ``flowgraph.path_traversal_count``), and ``path``
is the ordered list of selectors it passes through.

"""


def port_index(g: nx.DiGraph) -> tuple[dict[str, list[Wg]], dict[str, list[Wg]]]:
    """Port -> waveguides leaving / arriving at it.

    Built once in O(V).  Scanning the node set per pair, as a naive
    ``[n for n in g if n[0] == port]`` does, is O(V) each and dominates
    everything else once there are thousands of pairs.
    """
    out_of: dict[str, list[Wg]] = defaultdict(list)
    into: dict[str, list[Wg]] = defaultdict(list)
    for n in g:
        out_of[n[0]].append(n)
        into[n[1]].append(n)
    return dict(out_of), dict(into)


def psr_ports(idx: int, side: str, polarization: str) -> str:
    """PSR port name, from the naming scheme in the original script.

    o3 is the TE arm and o4 the TM arm; they swap between the input and output
    side.  Note the original indexed the *output* port by ``i`` rather than
    ``j``, so every task searched the same pair.
    """
    te_arm = polarization.upper() == "TE"
    if side == "in":
        tail = (
            f"m{4664488 - 127000 * idx}"
            if idx < 36
            else f"{161512 + 127000 * (idx - 36)}"
        )
        return f"v7b~si_psr_tw_{tail}_11901200_A270_M,{'o3' if te_arm else 'o4'}"
    tail = (
        f"m{4606512 - 127000 * idx}" if idx < 36 else f"{219488 + 127000 * (idx - 36)}"
    )
    return f"v7b~si_psr_tw_{tail}_m11901200_A90_M,{'o4' if te_arm else 'o3'}"


def rows_for_input(
    g: nx.DiGraph,
    in_label: str,
    in_port: str,
    out_ports: Mapping[str, str],
    *,
    out_of: Mapping[str, list[Wg]],
    into: Mapping[str, list[Wg]],
    cutoff: int | None = None,
    max_paths_per_input: int | None = None,
    mua_endpoints: bool = True,
) -> list[dict[str, Any]]:
    """All routes from one input port to every output port, in a single DFS."""
    sources = out_of.get(in_port, [])
    label_of_target: dict[Wg, str] = {}
    for label, port in out_ports.items():
        for node in into.get(port, []):
            label_of_target[node] = label
    if not sources or not label_of_target:
        return []

    rows: list[dict[str, Any]] = []
    for path in enumerate_paths(
        g, sources, label_of_target, cutoff=cutoff, max_paths=max_paths_per_input
    ):
        m = path_metrics(g, path)
        pucs = path_pucs(g, path)
        if mua_endpoints and pucs:
            pucs[0] = pucs[0].replace("puc", "")
        rows.append(
            {
                "Input Port": in_label,
                "Output Port": label_of_target[path[-1]],
                **{col: m.get(key, 0) for key, col in COLUMNS.items()},
                "traversals": path_traversal_count(g, path),
                "path": pucs,
            }
        )
    return rows


def sweep(
    g: nx.DiGraph,
    inputs: Mapping[str, str],
    outputs: Mapping[str, str],
    *,
    expected_routes: int | None = None,
    contract: bool = True,
    prune: bool = True,
    progress: bool = False,
    **kwargs: Any,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Enumerate every input->output pair. Returns (routes, summary).

    The stages run in this order, and the order is the reason this takes a
    minute rather than hours:

    1.  **Index** the ports, so finding the waveguides at a named port is a dict
        lookup instead of a scan over a million nodes -- done once, not per pair.
    2.  **Prune** to the waveguides that lie on some input->output route.  A
        linear pass that typically halves the graph and guarantees the search
        never wanders somewhere it cannot finish.
    3.  **Contract** the runs of straights and bends into single edges, which
        collapses the graph to just the points where a route makes a choice.
        After this a route is a handful of steps instead of thousands.
    4.  **Search** once per input, collecting all outputs in that one traversal.

    Each stage is exact -- the routes and their metrics are identical with any
    combination of them switched off, which is what the test suite checks -- so
    ``prune=False, contract=False`` is always available as a slower reference if
    a result ever looks wrong.

    The summary is the part worth reading: a route count per pair.  In a
    selector fabric that count is fixed by the topology, so any pair that
    deviates is a netlist problem -- zero means the route is broken, more than
    expected means unintended connectivity -- and that is far more informative
    than the route rows themselves.

    """

    out_of, into = port_index(g)
    src_nodes = [n for p in inputs.values() for n in out_of.get(p, [])]
    tgt_nodes = [n for p in outputs.values() for n in into.get(p, [])]
    print(
        f"endpoints: {len(src_nodes)} source waveguides, {len(tgt_nodes)} target "
        f"waveguides for {len(inputs)} inputs / {len(outputs)} outputs",
        flush=True,
    )
    if not src_nodes or not tgt_nodes:
        print(
            "  nothing to enumerate -- check the port names against the netlist",
            flush=True,
        )
        return pd.DataFrame(), pd.DataFrame()

    if prune:
        before = g.number_of_nodes()
        t0 = perf_counter()
        g = reachable_subgraph(g, src_nodes, tgt_nodes)
        print(
            f"pruned {before:,} -> {g.number_of_nodes():,} waveguides on a "
            f"source->target route in {perf_counter() - t0:.1f}s",
            flush=True,
        )
        out_of, into = port_index(g)
        dead = [lbl for lbl, p in inputs.items() if not out_of.get(p)]
        if dead:
            print(
                f"  {len(dead)} inputs reach no output at all, e.g. {dead[:5]}",
                flush=True,
            )

    if contract:
        endpoints = [
            n
            for p in (*inputs.values(), *outputs.values())
            for n in (*out_of.get(p, []), *into.get(p, []))
        ]
        before = g.number_of_nodes()
        t0 = perf_counter()
        contract_chains(g, endpoints)
        print(
            f"contracted {before:,} -> {g.number_of_nodes():,} waveguides "
            f"({g.number_of_edges():,} traversal groups) in {perf_counter() - t0:.1f}s",
            flush=True,
        )
        out_of, into = port_index(g)

    rows: list[dict[str, Any]] = []
    t0 = perf_counter()
    for k, (in_label, in_port) in enumerate(inputs.items(), 1):
        n_before = len(rows)
        rows.extend(
            rows_for_input(
                g, in_label, in_port, outputs, out_of=out_of, into=into, **kwargs
            )
        )
        if progress:
            print(
                f"  [{k}/{len(inputs)}] {in_label}: {len(rows) - n_before} routes "
                f"({perf_counter() - t0:.1f}s elapsed)",
                flush=True,
            )

    routes = pd.DataFrame(rows)
    if routes.empty:
        return routes, pd.DataFrame()

    summary = (
        routes.groupby(["Input Port", "Output Port"], sort=False)
        .agg(
            routes=("traversals", "size"),
            min_traversals=("traversals", "min"),
            max_traversals=("traversals", "max"),
        )
        .reset_index()
    )
    missing = [
        (i, o)
        for i in inputs
        for o in outputs
        if not ((summary["Input Port"] == i) & (summary["Output Port"] == o)).any()
    ]
    for i, o in missing:
        summary.loc[len(summary)] = [i, o, 0, pd.NA, pd.NA]
    if expected_routes is not None:
        summary["as_expected"] = summary["routes"] == expected_routes
    return routes, summary


def write_excel(routes: pd.DataFrame, summary: pd.DataFrame, path: str | Path) -> None:
    if len(routes) > EXCEL_MAX_ROWS:
        raise ValueError(
            f"{len(routes):,} routes exceeds Excel's {EXCEL_MAX_ROWS:,}-row limit; "
            "write Parquet instead"
        )
    out = routes.copy()
    out["path"] = out["path"].apply(lambda p: ", ".join(p))
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        out.to_excel(writer, sheet_name="routes", index=False)
        if not summary.empty:
            summary.to_excel(writer, sheet_name="route_counts", index=False)


def main(
    netlist_path: Path,
    out_path: Path,
    n_io: int,
    expected_routes: int | None,
    contract: bool = True,
) -> None:
    netlist = json.loads(netlist_path.read_text())
    g, report = build_flow_graph(netlist, INTERNAL_CONNECTIONS)
    print(
        f"flow graph: {report['nodes']:,} waveguides, {report['edges']:,} traversals "
        f"(excess {report['edges'] - report['nodes']:,})",
        flush=True,
    )
    if report["unknown_components"]:
        print(
            f"  WARNING blockers (no internal channels): {report['unknown_components']}"
        )

    inputs, outputs = {}, {}
    for pol in ("TE", "TM"):
        for k in range(n_io):
            inputs[f"IN{k + 1}_{pol}"] = psr_ports(k, "in", pol)
            outputs[f"OUT{k + 1}_{pol}"] = psr_ports(k, "out", pol)

    t0 = perf_counter()
    t0 = perf_counter()
    acyclic = nx.is_directed_acyclic_graph(g)
    print(f"acyclic: {acyclic}  ({perf_counter() - t0:.1f}s)", flush=True)
    if not acyclic:
        print(
            "  WARNING routes may recirculate; contraction is only exact on a DAG,"
            " so re-run with --no-contract to confirm the route counts",
            flush=True,
        )
    routes, summary = sweep(
        g,
        inputs,
        outputs,
        expected_routes=expected_routes,
        contract=contract,
        progress=True,
    )
    print(f"{len(routes):,} routes in {perf_counter() - t0:.1f}s")
    if "as_expected" in summary and not summary["as_expected"].all():
        bad = summary[~summary["as_expected"]]
        print(f"  WARNING {len(bad)} pairs deviate from {expected_routes} routes:")
        print(bad.head(20).to_string(index=False))
    write_excel(routes, summary, out_path)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    # c:\Users\AlvaroLebrun\Desktop\Repos\Tapeouts\.venv\Scripts\python.exe
    # c:/Users/AlvaroLebrun/Desktop/Repos/Tapeouts/src/V7b/tools/netlist/calculate_paths_v2.py
    # mesh_die_netlist.json -n 72
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("netlist", type=Path)
    ap.add_argument("-o", "--out", type=Path, default=Path("V7b_paths.xlsx"))
    ap.add_argument("-n", "--n-io", type=int, default=72)
    ap.add_argument("--expect", type=int, default=None, help="expected routes per pair")
    ap.add_argument("--no-contract", action="store_true")
    a = ap.parse_args()
    main(a.netlist, a.out, a.n_io, a.expect, contract=not a.no_contract)
