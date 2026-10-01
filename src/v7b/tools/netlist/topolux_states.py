"""Topolux ``__states__`` for a polarisation-diverse selector mesh.

The die carries two structurally identical copies of the mesh, one per
polarisation, placed side by side in x.  A route enters on an edge coupler,
splits at a PSR into a TE arm and a TM arm, crosses the corresponding copy, and
recombines at the PSR on the far side.  Topolux wants, for every ``(In, Out)``
pair, every route that pair admits, and for each route the state every selector
on it must be set to -- once for the TE copy and once for the TM copy.

The two copies differ by exactly one token in the hierarchical instance name --
the mesh instance, whose placement x differs -- and by nothing else.  There is
no mirror and no rotation in either placement, so the port roles inside each
selector are untouched and the TM route is the TE route with that one token
substituted, state for state.  That is what makes this affordable: the sweep
enumerates the TE plane only and derives TM, halving both the search and the
number of routes whose metrics have to be read off.

Because so much rests on it, the substitution is not assumed.  Two checks
establish it, both linear and both run before any enumeration:

*   ``mesh_tokens`` derives the two tokens from ``puc_map.json`` rather than
    taking them as constants, and refuses unless substituting one for the other
    is a bijection between the two planes that preserves the topolux id.
*   ``check_plane_isomorphism`` walks the flow graph once and requires every
    selector traversal in the TE plane to have a TM twin with the same entry
    port, exit port and state.  This proves the substitution for all routes at
    once, in O(edges), instead of trusting it route by route.

This module covers endpoint resolution and those checks.  The sweep itself, and
the writer, come next.
"""

from __future__ import annotations

import json
import re
from collections import deque
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any

import networkx as nx
from v7b.tools.netlist.calculate_paths_v2 import port_index, psr_ports
from v7b.tools.netlist.flowgraph import (
    Wg,
    build_flow_graph,
    contract_chains,
    enumerate_paths,
    path_puc_states,
    reachable_subgraph,
)
from v7b.tools.netlist.nxgraph import INTERNAL_CONNECTIONS

POLARISATIONS = ("TE", "TM")

PortFn = Callable[[int, str, str], str]
"""``(index, side, polarisation) -> port name``; ``psr_ports`` is the default.

Injectable so the tests can drive the resolution with a fixture's own names.
The production implementation lives in ``calculate_paths_v2`` and stays the
single source of truth for the PSR coordinates and the ``o3``/``o4`` arm
assignment, which swaps between the input and output sides because the two PSR
rows are rotated A270 and A90 respectively.
"""


# --------------------------------------------------------------------------- #
# the two planes
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Planes:
    """Where the TE and TM copies of the mesh differ in an instance name.

    Attributes:
        level: index of the differing token in a ``~``-split instance name.
        token: the token at that level, per polarisation.
    """

    level: int
    token: dict[str, str]

    def swap(self, name: str, to: str) -> str:
        """The same selector in the `to` plane.

        Args:
            name: full hierarchical instance name, in either plane.
            to: target polarisation, ``"TE"`` or ``"TM"``.

        Returns:
            The instance name with the mesh token replaced.
        """
        parts = name.split("~")
        parts[self.level] = self.token[to]
        return "~".join(parts)

    def plane_of(self, name: str) -> str | None:
        """Which plane `name` belongs to, or None if it is in neither."""
        parts = name.split("~")
        if len(parts) <= self.level:
            return None
        return next(
            (p for p, t in self.token.items() if parts[self.level] == t),
            None,
        )


def _constant_tokens(names: Iterable[str]) -> dict[int, str]:
    """Token positions at which every name agrees, and the token found there."""
    shared: dict[int, set[str]] = {}
    for name in names:
        for i, tok in enumerate(name.split("~")):
            shared.setdefault(i, set()).add(tok)
    return {i: next(iter(v)) for i, v in shared.items() if len(v) == 1}


def mesh_tokens(puc_map: Mapping[str, Mapping[str, str]]) -> Planes:
    """Derive the TE/TM mesh tokens from the topolux map, and validate them.

    Finds the one hierarchy level at which each plane is internally constant and
    the two planes disagree.  Deriving this beats hardcoding the tokens: the
    placement hashes change whenever the mesh is re-elaborated, and a stale
    constant would fail as "no such selector" somewhere deep in the sweep rather
    than here.

    Args:
        puc_map: the ``puc_map.json`` contents, ``{"TE": {...}, "TM": {...}}``.
            Values are topolux ids and are compared but not otherwise used.

    Returns:
        The differing level and its token in each plane.

    Raises:
        ValueError: with every fault listed, if the two planes are not related
            by a single-token substitution.  Everything downstream assumes they
            are, so this is the place to find out.
    """
    faults: list[str] = []
    missing = [p for p in POLARISATIONS if not puc_map.get(p)]
    if missing:
        raise ValueError(f"puc_map has no {', '.join(missing)} entries")

    te, tm = puc_map["TE"], puc_map["TM"]
    if len(te) != len(tm):
        faults.append(f"TE has {len(te)} selectors, TM has {len(tm)}")

    const = {p: _constant_tokens(puc_map[p]) for p in POLARISATIONS}
    levels = [
        i
        for i in const["TE"]
        if i in const["TM"] and const["TE"][i] != const["TM"][i]
    ]
    if len(levels) != 1:
        raise ValueError(
            f"expected exactly one hierarchy level to distinguish the planes, "
            f"found {levels or 'none'}"
        )

    level = levels[0]
    planes = Planes(level, {p: const[p][level] for p in POLARISATIONS})

    for source, target in (("TE", "TM"), ("TM", "TE")):
        for name, topolux_id in puc_map[source].items():
            twin = planes.swap(name, target)
            if twin not in puc_map[target]:
                faults.append(f"{source} {name} has no {target} counterpart")
            elif puc_map[target][twin] != topolux_id:
                faults.append(
                    f"{name} is topolux {topolux_id} in {source} but "
                    f"{puc_map[target][twin]} in {target}"
                )
            if len(faults) > 20:
                faults.append("...")
                break

    if faults:
        raise ValueError(
            "puc_map planes are not a substitution:\n  " + "\n  ".join(faults)
        )
    return planes


