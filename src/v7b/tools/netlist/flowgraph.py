"""Direction-aware path enumeration for photonic netlists.

Why this exists
---------------
The port-node graph built by ``nxgraph.create_nxgraph`` represents a component
as a *set of port nodes* joined by internal edges.  For a 2x2 PUC the four
internal connections

    o1-o3   o1-o4   o2-o3   o2-o4

form a 4-cycle (K_{2,2}) over the four port nodes.  Nothing in
``nx.all_simple_paths`` forbids walking around that cycle, so a "simple" path
can chain several internal edges in a row::

    puc,o1 -> puc,o3 -> puc,o2 -> puc,o4

which is not a physical route (light would have to re-enter the coupler through
the port it just left).  Two consequences:

1.  The path count is inflated multiplicatively -- one spurious factor per PUC
    on the route -- which is a large part of the runtime problem.
2.  ``calculate_paths.pairwise`` chunks the node list into *non-overlapping*
    pairs on the assumption that internal and external edges strictly
    alternate.  Chained internal edges break that assumption silently: the
    same instance gets counted twice and metrics are attributed to the wrong
    component.

The fix is representational.  Here:

    node = a *directed* waveguide, i.e. the tuple (src_port, dst_port),
           meaning "light leaves src_port and enters dst_port"
    edge = exactly one traversal of exactly one component, carrying that
           component's metrics as edge data

Alternation is then structural, not something the traversal has to respect by
convention: every edge is a component traversal and every node is a waveguide.
Reflection is impossible by construction (see ``assert_no_reflection``), and a
simple path -- no repeated node -- means no reused waveguide, which is the
physically correct uniqueness rule.

Concepts, for readers who do not work with graphs
-------------------------------------------------
**Graph, node, edge.**  A graph is just "things" (nodes) and "connections
between things" (edges).  Which one you make the component and which one you
make the waveguide is a design choice, and it is the whole trick in this module:
we put the *waveguides* in the nodes and the *components* in the edges, because
that is the arrangement in which an illegal route becomes impossible to express
rather than merely discouraged.

**Directed edge.**  An edge you may only cross one way, like a one-way street.
Light in a routed circuit has a direction of travel, so every edge here is
directed, and each physical waveguide appears twice -- once per direction.  The
reverse-direction copies exist so the code makes no assumption about which way
the fabric flows; ``reachable_subgraph`` deletes the ones no route can use.

**DFS (depth-first search).**  How ``enumerate_paths`` finds routes: follow one
waveguide as far as it goes, and when you run out of options, step back to the
last place you had a choice and take the next one.  Exactly how you would trace
a route with a finger on a layout.  The cost of DFS is *not* the number of
routes it returns -- it is the number of partial routes it tries, including all
the ones that dead-end.  That gap is why the original script could take hours to
produce sixteen answers, and why the two optimisations below matter so much.

**Cycle and DAG.**  A cycle is a loop you can go around and arrive back where
you started.  A *DAG* -- directed acyclic graph -- is a graph with no such
loops, which is what a feed-forward fabric produces: light always makes net
forward progress, so it can never return to a waveguide it has already used.
DAGs are much easier to reason about, and several shortcuts here (``count_paths``
by arithmetic, and the safety of ``contract_chains``) are valid only on a DAG.
``nx.is_directed_acyclic_graph`` is the check.

**Contraction.**  Collapsing a run of nodes that offer no choices into a single
edge, adding up what was on the way.  A thousand straights and bends between two
selectors form one such run: there is nothing to decide along it, so it can be
replaced by one edge labelled "these are the lengths and bends you accumulate
getting from here to there".  See ``contract_chains``.

**Pruning.**  Deleting the parts of the graph that provably cannot appear in any
answer, before searching.  See ``reachable_subgraph``.

Reading order: ``build_flow_graph`` (construction), ``reachable_subgraph`` and
``contract_chains`` (making the graph small), ``enumerate_paths`` (the search),
then the ``path_*`` helpers (reading results off a route).

"""

from __future__ import annotations

from collections import deque
from collections.abc import Hashable, Iterable, Iterator, Mapping, Sequence
from typing import Any