def check_plane_isomorphism(
    g: nx.DiGraph,
    planes: Planes,
    puc_map: Mapping[str, Mapping[str, str]],
    *,
    allow_unmapped: bool = True,
) -> dict[str, Any]:
    """Require every TE selector traversal to have an identical TM twin.

    This is the proof behind deriving the TM route from the TE one.  One pass
    over the edges, so it costs nothing next to the sweep, and it covers every
    route the sweep will ever produce rather than the handful a spot check
    would.

    Args:
        g: the **raw** flow graph.  Run this before ``contract_chains``: a
            contracted edge has no ``inport``/``outport`` and stands for many
            traversals, so the twin comparison would have nothing to compare.
        planes: from ``mesh_tokens``.
        puc_map: used to decide which selectors are mesh selectors.
        allow_unmapped: report selectors outside both meshes rather than
            faulting on them.  The MUAs are outside both by construction -- they
            sit at top level, one per port, and every route crosses one at each
            end -- so this defaults to True and the caller decides what to do
            with the list.

    Returns:
        Counts per plane of the selector traversals checked, plus ``unmapped``:
        the instance names that belong to neither mesh.

    Raises:
        ValueError: with every fault listed, if a traversal has no twin, the
            twin disagrees on the state, or -- when `allow_unmapped` is False --
            a selector is not in the map.
    """
    faults: list[str] = []
    seen: dict[tuple[str, str, str], float] = {}
    counts = dict.fromkeys(POLARISATIONS, 0)
    foreign: set[str] = set()

    for _u, _v, d in g.edges(data=True):
        for instance, state in d.get("puc_states", ()):
            plane = planes.plane_of(instance)
            if plane is None or instance not in puc_map[plane]:
                foreign.add(instance)
                continue
            seen[instance, d["inport"], d["outport"]] = state
            counts[plane] += 1

    for (instance, inport, outport), state in seen.items():
        plane = planes.plane_of(instance)
        other = "TM" if plane == "TE" else "TE"
        twin = (planes.swap(instance, other), inport, outport)
        if twin not in seen:
            faults.append(f"{instance} {inport}->{outport} has no {other} twin")
        elif seen[twin] != state:
            faults.append(
                f"{instance} {inport}->{outport} is {state} but its {other} "
                f"twin is {seen[twin]}"
            )
        if len(faults) > 20:
            faults.append("...")
            break

    if foreign and not allow_unmapped:
        faults.append(
            f"{len(foreign)} traversed selectors are not in puc_map, e.g. "
            f"{sorted(foreign)[:3]}"
        )
    if counts["TE"] != counts["TM"]:
        faults.append(
            f"{counts['TE']} TE traversals against {counts['TM']} TM traversals"
        )
    if faults:
        raise ValueError(
            "the two mesh planes are not isomorphic, so a TM route cannot be "
            "derived from its TE twin:\n  " + "\n  ".join(faults)
        )
    return {**counts, "unmapped": sorted(foreign)}


# --------------------------------------------------------------------------- #
# endpoints
# --------------------------------------------------------------------------- #


@dataclass
class Endpoints:
    """PSR arm waveguides for every labelled input and output.

    Attributes:
        sources: ``(label, polarisation) -> waveguides leaving that arm``.
        targets: ``(label, polarisation) -> waveguides arriving at that arm``.
        port: ``(label, polarisation) -> the PSR port name``, for messages.
    """

    sources: dict[tuple[str, str], list[Wg]] = field(default_factory=dict)
    targets: dict[tuple[str, str], list[Wg]] = field(default_factory=dict)
    port: dict[tuple[str, str], str] = field(default_factory=dict)

    def labels(self, side: str) -> list[str]:
        """Input or output labels, in index order, without duplicates."""
        keys = self.sources if side == "in" else self.targets
        return list(dict.fromkeys(label for label, _ in keys))


def first_selector(
    g: nx.DiGraph,
    start: Wg,
    *,
    forward: bool,
    planes: Planes | None = None,
    max_steps: int = 100_000,
) -> str | None:
    """The first *mesh* selector reachable from `start`, in either direction.

    Used to identify which plane a PSR arm feeds, which is how the ``o3``/``o4``
    assignment gets checked against the layout instead of being trusted.  A
    breadth-first walk, so it finds the nearest one rather than following one
    branch to the far side of the die.

    Every route crosses a MUA selector between the PSR and the mesh.  A MUA sits
    at top level, outside either mesh instance, so it cannot be attributed to a
    plane and answers nothing about the arm.  With `planes` given, the walk
    passes straight through anything it cannot attribute and keeps going until
    it reaches a selector inside one of the two meshes.  Without it, the first
    selector of any kind is returned.

    Only meaningful on the raw graph.  A contracted edge merges a whole run of
    traversals into one, so "the first selector on this edge" is the only one
    this can see, and a mesh selector merged behind a MUA would be stepped over
    rather than found.

    Args:
        g: the raw flow graph.
        start: waveguide to walk from.
        forward: walk with the light (successors) or against it (predecessors).
        planes: if given, only a selector belonging to a plane will do.
        max_steps: give up after this many waveguides.

    Returns:
        The selector's instance name, or None if none is reachable.
    """
    step = g._succ if forward else g._pred
    edge = (lambda a, b: (a, b)) if forward else (lambda a, b: (b, a))
    queue: deque[Wg] = deque([start])
    seen = {start}
    steps = 0
    while queue and steps < max_steps:
        node = queue.popleft()
        steps += 1
        for nxt in step[node]:
            states = g.edges[edge(node, nxt)].get("puc_states", ())
            if states and (planes is None or planes.plane_of(states[0][0])):
                return states[0][0]
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return None


def resolve_endpoints(
    g: nx.DiGraph,
    planes: Planes,
    *,
    n_io: int = 72,
    port_fn: PortFn = psr_ports,
    verify: bool = True,
) -> Endpoints:
    """Locate the TE and TM arm of every input and output PSR.

    ``In1`` names a whole PSR, which splits into a TE arm and a TM arm; a route
    for the pair ``(In1, Out1)`` is really a TE route between the TE arms and
    the matching TM route between the TM arms.  This resolves all four arm sets
    per index and, with `verify`, confirms each arm actually feeds the plane its
    name claims by walking to the nearest selector and asking which mesh that
    selector sits in.

    That check is worth its cost.  The arm assignment is not symmetric -- the
    input row is ``o3``=TE, the output row ``o4``=TE, because the two rows are
    rotated oppositely -- and getting it wrong does not fail loudly.  It quietly
    enumerates a polarisation mismatch, which has no routes at all, so the sweep
    would report zero routes for every pair and look like a broken netlist.

    Args:
        g: the raw flow graph.
        planes: from ``mesh_tokens``.
        n_io: number of input/output PSRs.
        port_fn: PSR port namer.
        verify: walk each arm to its first selector and check the plane.

    Returns:
        The resolved arms.

    Raises:
        ValueError: with every fault listed, if an arm has no waveguides or
            feeds the wrong plane.
    """
    faults: list[str] = []
    out_of, into = port_index(g)
    ends = Endpoints()

    for idx in range(n_io):
        for pol in POLARISATIONS:
            for side, label in (("in", f"In{idx + 1}"), ("out", f"Out{idx + 1}")):
                port = port_fn(idx, side, pol)
                nodes = (out_of if side == "in" else into).get(port, [])
                key = (label, pol)
                ends.port[key] = port
                if side == "in":
                    ends.sources[key] = nodes
                else:
                    ends.targets[key] = nodes
                if not nodes:
                    faults.append(f"{label} {pol}: no waveguide at {port}")
                    continue
                if not verify:
                    continue
                selector = first_selector(
                    g, nodes[0], forward=side == "in", planes=planes
                )
                if selector is None:
                    faults.append(
                        f"{label} {pol}: {port} reaches no mesh selector"
                    )
                elif planes.plane_of(selector) != pol:
                    faults.append(
                        f"{label} {pol}: {port} feeds the "
                        f"{planes.plane_of(selector)} mesh ({selector}) -- the "
                        f"o3/o4 arm assignment for the {side} row is wrong"
                    )

    if faults:
        raise ValueError(
            f"endpoint resolution failed for {len(faults)} arms:\n  "
            + "\n  ".join(faults[:20])
            + ("\n  ..." if len(faults) > 20 else "")
        )
    return ends


def endpoint_report(ends: Endpoints) -> dict[str, Any]:
    """Counts worth printing before a sweep that takes minutes."""
    return {
        "inputs": len(ends.labels("in")),
        "outputs": len(ends.labels("out")),
        "source_waveguides": sum(len(v) for v in ends.sources.values()),
        "target_waveguides": sum(len(v) for v in ends.targets.values()),
    }


# --------------------------------------------------------------------------- #
# MUAs
# --------------------------------------------------------------------------- #

_MUA_NUMBER = re.compile(r"pucmua(\d+)")
_PLACEMENT = re.compile(r"_(m?\d+)_(m?\d+)(?:_[AMR]\d+)*$")


def _coord(token: str) -> int:
    """A placement coordinate from an instance name; ``m`` prefixes negatives."""
    return -int(token[1:]) if token.startswith("m") else int(token)


def placement_x(instance: str) -> int | None:
    """The x in an instance name's placement suffix, or None if it has none."""
    match = _PLACEMENT.search(instance.split("~")[-1])
    return _coord(match[1]) if match else None


def traversed_selectors(g: nx.DiGraph) -> set[str]:
    """Every selector some traversal edge of `g` passes through.

    Works on a contracted graph as well as a raw one, since ``puc_states``
    survives contraction.  On a pruned graph this is exactly the set of
    selectors a route can reach, which is the set that has to be mappable --
    the raw graph also holds test structures and anything else the die carries
    that no route touches.
    """
    return {
        instance
        for _u, _v, d in g.edges(data=True)
        for instance, _state in d.get("puc_states", ())
    }