import networkx as nx

Port = str  # "instance,port"
Wg = tuple[Port, Port]  # directed waveguide: (src_port, dst_port)

# --------------------------------------------------------------------------- #
# metrics
# --------------------------------------------------------------------------- #


def traversal_metrics(
    record: Mapping[str, Any], inport: str, outport: str
) -> dict[str, float]:
    """Metrics accumulated by traversing one component from `inport` to `outport`.

    Mirrors the tallies in ``calculate_paths.process_path``, but the traversal
    direction is now unambiguous, which matters for the ``crossing_anwg_si``
    layer assignment.
    """
    comp = record["component"]
    m: dict[str, float] = {f"n_{comp}": 1}

    if comp == "straight":
        info = record.get("info", {})
        width = info.get("width")
        length = float(info.get("length", 0.0))
        key = {
            0.41: "length_041",
            0.93: "length_093",
            1.56: "length_156",
            2.0: "length_200",
        }.get(width, "length_other")
        m[key] = length
    elif comp == "bend_modified_hermite":
        m["bends_45"] = 1
    elif comp == "bend":
        m["bends_90"] = 1
    elif comp == "taper":
        m["n_rib_taper"] = 1
    elif comp == "vertical_transition":
        m["n_transition_si_sin2"] = 1
    elif comp == "crossing_anwg_si":
        m["crossings_sin2" if outport in ("o1", "o3") else "crossings_si"] = 1
    return m


def short_name(instance: str) -> str:
    """Leaf name of a hierarchical instance path: "...~puc1322_289596_0" -> "puc1322"."""
    return instance.split("~")[-1].split("_")[0]


def add_metrics(*dicts: Mapping[str, float]) -> dict[str, float]:
    """Sum metric dicts. Plain dict, not Counter: Counter.__add__ drops zeros."""
    out: dict[str, float] = {}
    for d in dicts:
        for k, v in d.items():
            out[k] = out.get(k, 0) + v
    return out


# --------------------------------------------------------------------------- #
# construction
# --------------------------------------------------------------------------- #


def external_map(netlist: Mapping[str, Any]) -> dict[Port, Port]:
    """Port -> the single port it is physically connected to.

    Netlist connections form a perfect matching over connected ports; a port
    appearing twice means the netlist is inconsistent, so it raises rather than
    silently picking one peer.
    """
    peer: dict[Port, Port] = {}
    for u, vs in netlist["connections"].items():
        for v in (vs,) if isinstance(vs, str) else vs:
            for a, b in ((u, v), (v, u)):
                if peer.setdefault(a, b) != b:
                    raise ValueError(
                        f"port {a!r} connected to both {peer[a]!r} and {b!r}"
                    )
    return peer


def build_flow_graph(
    netlist: Mapping[str, Any],
    internal_connections: Mapping[str, Sequence[Any]],
    *,
    metrics_fn=traversal_metrics,
) -> tuple[nx.DiGraph, dict[str, Any]]:
    """Build the directed waveguide graph.

    Returns the graph plus a report dict. Components missing from
    ``internal_connections`` get no traversal edges at all, i.e. they silently
    become path *blockers* -- the report lists them so that never happens
    unnoticed.
    """
    peer = external_map(netlist)
    g = nx.DiGraph()
    unknown: dict[str, int] = {}
    dangling: list[Port] = []
    # port names in this netlist run to ~200 characters and each appears in two
    # nodes; interning keeps one copy instead of one per f-string
    pool: dict[str, str] = {}

    def intern_port(p: str) -> str:
        return pool.setdefault(p, p)

    for inst, record in netlist["instances"].items():
        comp = record["component"]
        channels = internal_connections.get(comp)
        if channels is None:
            unknown[comp] = unknown.get(comp, 0) + 1
            continue
        for chan in channels:
            state = (chan.data or {}).get("puc_k")
            for a, b in ((chan.p1, chan.p2), (chan.p2, chan.p1)):
                pa, pb = f"{inst},{a}", f"{inst},{b}"
                if pa not in peer or pb not in peer:
                    dangling.extend(p for p in (pa, pb) if p not in peer)
                    continue
                g.add_edge(
                    (intern_port(peer[pa]), intern_port(pa)),  # arriving at port a
                    (intern_port(pb), intern_port(peer[pb])),  # leaving from port b
                    instance=inst,
                    component=comp,
                    inport=a,
                    outport=b,
                    m=metrics_fn(record, a, b),
                    pucs=(f"{short_name(inst)}, {a}",) if comp == "puc" else (),
                    puc_states=((inst, float(state)),) if state is not None else (),
                    traversals=1,
                    **(chan.data or {}),
                )

    report = {
        "nodes": g.number_of_nodes(),
        "edges": g.number_of_edges(),
        "unknown_components": unknown,
        "dangling_ports": sorted(set(dangling)),
    }
    return g, report