def resolve_muas(
    g: nx.DiGraph, planes: Planes, ends: Endpoints, *, strict: bool = True
) -> dict[str, str]:
    """Pair each arm's MUA selector with its counterpart in the other plane.

    A MUA sits between a PSR arm and the mesh, one per arm per polarisation,
    differing between the planes only by an x shift.  It is a selector -- it has
    a state, and topolux wants it -- but it is placed at top level, so it
    carries no mesh token and the TE -> TM substitution cannot reach it.

    Rather than assume the naming, this walks out from each arm and takes the
    first selector it meets: if that selector is in a mesh, the arm has no MUA;
    otherwise it is that arm's MUA, by construction.  The TE and TM arms of one
    label therefore name the two halves of a pair directly, with nothing
    inferred from the numbering.

    The numbering is then used the other way round, as a check: ``In1``'s MUA
    should be ``pucmua1``, the two planes' MUAs should share that number, and
    the TE one should sit at the lower x, since the TE mesh does.  Each is a
    statement about the layout that costs nothing to verify and would otherwise
    be an assumption nobody revisits.

    Args:
        g: the **raw** flow graph; see ``first_selector``.
        planes: from ``mesh_tokens``.
        ends: resolved arms.
        strict: raise on the faults below rather than returning what was found.

    Returns:
        ``{TE instance: TM instance}``, ready to merge into ``tm_name_map``'s
        result.  Empty if no arm has a MUA.

    Raises:
        ValueError: with every fault listed, if an arm has a MUA in one plane
            but not the other, the two disagree on the number, an input's number
            does not match its label, or the TE MUA is not at the lower x.
    """
    faults: list[str] = []
    found: dict[tuple[str, str], str] = {}

    for (label, pol), nodes in (
        *((k, v) for k, v in ends.sources.items()),
        *((k, v) for k, v in ends.targets.items()),
    ):
        if not nodes:
            continue
        inward = label.startswith("In")
        selector = first_selector(g, nodes[0], forward=inward)
        if selector is not None and not planes.plane_of(selector):
            found[label, pol] = selector

    pairs: dict[str, str] = {}
    for label in {lbl for lbl, _ in found} | {
        lbl for lbl, _ in (*ends.sources, *ends.targets)
    }:
        te, tm = found.get((label, "TE")), found.get((label, "TM"))
        if te is None and tm is None:
            continue
        if te is None or tm is None:
            faults.append(
                f"{label}: a MUA on the "
                f"{'TM' if te is None else 'TE'} arm only"
            )
            continue
        if te == tm:
            faults.append(f"{label}: both arms reach the same MUA {te}")
            continue

        numbers = [_MUA_NUMBER.search(name) for name in (te, tm)]
        if not all(numbers):
            faults.append(f"{label}: {te} / {tm} are not named pucmua<n>")
        elif numbers[0][1] != numbers[1][1]:
            faults.append(
                f"{label}: TE MUA is number {numbers[0][1]} but TM is "
                f"{numbers[1][1]}"
            )
        elif label.startswith("In") and numbers[0][1] != label[2:]:
            faults.append(
                f"{label}: expected pucmua{label[2:]}, found "
                f"pucmua{numbers[0][1]}"
            )

        xs = [placement_x(name) for name in (te, tm)]
        if all(x is not None for x in xs) and xs[0] >= xs[1]:
            faults.append(
                f"{label}: TE MUA is at x={xs[0]}, not left of the TM one at "
                f"x={xs[1]} -- the planes may be the other way round"
            )
        pairs[te] = tm

    if faults and strict:
        raise ValueError(
            f"MUA pairing failed for {len(faults)} arms:\n  "
            + "\n  ".join(faults[:20])
            + ("\n  ..." if len(faults) > 20 else "")
        )
    return pairs


# --------------------------------------------------------------------------- #
# pair selection
# --------------------------------------------------------------------------- #

EXPECTED_ROUTES = (24, 48, 96)
"""Route counts a pair may legitimately have.  Anything else is a fault."""