def waveguides_from(g: nx.DiGraph, port: Port) -> list[Wg]:
    """Waveguides on which light *leaves* `port` -- use as enumeration sources."""
    return [n for n in g if n[0] == port]


def waveguides_into(g: nx.DiGraph, port: Port) -> list[Wg]:
    """Waveguides on which light *arrives* at `port` -- use as targets."""
    return [n for n in g if n[1] == port]


# --------------------------------------------------------------------------- #
# pruning
# --------------------------------------------------------------------------- #


def reachable_subgraph(
    g: nx.DiGraph, sources: Iterable[Wg], targets: Iterable[Wg]
) -> nx.DiGraph:
    """Keep only waveguides lying on some source -> target route.

    Two linear sweeps: forward from the sources, then backward from the targets
    through the forward set.  A node surviving both is on at least one route, so
    a DFS restricted to this subgraph never explores a branch that cannot reach
    a target.  With all targets harvested in one traversal that makes
    enumeration output-sensitive: every step taken contributes to a route.

    In detail.  The first sweep marks everywhere light from an input can get to,
    by repeatedly taking a marked waveguide and marking the ones downstream of
    it.  The second does the same backwards from the outputs, staying inside the
    first set, marking everywhere that can still reach an output.  Survive both
    and you are downstream of an input *and* upstream of an output, which is
    precisely what it means to be on a route.

    "Linear" means each waveguide and each traversal is looked at a fixed number
    of times, so the cost grows in proportion to the size of the graph -- unlike
    the search itself, whose cost grows with the number of partial routes.  A
    linear pass over a million-node graph is seconds; that is why it is always
    worth doing before searching, even when it removes nothing.

    On a feed-forward fabric this drops roughly half the graph on its own: the
    flow graph holds both directions of every waveguide, and the ones pointing
    against the flow are on no route at all.

    This also converts the worst case into a fast answer.  A DFS looking for a
    route that does not exist has no early exit -- it explores the entire
    reachable component before concluding nothing is there.  Here a source that
    cannot reach any target simply drops out of the graph, and the caller can
    say so immediately.

    Returns a new graph; `g` is left alone.
    """

    fwd: set[Wg] = set()
    stack = [s for s in sources if s in g]
    while stack:
        n = stack.pop()
        if n in fwd:
            continue
        fwd.add(n)
        stack.extend(g._succ[n])

    bwd: set[Wg] = set()
    stack = [t for t in targets if t in fwd]
    while stack:
        n = stack.pop()
        if n in bwd:
            continue
        bwd.add(n)
        stack.extend(p for p in g._pred[n] if p in fwd)

    return g.subgraph(bwd).copy()


# --------------------------------------------------------------------------- #
# contraction
# --------------------------------------------------------------------------- #


def contract_chains(g: nx.DiGraph, protect: Iterable[Wg] = ()) -> nx.DiGraph:
    """Splice out every pass-through waveguide, summing metrics onto one edge.

    A waveguide with exactly one traversal in and one out is not a decision
    point -- it is a straight, bend, taper or crossing in the middle of a run of
    routing.  Removing it and merging the two traversals into a single edge
    preserves every route and every metric while collapsing the graph to its
    branch points, which in a selector fabric is a few thousand nodes rather
    than a million.

    Mutates and returns `g`.  `protect` must contain every node used as an
    enumeration source or target, since those must survive as endpoints.

    "Exactly one in and one out" is what ``in_degree(n) == 1 and
    out_degree(n) == 1`` says: degree counts the edges at a node, so a node with
    one of each is somewhere light arrives by a single route and departs by a
    single route -- no decision, nothing for the search to branch on.  Selectors
    are unaffected: the waveguide feeding a 2x2 selector has two ways out (to
    each of its two output arms), so its out-degree is 2 and it survives as a
    node.  That is exactly the behaviour you want -- the contracted graph keeps
    every point where a route makes a choice and discards everything else.

    Two guards worth knowing about.  Splicing is skipped when `u` and `w` are
    already joined, because two routes between the same pair would need two
    parallel edges and this is a plain DiGraph; leaving the node in place is
    correct, just slightly less reduced.  And nodes are re-queued after a splice
    so a run collapses all the way along instead of one hop per pass.

    One caveat: the intermediate waveguides no longer exist as nodes, so the
    no-reused-waveguide rule can no longer reject a route that revisits one.
    On an acyclic flow graph -- any feed-forward fabric -- no route can revisit
    anything, so the contraction is exact.  Check
    ``nx.is_directed_acyclic_graph`` before relying on it.
    """

    protect = set(protect)

    def spliceable(n):
        return n not in protect and g.in_degree(n) == 1 and g.out_degree(n) == 1

    work = deque(n for n in list(g) if spliceable(n))

    while work:
        v = work.popleft()
        if v not in g or not spliceable(v):
            continue
        u = next(g.predecessors(v))
        w = next(g.successors(v))
        if u is v or w is v or u is w or g.has_edge(u, w):
            # a parallel edge would need a MultiDiGraph; leave this one in place
            continue
        a, b = g.edges[u, v], g.edges[v, w]
        g.add_edge(
            u,
            w,
            m=add_metrics(a["m"], b["m"]),
            pucs=a["pucs"] + b["pucs"],
            puc_states=a.get("puc_states", ()) + b.get("puc_states", ()),
            traversals=a["traversals"] + b["traversals"],
        )
        g.remove_node(v)
        work.extend(x for x in (u, w) if x in g and spliceable(x))
    return g


# --------------------------------------------------------------------------- #
# enumeration
# --------------------------------------------------------------------------- #


def _wg_key(n: Wg) -> Wg:
    """Direction-insensitive waveguide identity.

    A waveguide appears in the graph as two nodes, one per direction.  Sorting
    the pair gives both the same key, so "have I used this waveguide?" can be
    asked without caring which way round it was used.
    """
    return n if n[0] <= n[1] else (n[1], n[0])