def select_pairs(
    n_io: int = 72, mode: str = "diagonal", limit: int | None = None
) -> list[tuple[str, str]]:
    """The ``(In, Out)`` pairs to sweep.

    The full sweep is the cartesian product, ``n_io**2`` pairs.  The other modes
    exist to measure before committing to it: a bounded run gives bytes per pair
    and seconds per pair, which extrapolate to the whole thing.

    Args:
        n_io: number of input and output PSRs.
        mode: ``"all"`` for the cartesian product in ``In`` then ``Out`` order;
            ``"diagonal"`` for ``(In_k, Out_k)``; ``"row"`` for ``In1`` against
            every output; ``"stride"`` for an evenly spaced sample of the full
            product.
        limit: keep only this many pairs.

    Returns:
        The pairs, in the order they should be written.

    Raises:
        ValueError: on an unknown mode.
    """
    everything = [
        (f"In{i + 1}", f"Out{j + 1}") for i in range(n_io) for j in range(n_io)
    ]
    if mode == "all":
        pairs = everything
    elif mode == "diagonal":
        pairs = [(f"In{k + 1}", f"Out{k + 1}") for k in range(n_io)]
    elif mode == "row":
        pairs = [("In1", f"Out{j + 1}") for j in range(n_io)]
    elif mode == "stride":
        step = max(1, len(everything) // (limit or len(everything)))
        pairs = everything[::step]
    else:
        raise ValueError(f"unknown pair mode {mode!r}")
    return pairs[:limit] if limit else pairs


# --------------------------------------------------------------------------- #
# the sweep
# --------------------------------------------------------------------------- #


@dataclass
class SweepStats:
    """What a sweep produced, for extrapolating and for the summary field.

    The fixed and variable parts of the output are tracked separately, which
    matters more than it sounds.  The netlist body -- instances, placements,
    connections -- is written once and is the same size whether one pair is
    swept or all of them, while only ``__states__`` grows.  On this die the body
    is hundreds of megabytes and a ten-pair states array is about one, so
    projecting the *total* overstates the full sweep by roughly a hundredfold.
    """

    pairs: int = 0
    paths: int = 0
    selectors: int = 0
    min_selectors: int = 0
    max_selectors: int = 0
    netlist_bytes: int = 0
    states_bytes: int = 0
    netlist_seconds: float = 0.0
    states_seconds: float = 0.0
    seconds: float = 0.0
    faults: list[str] = field(default_factory=list)

    @property
    def bytes_written(self) -> int:
        """Total size of the file."""
        return self.netlist_bytes + self.states_bytes

    @property
    def selectors_per_route(self) -> float:
        """Mean selectors traversed per route, the figure that sets the size."""
        return self.selectors / self.paths if self.paths else 0.0

    @property
    def paths_per_pair(self) -> float:
        """Mean routes per pair in this run."""
        return self.paths / self.pairs if self.pairs else 0.0

    @property
    def bytes_per_path(self) -> float:
        """Bytes of ``__states__`` per route, the only figure that scales."""
        return self.states_bytes / self.paths if self.paths else 0.0

    def extrapolate(
        self, to_pairs: int, paths_per_pair: float | None = None
    ) -> dict[str, float]:
        """Project onto a larger sweep: fixed part once, variable part scaled.

        Args:
            to_pairs: how many pairs the full sweep covers.
            paths_per_pair: routes per pair to assume.  Defaults to this run's
                mean, which is only representative if the pairs swept were.
                The diagonal pairs all carry the minimum route count, so pass
                the figure from a ``stride`` sample, or 96 for an upper bound.

        Returns:
            Projected paths, gigabytes and minutes.
        """
        if not self.paths:
            return {}
        paths = to_pairs * (
            paths_per_pair if paths_per_pair is not None else self.paths_per_pair
        )
        scale = paths / self.paths
        return {
            "pairs": to_pairs,
            "paths": paths,
            "gigabytes": (self.netlist_bytes + self.states_bytes * scale) / 1e9,
            "minutes": (self.netlist_seconds + self.states_seconds * scale) / 60,
        }


def tm_name_map(
    planes: Planes, puc_map: Mapping[str, Mapping[str, str]]
) -> dict[str, str]:
    """TE instance name -> its TM twin, built once.

    Every route rewrites its whole state dict into the TM plane, so doing the
    substitution per selector per route would allocate a new 140-character
    string tens of millions of times.  Precomputing it means every TM key is one
    of 2664 shared strings instead.
    """
    return {name: planes.swap(name, "TM") for name in puc_map["TE"]}


def _both_planes(
    te: dict[str, float], tm_of: Mapping[str, str], on_unmapped: str
) -> tuple[dict[str, float], dict[str, float]]:
    """Split one route's states into its TE and TM halves.

    The mesh selectors substitute cleanly.  Anything else -- a MUA -- has no
    entry in `tm_of`, and silently reusing the TE name in the TM half would
    write a state against a selector that is not on the TM route, so the caller
    has to say what it wants instead.

    Args:
        te: states as traversed, keyed by TE-plane instance names.
        tm_of: TE -> TM instance names for the mesh selectors.
        on_unmapped: ``"raise"``, ``"skip"`` or ``"keep"``.

    Returns:
        The TE and TM halves of the path record.

    Raises:
        ValueError: on an unmapped selector, when `on_unmapped` is ``"raise"``.
    """
    if on_unmapped == "raise":
        missing = [k for k in te if k not in tm_of]
        if missing:
            raise ValueError(
                f"{len(missing)} traversed selectors have no TM counterpart, "
                f"e.g. {missing[:3]} -- these are outside both meshes, so the "
                "TE->TM substitution does not reach them"
            )
        return te, {tm_of[k]: v for k, v in te.items()}
    if on_unmapped == "skip":
        kept = {k: v for k, v in te.items() if k in tm_of}
        return kept, {tm_of[k]: v for k, v in kept.items()}
    return te, {tm_of.get(k, k): v for k, v in te.items()}


def sweep_records(
    g: nx.DiGraph,
    ends: Endpoints,
    tm_of: Mapping[str, str],
    pairs: Iterable[tuple[str, str]],
    *,
    strict: bool = True,
    cutoff: int | None = None,
    expected: tuple[int, ...] = EXPECTED_ROUTES,
    on_unmapped: str = "raise",
    stats: SweepStats | None = None,
    progress: bool = False,
) -> Iterator[list[Any]]:
    """Yield one ``[[In, Out], [path, ...]]`` record per pair, in `pairs` order.

    Routes are enumerated in the TE plane only and the TM half of each path is
    derived by substitution, which halves the search.  Pairs are grouped by
    input so that one traversal harvests every output that input is asked
    about: the routes to different outputs share nearly all of their prefix, and
    a per-pair search re-walks it every time.

    Nothing accumulates across inputs -- one input's records are yielded and
    dropped before the next begins -- so peak memory is one input's worth of
    routes regardless of how many pairs are swept.

    Args:
        g: pruned and contracted flow graph.
        ends: resolved arms, from ``resolve_endpoints``.
        tm_of: TE -> TM instance names, from ``tm_name_map``.
        pairs: ``(In, Out)`` labels to sweep.
        strict: raise as soon as a pair's route count is not in
            ``EXPECTED_ROUTES``.  False collects the fault and carries on, which
            is what a measurement run wants.
        cutoff: maximum traversals per route, passed to the search.
        expected: the route counts a pair may have.  Parameterised so a fixture
            can state its own; the die's are ``EXPECTED_ROUTES``.
        on_unmapped: what to do with a traversed selector `tm_of` has no twin
            for -- in practice the MUAs, which sit outside both meshes.
            ``"raise"`` refuses, ``"skip"`` leaves it out of both halves of the
            path, ``"keep"`` records it under the same name in both.  Only
            ``"raise"`` and an entry in `tm_of` give a correct file; the other
            two exist so a measurement run can proceed before the MUA pairing
            is settled, and ``"skip"`` under-counts by one selector per MUA.
        stats: filled in as the sweep runs, if given.
        progress: print a line per input.

    Yields:
        One record per pair.

    Raises:
        ValueError: when `strict` and a pair has an unexpected route count, or
            when a selector has no TM twin and `on_unmapped` is ``"raise"``.
    """
    if on_unmapped not in ("raise", "skip", "keep"):
        raise ValueError(f"unknown on_unmapped policy {on_unmapped!r}")
    stats = stats if stats is not None else SweepStats()
    by_input: dict[str, list[str]] = {}
    for in_label, out_label in pairs:
        by_input.setdefault(in_label, []).append(out_label)

    for in_label, out_labels in by_input.items():
        t0 = perf_counter()
        label_of: dict[Wg, str] = {}
        for out_label in out_labels:
            for node in ends.targets[out_label, "TE"]:
                label_of[node] = out_label

        buckets: dict[str, list[dict[str, dict[str, float]]]] = {
            o: [] for o in out_labels
        }
        for path in enumerate_paths(
            g, ends.sources[in_label, "TE"], label_of, cutoff=cutoff
        ):
            te = path_puc_states(g, path)
            te, tm = _both_planes(te, tm_of, on_unmapped)
            buckets[label_of[path[-1]]].append({"te": te, "tm": tm})
            stats.selectors += len(te)
            stats.min_selectors = min(stats.min_selectors or len(te), len(te))
            stats.max_selectors = max(stats.max_selectors, len(te))

        for out_label in out_labels:
            routes = buckets[out_label]
            if len(routes) not in expected:
                fault = (
                    f"{in_label}->{out_label}: {len(routes)} routes, expected "
                    f"one of {expected}"
                )
                if strict:
                    raise ValueError(fault)
                stats.faults.append(fault)
            stats.pairs += 1
            stats.paths += len(routes)
            yield [[in_label, out_label], routes]

        if progress:
            print(
                f"  {in_label}: {sum(len(v) for v in buckets.values())} routes "
                f"over {len(out_labels)} pairs in {perf_counter() - t0:.1f}s",
                flush=True,
            )


# --------------------------------------------------------------------------- #
# writing
# --------------------------------------------------------------------------- #

_COMPACT = (",", ":")
"""Separators for every dump here.

Not cosmetic.  At this scale ``indent=2`` costs about 2.6x, which is the
difference between a four-gigabyte file and one that will not fit in a
ten-gigabyte budget.
"""


def write_netlist_with_states(
    path: Path,
    netlist: Mapping[str, Any],
    records: Iterable[list[Any]],
    *,
    stats: SweepStats | None = None,
) -> Path:
    """Stream the netlist, with ``__states__`` as a top-level key, to `path`.

    ``__states__`` is far too large to build as a Python object first -- as
    live dicts it is roughly an order of magnitude bigger than on disk -- so the
    file is assembled by hand: the ordinary keys, then the states array written
    one pair at a time as the sweep produces them.  The result is an ordinary,
    single, valid JSON document; only the *writing* is incremental.

    Output goes to ``<path>.partial`` and is renamed on success.  A sweep that
    faults has usually already written gigabytes, and a partial file under the
    final name would look authoritative; this way it is there to inspect but
    plainly unfinished.

    Args:
        path: final destination.
        netlist: the flat netlist, without ``__states__``.
        records: pair records, in order.
        stats: if given, the byte and second counts are filled in, split
            between the fixed netlist body and the growing states array.

    Returns:
        The path actually written -- `path` on success, the partial otherwise.
    """
    stats = stats if stats is not None else SweepStats()
    partial = path.with_suffix(path.suffix + ".partial")
    t0 = perf_counter()
    written = 0

    with partial.open("w", encoding="utf-8") as f:
        written += f.write("{")
        for key, value in netlist.items():
            if key == "__states__":
                continue
            written += f.write(f"{json.dumps(key)}:")
            written += f.write(json.dumps(value, separators=_COMPACT))
            written += f.write(",")
        written += f.write('"__states__":[')
        stats.netlist_bytes = written
        stats.netlist_seconds = perf_counter() - t0

        first = True
        for record in records:
            if not first:
                written += f.write(",")
            written += f.write(json.dumps(record, separators=_COMPACT))
            first = False
        written += f.write("]}")

    stats.states_bytes = written - stats.netlist_bytes
    stats.states_seconds = perf_counter() - t0 - stats.netlist_seconds
    stats.seconds = perf_counter() - t0
    if stats.faults:
        return partial
    partial.replace(path)
    return path


# --------------------------------------------------------------------------- #
# driver
# --------------------------------------------------------------------------- #


@dataclass
class Prepared:
    """Everything the sweep needs, from one pass over the netlist.

    Attributes:
        graph: the pruned and contracted flow graph.
        planes: the TE/TM mesh tokens.
        ends: the arms, filtered to the waveguides that survived.
        tm_of: TE -> TM instance names, mesh selectors and MUAs together.
        muas: just the MUA pairing, ``{TE: TM}``.
        unmapped: selectors outside both meshes anywhere on the die, as found
            by the isomorphism check.  Most are unreachable test structures;
            only the ones a route can reach have to be paired.
    """

    graph: nx.DiGraph
    planes: Planes
    ends: Endpoints
    tm_of: dict[str, str] = field(default_factory=dict)
    muas: dict[str, str] = field(default_factory=dict)
    unmapped: list[str] = field(default_factory=list)


def prepare_graph(
    netlist: Mapping[str, Any],
    puc_map: Mapping[str, Mapping[str, str]],
    *,
    n_io: int = 72,
    pairs: Iterable[tuple[str, str]] | None = None,
    port_fn: PortFn = psr_ports,
    verify: bool = True,
) -> Prepared:
    """Build, check, prune and contract the flow graph, and resolve the arms.

    Order matters and is not free to rearrange:

    1.  Build the raw graph.
    2.  Resolve the arms on it and, with `verify`, confirm each feeds the plane
        its name claims -- this needs ``inport``/``outport``, which contraction
        removes.
    3.  Check the two planes are isomorphic, and pair the MUAs, for the same
        reason -- both walk edges that contraction merges away.
    4.  Prune to the waveguides on some route between the arms actually being
        swept, then contract the runs of passives between decision points.
    5.  Filter the resolved arms down to the waveguides that survived, and
        check that every selector still standing can be mapped to the other
        plane.

    A bounded sweep prunes with only the arms it was asked about, so the graph
    it returns is smaller than the full sweep's and its timings are optimistic.
    Sizes per pair extrapolate; seconds per pair do not.

    Args:
        netlist: flat netlist with ``instances`` and ``connections``.
        puc_map: the topolux map.
        n_io: number of input/output PSRs.
        pairs: the pairs to be swept; only their arms are kept by pruning.
            None keeps every arm.
        port_fn: PSR port namer.
        verify: run the arm and isomorphism checks.

    Returns:
        The reduced graph, the plane tokens, the arms on that graph, and the
        TE -> TM name map covering both mesh selectors and MUAs.
    """
    g, report = build_flow_graph(netlist, INTERNAL_CONNECTIONS)
    print(
        f"flow graph: {report['nodes']:,} waveguides, {report['edges']:,} traversals",
        flush=True,
    )
    if report["unknown_components"]:
        print(f"  WARNING blockers: {report['unknown_components']}", flush=True)

    planes = mesh_tokens(puc_map)
    ends = resolve_endpoints(g, planes, n_io=n_io, port_fn=port_fn, verify=verify)
    print(f"endpoints: {endpoint_report(ends)}", flush=True)

    counts = check_plane_isomorphism(g, planes, puc_map)
    print(f"planes isomorphic: {counts['TE']:,} traversals each", flush=True)

    tm_of = tm_name_map(planes, puc_map)
    muas = resolve_muas(g, planes, ends, strict=verify)
    tm_of.update(muas)
    unmapped = counts["unmapped"]
    print(
        f"MUAs: {len(muas)} pairs; {len(unmapped)} selectors outside the meshes "
        "on the die as a whole",
        flush=True,
    )

    in_labels = {i for i, _ in pairs} if pairs else set(ends.labels("in"))
    out_labels = {o for _, o in pairs} if pairs else set(ends.labels("out"))
    sources = [
        n for (lbl, _p), v in ends.sources.items() if lbl in in_labels for n in v
    ]
    targets = [
        n for (lbl, _p), v in ends.targets.items() if lbl in out_labels for n in v
    ]

    before = g.number_of_nodes()
    t0 = perf_counter()
    g = reachable_subgraph(g, sources, targets)
    print(
        f"pruned {before:,} -> {g.number_of_nodes():,} waveguides in "
        f"{perf_counter() - t0:.1f}s",
        flush=True,
    )

    before = g.number_of_nodes()
    t0 = perf_counter()
    contract_chains(g, [n for n in (*sources, *targets) if n in g])
    print(
        f"contracted {before:,} -> {g.number_of_nodes():,} waveguides in "
        f"{perf_counter() - t0:.1f}s",
        flush=True,
    )

    # Node identity survives both stages -- ``reachable_subgraph`` copies nodes
    # and ``contract_chains`` never splices a protected one -- so the reduced
    # arms are the resolved ones filtered to what is left.  Re-resolving here
    # would fail instead: a bounded sweep prunes away every arm it was not asked
    # about, and those are absent by design rather than missing.
    # Now that the graph holds only what a route can reach, every selector left
    # in it must be mappable.  Asking this before pruning would fault on the
    # die's test structures -- spare MUAs wired to nothing -- which are real,
    # unmapped, and completely irrelevant, since no route can get to them.
    routed = traversed_selectors(g)
    paired = set(muas) | set(muas.values())
    stranded = sorted(
        name for name in routed if not planes.plane_of(name) and name not in paired
    )
    print(
        f"routed selectors: {len(routed):,}, of which "
        f"{len(routed & paired):,} MUAs",
        flush=True,
    )
    if stranded and verify:
        raise ValueError(
            f"{len(stranded)} selectors are on a route but in neither mesh and "
            f"on no arm, so they have no TM counterpart: {stranded[:5]}"
        )

    reduced = Endpoints(
        sources={k: [n for n in v if n in g] for k, v in ends.sources.items()},
        targets={k: [n for n in v if n in g] for k, v in ends.targets.items()},
        port=dict(ends.port),
    )
    return Prepared(g, planes, reduced, tm_of, muas, unmapped)


def add_states(
    netlist: Mapping[str, Any],
    puc_map: Mapping[str, Mapping[str, str]],
    path: Path,
    *,
    n_io: int = 72,
    mode: str = "all",
    limit: int | None = None,
    strict: bool = True,
    cutoff: int | None = None,
    on_unmapped: str = "raise",
    port_fn: PortFn = psr_ports,
    progress: bool = True,
) -> tuple[Path, SweepStats]:
    """Sweep the pairs and write the netlist with ``__states__`` to `path`.

    Args:
        netlist: the flat netlist.
        puc_map: the topolux map.
        path: destination file.
        n_io: number of input/output PSRs.
        mode: pair selection, see ``select_pairs``.
        limit: cap on pairs swept.
        strict: raise on an unexpected route count rather than collecting it.
        cutoff: maximum traversals per route.
        on_unmapped: how to treat selectors outside both meshes; see
            ``sweep_records``.
        port_fn: PSR port namer.
        progress: print per-input timings.

    Returns:
        The path written and the statistics of the run.
    """
    pairs = select_pairs(n_io, mode, limit)
    print(f"sweeping {len(pairs):,} of {n_io**2:,} pairs ({mode})", flush=True)

    prep = prepare_graph(netlist, puc_map, n_io=n_io, pairs=pairs, port_fn=port_fn)

    stats = SweepStats()
    t0 = perf_counter()
    records = sweep_records(
        prep.graph, prep.ends, prep.tm_of, pairs, strict=strict, cutoff=cutoff,
        on_unmapped=on_unmapped, stats=stats, progress=progress,
    )
    written = write_netlist_with_states(path, netlist, records, stats=stats)
    stats.seconds = perf_counter() - t0
    return written, stats


def attach_states(
    netlist: Mapping[str, Any],
    puc_map: Mapping[str, Mapping[str, str]] | str | Path,
    path: str | Path,
    *,
    n_io: int = 72,
    **kwargs: Any,
) -> dict[str, Any]:
    """Sweep, write `netlist` with ``__states__`` to `path`, and summarise.

    The one call ``get_netlist_flat`` needs.  Everything is derived from the
    `netlist` mapping passed in: the flow graph is built from its instances and
    connections, so no netlist file has to exist first and no separate run is
    needed.  `puc_map` is the only input read from disk.

    It writes the whole netlist, not just the states, because ``__states__``
    cannot be assembled in memory and handed back -- see
    ``write_netlist_with_states``.  So the caller should *not* dump the returned
    dict over `path` afterwards: the file is already complete, and the returned
    ``__states__`` is a summary standing in for a payload three orders of
    magnitude larger.

    Args:
        netlist: the flat netlist, without ``__states__``.  Instances and
            connections are all the sweep needs.
        puc_map: the topolux map, or a path to read it from.
        path: destination to write to; never read.
        n_io: number of input/output PSRs.
        **kwargs: passed to ``add_states`` -- ``mode``, ``limit``, ``strict``,
            ``cutoff``, ``on_unmapped``, ``port_fn``, ``progress``.

    Returns:
        The summary to put in the returned netlist's ``__states__`` field:
        where the file went, what it contains, and any faults.  With
        ``strict=False`` a faulted sweep reports here and leaves its output
        under ``.partial``; with the default it raises instead.
    """
    if isinstance(puc_map, str | Path):
        puc_map = json.loads(Path(puc_map).read_text())
    written, stats = add_states(netlist, puc_map, Path(path), n_io=n_io, **kwargs)
    return summarise(stats, written, n_io)


def summarise(stats: SweepStats, path: Path, n_io: int = 72) -> dict[str, Any]:
    """The ``__states__`` summary for the returned netlist dict, plus a report.

    Two projections, because one number here would be misleading.  The first
    assumes the rest of the die looks like what was swept; the second assumes
    every pair carries the largest route count the fabric allows.  The truth is
    between them, and how far between depends on the mix of 24/48/96 pairs,
    which only a representative sample can show.
    """
    return {
        "path": str(path),
        "pairs": stats.pairs,
        "paths": stats.paths,
        "paths_per_pair": round(stats.paths_per_pair, 1),
        "selectors_per_route": round(stats.selectors_per_route, 2),
        "min_selectors": stats.min_selectors,
        "max_selectors": stats.max_selectors,
        "netlist_bytes": stats.netlist_bytes,
        "states_bytes": stats.states_bytes,
        "bytes_per_path": round(stats.bytes_per_path),
        "seconds": round(stats.seconds, 1),
        "projected_at_this_rate": stats.extrapolate(n_io**2),
        "projected_worst_case": stats.extrapolate(n_io**2, max(EXPECTED_ROUTES)),
        "faults": stats.faults,
    }