def enumerate_paths(
    g: nx.DiGraph,
    sources: Iterable[Wg],
    targets: Iterable[Wg],
    *,
    cutoff: int | None = None,
    max_paths: int | None = None,
    unique_waveguides: bool = True,
) -> Iterator[list[Wg]]:
    """Yield node paths (lists of directed waveguides) from sources to targets.

    A depth-first search, written out explicitly rather than with recursion so
    that very long routes cannot overflow the Python stack.  Three pieces of
    state, which is all a DFS ever needs:

    * ``path``  -- the route traced so far, from the source to wherever we are.
    * ``used``  -- the waveguides already on it, so we never reuse one.
    * ``stack`` -- for each step of ``path``, an iterator over the ways onward
      that we have not tried yet.

    The loop asks the top iterator for the next way onward.  If it is exhausted
    (``child is None``) there is nothing left to try here, so we drop back one
    step -- that is the *backtracking* -- and continue from the previous choice.
    Otherwise, a waveguide already in ``used`` is skipped, a target is a finished
    route and gets yielded, and anything else is stepped onto and explored.

    Every route is yielded as it is found rather than collected into a list, so
    the caller can process millions of routes without them all being in memory
    at once, and can stop early.

    Pass *all* the targets you care about at once.  One traversal that harvests
    every output is dramatically cheaper than one traversal per output, because
    the routes to different outputs share almost all of their prefix and a
    per-target search re-walks that prefix every time.

    Args:
        cutoff: maximum number of component traversals per path. Strongly
            recommended -- see ``count_paths`` first.
        max_paths: stop after this many paths.
        unique_waveguides: if True (default) a waveguide may not be reused in
            either direction. If False, only the *directed* waveguide is
            unique, which permits counter-propagating reuse of one waveguide.

    Yields:
        Each route as a list of waveguide nodes. Turn one into components and
        metrics with ``traversals``, ``path_metrics`` and ``path_pucs``.
    """

    target_set = set(targets)
    key = _wg_key if unique_waveguides else (lambda n: n)
    found = 0

    for source in sources:
        if source in target_set:
            yield [source]
            found += 1
            if max_paths is not None and found >= max_paths:
                return
            continue

        path: list[Wg] = [source]
        used: set[Hashable] = {key(source)}
        stack: list[Iterator[Wg]] = [iter(g[source])]

        while stack:
            child = next(stack[-1], None)
            if child is None:
                stack.pop()
                used.discard(key(path.pop()))
                continue
            k = key(child)
            if k in used:
                continue
            if child in target_set:
                yield [*path, child]
                found += 1
                if max_paths is not None and found >= max_paths:
                    return
                continue
            if cutoff is not None and len(path) >= cutoff:
                continue
            path.append(child)
            used.add(k)
            stack.append(iter(g[child]))


def count_paths(
    g: nx.DiGraph, sources: Iterable[Wg], targets: Iterable[Wg]
) -> int | None:
    """Exact path count without enumerating, or None if `g` has cycles.

    Counts by working backwards.  If you know, for every waveguide, how many
    routes lead from it to an output, then the answer for any waveguide is just
    the sum of those numbers over the places it can go next (plus one if it is
    itself an output).  So visit the waveguides in an order where every "next"
    is already solved, and each is a single addition.

    That order is a *topological sort*: an ordering of a DAG in which every edge
    points forwards.  It exists only when the graph has no cycles -- with a loop
    there is no consistent "later", and the recursion above would chase itself
    forever -- which is why this returns None instead of guessing.  Counting
    routes in a graph with cycles is a genuinely hard problem, not merely a
    slower version of this one.

    Call this *before* enumerating. On an acyclic flow graph this answers "how
    many paths are there" in O(V+E) instead of O(paths); if the answer does not
    fit in a spreadsheet, no amount of parallelism will help.
    """

    if not nx.is_directed_acyclic_graph(g):
        return None
    target_set = set(targets)
    to_target: dict[Wg, int] = {}
    for n in reversed(list(nx.topological_sort(g))):
        total = 1 if n in target_set else 0
        total += sum(to_target.get(s, 0) for s in g[n])
        to_target[n] = total
    return sum(to_target.get(s, 0) for s in sources)


# --------------------------------------------------------------------------- #
# reading results
# --------------------------------------------------------------------------- #


def traversals(g: nx.DiGraph, path: Sequence[Wg]) -> list[dict[str, Any]]:
    """Edge data for each component traversal along `path`."""
    return [g.edges[u, v] for u, v in zip(path, path[1:], strict=False)]


def path_metrics(g: nx.DiGraph, path: Sequence[Wg]) -> dict[str, float]:
    return add_metrics(*(t["m"] for t in traversals(g, path)))


def path_pucs(g: nx.DiGraph, path: Sequence[Wg]) -> list[str]:
    """The ``pucs`` column, by concatenating each edge's contribution.

    Works identically on a raw and a contracted graph: contraction concatenates
    these lists, so a contracted edge already carries the PUCs it absorbed in
    order.  Never materialises the full traversal list, which after contraction
    is the only affordable way to do this -- a single route here crosses tens of
    thousands of components.
    """
    return [
        p for u, v in zip(path, path[1:], strict=False) for p in g.edges[u, v]["pucs"]
    ]


def path_puc_states(g: nx.DiGraph, path: Sequence[Wg]) -> dict[str, float]:
    """The switch state every selector on `path` must be set to, in traversal order.

    Each selector traversal fixes the state of that selector: entering ``o1``
    and leaving ``o3`` means cross (1.0), entering ``o1`` and leaving ``o4``
    means bar (0.0).  Those values come from ``puc_k`` in the internal-channel
    table, so this reads the route's requirement rather than restating it.

    Like ``path_pucs`` this works identically before and after contraction, and
    never materialises the traversal list.  Unlike it, the result is keyed by
    the *full* hierarchical instance name, which is what the topolux map is
    keyed by.

    Args:
        g: flow graph, raw or contracted.
        path: route, as yielded by ``enumerate_paths``.

    Returns:
        ``{instance: state}``, insertion-ordered by first traversal.

    Raises:
        ValueError: if a selector is traversed twice.  On an acyclic fabric a
            route cannot revisit one, so this means the graph is not the fabric
            it is assumed to be -- the alternative, silently keeping one of the
            two states, would emit a route that cannot be configured.
    """
    states: dict[str, float] = {}
    for u, v in zip(path, path[1:], strict=False):
        for instance, state in g.edges[u, v].get("puc_states", ()):
            if instance in states:
                raise ValueError(
                    f"{instance} traversed twice on one route "
                    f"(states {states[instance]} then {state})"
                )
            states[instance] = state
    return states


def path_traversal_count(g: nx.DiGraph, path: Sequence[Wg]) -> int:
    """Total components the light passes through along `path`.

    Everything on the route -- selectors, straights, bends, tapers, crossings --
    not just the selectors, so it is normally far larger than ``Number pucs``.
    The two terminal components are excluded: a route begins on the waveguide
    *leaving* the input port and ends on the one *arriving* at the output port,
    so the PSRs at each end are the endpoints rather than things traversed.

    This reads a stored count rather than measuring the length of `path`, which
    matters after contraction: one contracted edge stands for a whole run of
    components, so the number of *nodes* on the route no longer reflects the
    number of components on it.  ``contract_chains`` adds the counts up as it
    merges, and this sums them back, so the answer is the same before and after.
    """

    return sum(
        g.edges[u, v]["traversals"] for u, v in zip(path, path[1:], strict=False)
    )


# --------------------------------------------------------------------------- #
# structural invariants
# --------------------------------------------------------------------------- #


def assert_no_reflection(g: nx.DiGraph) -> None:
    """No edge may enter and leave a component through the same port, and no
    two-cycles may exist. Both hold by construction; this pins them down.

    A *reflection* would be light entering a component and coming straight back
    out of the port it arrived on, and a *two-cycle* would be a pair of edges
    letting a route go somewhere and immediately return.  Neither is physical,
    and neither can be built by ``build_flow_graph`` -- the point of asserting
    it is that if anyone changes the construction, this fails loudly rather than
    quietly admitting impossible routes.
    """
    for u, v, d in g.edges(data=True):
        assert d["inport"] != d["outport"], (u, v)
        assert u[1] != v[0], f"reflection at {u[1]}"
        assert not g.has_edge(v, u), f"2-cycle {u} <-> {v}"


def assert_valid_path(g: nx.DiGraph, path: Sequence[Wg]) -> None:
    """A path is valid iff consecutive traversals hand off across a waveguide
    and no component is traversed twice in a row.

    Three properties of a physical route, checked directly: each component's
    exit port is where the next one's entry port is wired, no component appears
    twice in succession (which would be the coupler bounce the old port-node
    graph allowed), and no waveguide is used twice.

    Only meaningful on an uncontracted graph, where every edge is one component.
    """

    travs = traversals(g, path)
    for (u, v), t in zip(zip(path, path[1:], strict=False), travs, strict=True):
        assert u[1] == f"{t['instance']},{t['inport']}"
        assert v[0] == f"{t['instance']},{t['outport']}"
    for a, b in zip(travs, travs[1:], strict=False):
        assert (
            a["instance"] != b["instance"]
        ), f"consecutive traversal of {a['instance']}"
    keys = [_wg_key(n) for n in path]
    assert len(set(keys)) == len(keys), "waveguide reused"
