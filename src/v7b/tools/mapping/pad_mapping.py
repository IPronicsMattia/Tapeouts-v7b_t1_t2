"""Assign a functional name to every flip-chip pad on the die.

The die is tiled with identical circular pads.  Each one either serves a
component -- a PUC arm, a photodiode, a thermistor, a shared ground or bias
group, a continuity chain -- or serves nothing and is a dummy.  This module
recovers that association from the *layout* and names each pad accordingly, then
writes the pad mapping spreadsheet: ``PAD_ID``, ``x_location``, ``y_location``,
``signal_ground``, ``name``.

Everything comes from the layout.  The netlist records neither the electrical
port locations nor, in several cases, the association at all, and a route does
not always start at the port it belongs to -- so components are found by cell
name, their terminals probed on the metal they leave on, and the pads reached by
following the extracted nets.

Structure
---------
One :class:`PadMapContext` holds the work every rule needs and none may repeat:
the pad list with its ``PAD_ID`` numbering, and one net extraction over
MT1/Via1/MT2/Via2/MT3.  Each rule is then a separate function taking that
context and returning ``{pad index: Assignment}``, so rules stay independent and
individually testable.  :func:`merge_assignments` combines the dicts and marks
any pad two rules claim differently as ``ERROR``; :func:`write_pad_mapping`
writes the sheet.

The rules, and what names they produce:

===========================  ==================================================
:func:`assign_puc_signals`   ``PUC<n>_<top|bot>[_MUA]_<TE|TM>``
:func:`assign_puc_grounds`   ``GND_MESH`` / ``GND_MUA``
:func:`assign_pd_signals`    ``PD<n>[_<top|bot>]_<MESH|MUA>_<TE|TM>``
:func:`assign_pd_bias`       ``BIAS_MESH`` / ``BIAS_MUA``
:func:`assign_thermistors`   ``TH_<n>_<S|G>``
:func:`assign_dc_chains`     ``DC<block>.<n>``
:func:`assign_dummies`       ``DUMMY``
===========================  ==================================================

Only :func:`assign_dc_chains` needs an argument beyond the context: the
rectangles covering the continuity ring.

Passing ``pic_names=load_pic_names(<netlist>)`` to :func:`write_pad_mapping`
adds a ``PIC name`` column, filled on PUC and PD *signal* rows with that
instance's full hierarchical name from the netlist. Shared pads -- grounds, bias
pairs, chain and dummy pads -- are left blank, having no single owning instance.

Four ideas do most of the work
------------------------------
**Probe, then follow the net.**  Every component rule shares
:func:`port_roles`: each electrical port's possible attachment points are tested
for metal in one batched pass, each live one resolved to a net, and the net
followed to the pads it reaches.  Rules differ only in which cells they match,
which layer the terminals sit on (MT3 for PUCs, MT2 for PDs, MT1 for
thermistors) and where a route may attach.

**Attachment offsets are expressed rotation-free.**  A PUC route attaches at the
port or 5.5 um away; a PD's ``e1`` at 90 degrees may attach 15.8 um away.  Both
are written in terms of the port's own normal rather than as a table indexed by
instance rotation -- ``5.5 backwards along the normal plus 5.5 laterally away
from the component centre`` for the PUC, ``15.8 backwards along the normal`` for
the PD.  Each reproduces the measured tables exactly and cannot be misapplied to
an orientation it was not measured at.

**Roles are inferred where they vary and asserted where they do not.**  On a PUC
either port of an arm may be the signal, so the pad count decides: one pad is a
signal, two or three a joined ground group.  On a PD and a thermistor the port
names fix the meaning, so the same pad count becomes a check instead -- a
deviation is an error, never a reclassification.

**Polarization comes from pairing, not from a boundary.**  The two halves of the
die overlap in x -- the first TM column shares an x with the last TE column -- so
no vertical line classifies every PUC.  Every PUC cell is instanced exactly
twice, once per half, so :func:`puc_polarizations` takes the lower-x instance of
each cell as TE and the other as TM.  The comparison is between two instances of
one cell, which is why an overlap in absolute x cannot break it.

What produces an ERROR
---------------------
No rule ever guesses.  Where the evidence is contradictory, incomplete, or
inconsistent with the structure the die is supposed to have, the affected pads
are named ``ERROR`` and the reason is recorded in the diagnostics, which
:func:`write_pad_mapping` puts on its second sheet.  The full set of checks:

*Shorts and contested pads*
  - One pad reached by two different components, or claimed by two rules under
    different names -- caught in :func:`merge_assignments`, which is the only
    place a cross-rule collision is visible.
  - A signal net reaching more than one pad, on any component: a PUC arm, a PD's
    ``e2``, a thermistor port. Two pads on a signal net means the routes are
    shorted, or a route lands on a neighbouring pad.
  - A port whose two attachment points resolve to *different* nets. (Both
    resolving to the same net is normal: a wide route may cover the port and its
    offset point alike.)
  - A group larger than its kind allows -- more than three pads on a PUC ground,
    more than two on a PD bias, more than two on a chain bar.

*Missing or dangling connections*
  - A PUC arm with no signal candidate, or with two: either port may be the
    signal, so exactly one must reach a lone pad.
  - A port with metal and a net, but whose net reaches no pad at all.
  - A PD's ``e2`` not reaching exactly one pad, or ``e1`` not reaching exactly
    two. Unlike a PUC, a PD's port names fix the meaning, so these are checks.
  - A thermistor port not reaching exactly one pad.
  - A PUC without exactly two ground ports, one per arm.
  - A PUC whose two ground ports reach *different* groups rather than the one
    they share.

*Group geometry*
  - A joined group whose pads are not collinear.
  - A group whose covered extent does not match a real join -- 245.656 um for a
    pair, 425.656 um for a ground triple -- reconstructed from the pad span plus
    the pad diameter, so it validates spacing without assuming the pitch.
  - A join that fails the width probe: no metal 25 um off its centreline means
    the pads are bridged by something narrower than a ground or bias join. This
    is the only check that separates a ground pair from a continuity pair, whose
    bounding boxes are identical.
  - Conversely, a chain link *wider* than 20 um: a ground join inside the
    continuity ring.
  - A chain bar not spanning 180 um.

*Identity and association*
  - A PUC cell not instanced exactly twice, or whose two instances share an x:
    polarization is decided by pairing the two halves, so neither can be
    resolved and the name would carry a guessed TE/TM.
  - A PUC pair whose separation differs from the block offset every other pair
    shows -- one of the two is misplaced.
  - A PD cell name that does not name its owner PUC.
  - A PD naming a PUC absent from the layout, or one where two instances of that
    cell are equally close, leaving the owner ambiguous.
  - A mesh PUC with more than one PD, or a MUA PUC without exactly two.
  - A MUA PUC whose two PDs share a y, leaving top/bot undecidable.
  - An unrecognised component kind, where MESH could not be told from MUA.

*Continuity chains*
  - A square that does not close, or that contains a dangling end pad.
  - A pad appearing in two connections, or in none -- either means the walk does
    not match the drawn topology, usually because the bars are staggered rather
    than aligned between the two rows.
  - A zone holding a number of rows that is neither 1 (chain), 2 (square) nor 3
    (square plus chain).
  - A pad falling inside two DC zones. Configurable: by default the earlier
    block takes a shared corner pad.

*Left over*
  - With every rule enabled and ``unresolved="ERROR"``, any pad no rule claimed.
    Dummies are identified positively, so a leftover pad is one that is neither
    properly connected nor electrically isolated.

Distinguishing joins
--------------------
Three different things join pads, and two of them are indistinguishable by
bounding box, which is worth knowing before changing any of this.  Pads are
65.656 um across on a 180 um pitch, so a ground pair (65.656 + 180 = 245.656),
and a continuity pair joined by a 180 x 20 bar, occupy *exactly* the same
245.656 x 65.656 box.  They are told apart by probing 25 um off the join
centreline: inside a solid join, outside a 20 um bar.

Tested against gdsfactory 9.12 (kfactory 1.10, which pins KLayout 0.30.x).
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

import klayout.db as kdb

__all__ = [
    # data types
    "Assignment",
    "DcConnection",
    "InstancePorts",
    "LayerStack",
    "Pad",
    "PadMapContext",
    "PdOwner",
    "PlacedInstance",
    "PortRole",
    "PucPorts",
    # discovery and shared passes
    "block_offset",
    "find_instances",
    "pd_port_roles",
    "port_probe_points",
    "port_roles",
    "puc_polarizations",
    "puc_port_roles",
    "th_port_roles",
    # naming rules
    "assign_dc_chains",
    "assign_dummies",
    "assign_pd_bias",
    "assign_pd_signals",
    "assign_puc_grounds",
    "assign_puc_signals",
    "assign_thermistors",
    # name grammar helpers
    "order_thermistors",
    "parse_pd_owner",
    "pd_signal_name",
    "puc_signal_name",
    # merge and output
    "PicNames",
    "load_pic_names",
    "pic_match_report",
    "merge_assignments",
    "pad_mapping_rows",
    "write_pad_mapping",
]


UNRESOLVED = "UNRESOLVED"
"""Placeholder for a pad no rule has claimed.

Deliberately *not* ``DUMMY``.  Dummies are identified positively, by
:func:`assign_dummies` testing that a pad's MT3 does not extend beyond the pad,
so a pad left over after every rule has run is neither properly connected nor
isolated -- which is a finding, not a dummy.  With the full rule set in place,
pass ``unresolved="ERROR"`` to :func:`write_pad_mapping` so those pads are
flagged; the default placeholder exists for runs with only some rules enabled.
"""

# --------------------------------------------------------------------------- #
# layers
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class LayerStack:
    """The metal/via stack the pad routing lives on, as ``(layer, datatype)``.

    Connectivity is MT1-Via1-MT2-Via2-MT3.  Pads and PUC electrical ports are on
    MT3; a route may drop to MT2 or MT1 and come back, which is why the whole
    stack has to be extracted rather than just MT3.
    """

    m1: tuple[int, int] = (8, 0)
    m2: tuple[int, int] = (18, 0)
    m3: tuple[int, int] = (28, 0)
    via1: tuple[int, int] = (17, 0)
    via2: tuple[int, int] = (27, 0)


# --------------------------------------------------------------------------- #
# result types
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Pad:
    """One pad instance, with its absolute centre in the die frame (um)."""

    index: int
    """Stable index into :attr:`PadMapContext.pads`, in discovery order."""
    x: float
    y: float
    pad_id: str = ""
    """``flipchip_pad<N>``, numbered in reading order: the top row first, left to
    right within each row."""
    row: int = -1
    col: int = -1


@dataclass(frozen=True)
class Assignment:
    """One naming decision about one pad."""

    name: str
    """The functional name, or ``"ERROR"``."""
    signal_ground: int
    """1 for a signal pad, 0 for ground / chain / dummy / error."""
    source: str = ""
    """Which rule produced this, e.g. ``"puc_signal"`` -- used by the merge
    stage to report *which* two rules collided on a doubly-claimed pad."""
    evidence: str = ""
    """Why, in words. The only thing that makes an ``ERROR`` actionable."""
    component: tuple[str, int, int] | None = None
    """:attr:`PlacedInstance.origin_key` of the component that named this pad.

    The cell name alone would not do: a PUC cell is instanced twice, so
    ``puc2163`` names two different PUCs with two different netlist paths. Only
    the PUC and PD signal rules set this, since those are the rows that carry a
    PIC name.
    """


@dataclass(frozen=True)
class PlacedInstance:
    """A component instance with everything resolved into the die frame.

    Ports are already transformed, so nothing downstream has to know the
    instance orientation -- which matters here because the probe rule is
    expressed in terms of port normals.
    """

    cell: str
    """Referenced cell name, e.g. ``"puc1322"`` or ``"pucmua1204"``."""
    kind: str
    """Leading alphabetic part of the cell name, e.g. ``"puc"``/``"pucmua"``."""
    number: str
    """Trailing digits of the cell name, e.g. ``"1322"``."""
    x: float
    y: float
    ports: dict[str, tuple[float, float, float]] = field(default_factory=dict)
    """``{port name: (x um, y um, orientation degrees)}`` in the die frame."""

    origin: tuple[float, float] = (0.0, 0.0)
    """The instance's placement point in the die frame (um) -- where the cell's
    own origin lands, which is *not* the bbox centre.

    This is the coordinate a gdsfactory netlist records under ``placements``, so
    it is what a netlist entry has to be matched on.
    """

    @property
    def key(self) -> tuple[str, int, int]:
        """Hashable identity of this *instance*, by bbox centre.

        The cell name alone is not an identity: every PUC cell is instanced twice,
        once per polarization, so two different PUCs share a name.
        """
        return (self.cell, round(self.x * 1000), round(self.y * 1000))

    @property
    def origin_key(self) -> tuple[str, int, int]:
        """Hashable identity by placement point, for matching a netlist entry."""
        return (self.cell, round(self.origin[0] * 1000), round(self.origin[1] * 1000))


# --------------------------------------------------------------------------- #
# instance extraction
# --------------------------------------------------------------------------- #

_CELL_SPLIT = re.compile(r"^([A-Za-z_]+?)(\d+)")


def find_instances(
    die: Any,
    name_glob: str,
    *,
    name_regex: str | None = None,
    with_ports: bool = True,
) -> list[PlacedInstance]:
    r"""Every instance of a cell matching ``name_glob``, at any nesting depth.

    The recursive instance iterator reports matches at any depth, and
    ``it.trans() * it.inst_trans()`` is the full transform from the target cell's
    own coordinates into the die frame -- it already folds in every container
    translation and rotation above the target, so none has to be composed by
    hand. Ports are pushed through the same transform, which is what lets the
    probe rules work in absolute coordinates without knowing the hierarchy.

    Args:
        die: gdsfactory ``Component`` (needs ``.kcl`` and ``.kdb_cell``).
        name_glob: anchored KLayout glob on the target cell name, pushed into
            the iterator so non-matching cells are never visited.
        name_regex: optional exact ``re.fullmatch`` filter on top of the glob,
            for the cases a glob cannot express -- e.g. ``r"puc(mua)?\\d+"`` to
            keep ``puc7`` and ``pucmua7`` while rejecting ``puc_test``.
        with_ports: read and transform the cell's ports. Skip it for cells whose
            ports are irrelevant; it is the expensive part.

    Returns:
        One :class:`PlacedInstance` per instance, in iterator order.
    """
    dbu = die.kcl.dbu
    pat = re.compile(name_regex) if name_regex else None

    it = die.kdb_cell.begin_instances_rec()
    it.targets = name_glob

    out: list[PlacedInstance] = []
    while not it.at_end():
        raw = it.inst_cell()
        if pat is not None and not pat.fullmatch(raw.name):
            it.next()
            continue

        full = it.trans() * it.inst_trans()  # target cell -> die frame, dbu
        centre = full * raw.bbox().center()
        origin = full * kdb.Point(0, 0)  # the placement point the netlist records

        ports: dict[str, tuple[float, float, float]] = {}
        if with_ports:
            dtrans = kdb.DCplxTrans(full, dbu)
            for port in die.kcl[raw.cell_index()].ports:
                moved = port.copy(dtrans)
                # dcplx_trans.disp is um regardless of gdsfactory version;
                # Port.x has been dbu in some, so it is not safe to read here.
                disp = moved.dcplx_trans.disp
                ports[port.name] = (disp.x, disp.y, float(moved.orientation) % 360.0)

        match = _CELL_SPLIT.match(raw.name)
        out.append(
            PlacedInstance(
                cell=raw.name,
                kind=match.group(1) if match else raw.name,
                number=match.group(2) if match else "",
                x=centre.x * dbu,
                y=centre.y * dbu,
                origin=(origin.x * dbu, origin.y * dbu),
                ports=ports,
            )
        )
        it.next()
    return out


# --------------------------------------------------------------------------- #
# PAD_ID numbering
# --------------------------------------------------------------------------- #


def _cluster(values: list[float], tol: float) -> tuple[list[int], list[float]]:
    """Group 1D values whose sorted neighbours are within ``tol``.

    Single linkage on the sorted sequence: a gap wider than ``tol`` starts a new
    cluster. Used for pad rows and columns, and for the rows of a DC zone.

    Returns:
        ``(label per input value, cluster centres)``, clusters ascending.
    """
    order = sorted(range(len(values)), key=lambda i: values[i])
    labels = [0] * len(values)
    centres: list[float] = []
    bucket: list[int] = []
    for idx in order:
        if bucket and values[idx] - values[bucket[-1]] > tol:
            centres.append(sum(values[j] for j in bucket) / len(bucket))
            for j in bucket:
                labels[j] = len(centres) - 1
            bucket = []
        bucket.append(idx)
    if bucket:
        centres.append(sum(values[j] for j in bucket) / len(bucket))
        for j in bucket:
            labels[j] = len(centres) - 1
    return labels, centres


def assign_pad_ids(pads: list[Pad], *, tol: float = 1.0) -> list[Pad]:
    """Number the pads ``flipchip_pad1..N`` in reading order.

    Reading order means the topmost row first and, within a row, left to right.

    The lattice is a checkerboard, so a row holds only every other column; the
    numbering is *dense over pads that exist* -- it counts pads, not lattice
    sites -- so a keepout hole shifts every later number rather than leaving a
    gap. That is what was specified; note the consequence that PAD_IDs are not
    stable across a floorplan change.

    Args:
        pads: pads with absolute centres, any order.
        tol: um. Two pads share a row/column if their centres are within this.
            Must be below the smallest true row pitch and above placement jitter.

    Returns:
        A new list, ordered by ``PAD_ID``, with ``pad_id``/``row``/``col`` set.
    """
    if not pads:
        return []
    row_lbl, row_centres = _cluster([p.y for p in pads], tol)
    col_lbl, _ = _cluster([p.x for p in pads], tol)
    n_rows = len(row_centres)

    ordered = sorted(
        range(len(pads)),
        key=lambda i: (n_rows - 1 - row_lbl[i], col_lbl[i]),  # top row first
    )
    return [
        Pad(
            index=pads[i].index,
            x=pads[i].x,
            y=pads[i].y,
            pad_id=f"flipchip_pad{n + 1}",
            row=n_rows - 1 - row_lbl[i],
            col=col_lbl[i],
        )
        for n, i in enumerate(ordered)
    ]


# --------------------------------------------------------------------------- #
# shared context
# --------------------------------------------------------------------------- #


class PadMapContext:
    """Everything the naming rules share: pads, PAD_IDs, and the net graph.

    Built once per die.  The net extraction is the expensive part and the reason
    this is a class rather than a bag of functions -- every rule needs it and
    none of them may rebuild it.

    Note on lifetimes: the ``Region``s here are hierarchical and stay bound to
    the layout and to the ``LayoutToNetlist``.  Keeping the context alive keeps
    them valid; letting it go and holding a bare ``Region`` reads as empty.
    """

    def __init__(
        self,
        die: Any,
        *,
        pad_glob: str = "*flipchip_pad*",
        pad_regex: str | None = None,
        layers: LayerStack = LayerStack(),
        pad_tol: float = 1.0,
        die_bbox: tuple[float, float, float, float] | None = None,
    ) -> None:
        """Find the pads, number them, and extract the nets. Once per die.

        Args:
            die: the top-level gdsfactory ``Component``.
            pad_glob: anchored KLayout glob for the pad cell, pushed into the
                instance iterator. If this matches nothing, ``ctx.pads`` is
                empty and every rule silently finds nothing -- check it first.
            pad_regex: optional exact ``re.fullmatch`` filter on top of the glob.
            layers: the metal/via stack to extract over.
            pad_tol: um. Two pads share a row or column if their centres are
                within this; it sets the ``PAD_ID`` numbering.
            die_bbox: explicit die outline in um. Defaults to the top cell's
                bounding box, which is only used for coarse questions -- naming
                never depends on it.
        """
        self.die = die
        self.layers = layers
        self.layout = die.kcl.layout
        self.dbu = die.kcl.dbu
        self.top = die.kdb_cell

        raw_pads = [
            Pad(index=i, x=inst.x, y=inst.y)
            for i, inst in enumerate(
                find_instances(die, pad_glob, name_regex=pad_regex, with_ports=False)
            )
        ]
        self.pads = assign_pad_ids(raw_pads, tol=pad_tol)
        self.pad_by_index = {p.index: p for p in self.pads}

        box = self.top.dbbox() if die_bbox is None else kdb.DBox(*die_bbox)
        self.die_bbox = box
        self.split_x = 0.5 * (box.left + box.right)

        self._role_cache: dict[tuple[Any, ...], list[Any]] = {}
        self._build_nets()
        self._build_pad_lookup()

    # -- net extraction ---------------------------------------------------- #

    def _li(self, spec: tuple[int, int]) -> int:
        """Layer index in the source layout for a ``(layer, datatype)`` pair."""
        return self.layout.layer(spec[0], spec[1])

    def _build_nets(self) -> None:
        """Extract nets over MT1-Via1-MT2-Via2-MT3, on a flat copy of the stack.

        The flattening is a correctness requirement, not an optimisation.  On a
        hierarchical die ``probe_net`` returns the net *of the subcircuit* the
        point falls in, and ``shapes_of_net`` reports that net's geometry in the
        subcircuit's own coordinate space -- so two instances of one block return
        the same ``Net`` object with the same shape coordinates, and every copy
        of a block resolves to the first copy's pads.  Telling them apart would
        mean carrying ``sc_path_out`` from every probe and composing subcircuit
        transforms through every lookup.

        Copying the five stack layers flat into a scratch layout removes the
        problem at the root: one circuit, so a net is globally unique and its
        shapes are already in the die frame.  Only the metal and via layers are
        copied; the optical layers, which are the bulk of the die, are untouched.

        ``connect(a)`` makes a layer internally connected; ``connect(a, b)``
        joins two layers.  Only physically stacked pairs are joined, so MT1 and
        MT3 connect solely through MT2.
        """
        L = self.layers
        specs = (
            ("m1", L.m1),
            ("via1", L.via1),
            ("m2", L.m2),
            ("via2", L.via2),
            ("m3", L.m3),
        )

        # kept as an attribute: the extracted regions stay bound to this layout,
        # and if it is collected they read as empty.
        self._flat = kdb.Layout()
        self._flat.dbu = self.dbu
        flat_top = self._flat.create_cell("PAD_MAPPING_FLAT")
        for _, spec in specs:
            flat_top.shapes(self._flat.layer(spec[0], spec[1])).insert(
                kdb.Region(self.top.begin_shapes_rec(self._li(spec)))
            )

        l2n = kdb.LayoutToNetlist(kdb.RecursiveShapeIterator(self._flat, flat_top, []))
        self.l = {
            # the layer-index overload: the RecursiveShapeIterator variant was
            # removed in KLayout 0.30, and the l2n already carries its scope.
            name: l2n.make_polygon_layer(self._flat.layer(spec[0], spec[1]), name)
            for name, spec in specs
        }
        for layer in self.l.values():
            l2n.connect(layer)
        l2n.connect(self.l["m1"], self.l["via1"])
        l2n.connect(self.l["via1"], self.l["m2"])
        l2n.connect(self.l["m2"], self.l["via2"])
        l2n.connect(self.l["via2"], self.l["m3"])
        l2n.extract_netlist()
        self.l2n = l2n

    # -- pad geometry lookup ------------------------------------------------ #

    def _build_pad_lookup(self) -> None:
        """One MT3 marker box per pad, plus a centre -> pad index map.

        Pads are found back from net geometry by intersecting against these
        markers and mapping the survivor's centre to a pad index, which is exact
        because there is exactly one marker per pad and the markers are disjoint.
        """
        self._pad_markers = kdb.Region()
        self._pad_at: dict[tuple[int, int], int] = {}
        half = max(1, round(0.5 / self.dbu))  # a 1 um probe, well inside any pad
        for pad in self.pads:
            ix, iy = round(pad.x / self.dbu), round(pad.y / self.dbu)
            self._pad_markers.insert(
                kdb.Box(ix - half, iy - half, ix + half, iy + half)
            )
            self._pad_at[(ix, iy)] = pad.index

    def probe_live(
        self,
        points: list[tuple[float, float]],
        halfwidth: float = 1.0,
        layer: str = "m3",
    ):
        """Which of ``points`` have metal under them on ``layer``.

        Batched: one region of all probe boxes intersected against the layer in a
        single C++ pass, rather than a Python loop of per-point tests.
        Correspondence is recovered by mapping each surviving box's centre back
        to its index, which is exact as long as no two probe points coincide --
        duplicates are collapsed and reported for every index that produced them.

        Args:
            points: probe locations in um, die frame.
            halfwidth: um. Each probe is a box of this half-width rather than a
                bare point, which would miss a route whose edge is grid-snapped
                a fraction off the nominal coordinate.
            layer: stack layer to test against -- ``"m3"`` for PUC terminals and
                pads, ``"m2"`` for PDs, ``"m1"`` for thermistors.

        Returns:
            ``set`` of indices into ``points`` that have metal under them.
        """
        half = round(halfwidth / self.dbu)
        probes = kdb.Region()
        at: dict[tuple[int, int], list[int]] = {}
        for i, (x, y) in enumerate(points):
            ix, iy = round(x / self.dbu), round(y / self.dbu)
            at.setdefault((ix, iy), []).append(i)
            probes.insert(kdb.Box(ix - half, iy - half, ix + half, iy + half))
        live: set[int] = set()
        for poly in probes.interacting(self.l[layer]).each():
            c = poly.bbox().center()
            live.update(at.get((c.x, c.y), ()))
        return live

    def net_at(self, x: float, y: float, layer: str = "m3"):
        """The net touching ``(x, y)`` on ``layer``, or None.

        Terminals sit on different metals by component -- MT3 for PUCs, MT2 for
        PDs, MT1 for thermistors -- so the probe layer varies, even though the
        extraction spans the whole stack and the net that comes back is the same
        object whichever layer it was reached through.

        Args:
            x: probe x in um, die frame.
            y: probe y in um, die frame.
            layer: stack layer to probe on.

        Returns:
            The ``kdb.Net``, or None if there is no metal there.
        """
        return self.l2n.probe_net(
            self.l[layer], kdb.Point(round(x / self.dbu), round(y / self.dbu))
        )

    def pads_of_net(self, net) -> list[int]:
        """Pad indices whose MT3 geometry the net reaches.

        A pad is claimed on geometric overlap, so a route that stops short of
        the pad centre but still lands on the pad counts -- the case where the
        component ends over the pad rather than routing into it.
        """
        if net is None:
            return []
        # The layer must be the extracted Region layer, not a layer index:
        # polygons_of_net with an index silently returns nothing, because the
        # extraction identifies its layers by those Region objects.
        region = self.l2n.shapes_of_net(net, self.l["m3"], True)
        if region is None:
            return []
        out: list[int] = []
        for poly in self._pad_markers.interacting(region).each():
            c = poly.bbox().center()
            idx = self._pad_at.get((c.x, c.y))
            if idx is not None:
                out.append(idx)
        return sorted(out)

    def polarization(self, x: float) -> str:
        """``"TE"`` left of the die bbox midline, ``"TM"`` right of it.

        Not used for naming, and not reliable for it: the two halves overlap in
        x, so this misclassifies every PUC in the overlap. Component names take
        their polarization from :func:`puc_polarizations`, which pairs each PUC
        cell's two instances instead. This remains for coarse questions about a
        coordinate -- which side of the die something is roughly on.
        """
        return "TE" if x < self.split_x else "TM"


# --------------------------------------------------------------------------- #
# the probe rule
# --------------------------------------------------------------------------- #


def port_probe_points(
    port: tuple[float, float, float],
    centre: tuple[float, float],
    offset: float = 5.5,
) -> tuple[tuple[float, float], tuple[float, float]]:
    """The two places a route may attach to one electrical port.

    Rotation-free by construction: the offset is ``offset`` backwards along the
    port normal plus ``offset`` laterally away from the component centre, so it
    is derived from the port's own orientation rather than from a table indexed
    by instance rotation.  Reproduces the measured 0 deg and 270 deg tables.

    Args:
        port: ``(x, y, orientation degrees)`` in the die frame, the orientation
            pointing out of the component.
        centre: the component's centre ``(x, y)``, which fixes what "laterally
            away" means.
        offset: um. Exactly 5.5 on this die.

    Returns:
        ``(at_port, at_offset)``, both ``(x, y)`` in um.

    Raises:
        ValueError: if the port sits on the centre line transverse to its own
            normal, leaving "away from the centre" undefined. Such a port cannot
            be probed by this rule and the caller must flag it rather than guess.
    """
    px, py, angle = port
    rad = math.radians(angle)
    nx, ny = math.cos(rad), math.sin(rad)
    tx, ty = -ny, nx  # normal rotated +90 deg

    lateral = (px - centre[0]) * tx + (py - centre[1]) * ty
    if abs(lateral) < 1e-9:
        raise ValueError(
            f"port at ({px}, {py}) is transversely centred on the component, so "
            "'laterally away from the centre' is undefined"
        )
    sign = 1.0 if lateral > 0 else -1.0
    return (
        (px, py),
        (px - offset * nx + offset * sign * tx, py - offset * ny + offset * sign * ty),
    )


# --------------------------------------------------------------------------- #
# polarization
# --------------------------------------------------------------------------- #


def puc_polarizations(
    ctx: PadMapContext,
    *,
    puc_glob: str = "puc*",
    puc_regex: str = r"puc(mua)?\d+",
    strategy: str = "pairs",
    split_x: float | None = None,
    cache: bool = True,
) -> tuple[dict[tuple[str, int, int], str], list[str]]:
    """Resolve TE/TM per PUC *instance*.

    The die's two halves are not separated by its geometric midline -- the MUA
    array starts slightly before it and the mesh ends slightly after, and the
    first TM column sits at the same x as the last TE column.  So no vertical
    line can classify every PUC, and splitting on one mislabels the PUCs and PDs
    either side of the overlap.

    ``"pairs"`` sidesteps the boundary entirely.  Every PUC cell is instanced
    exactly twice, once per half, so for each cell name the instance with the
    lower x is TE and the other TM.  The comparison is between two instances of
    *the same cell*, which is why an overlap in absolute x cannot break it: the
    two halves are translated copies, so a cell's two instances always differ by
    the block offset regardless of how the columns interleave.

    The block offset is checked for consistency across every cell as a
    by-product: a pair whose separation differs from the rest is reported, which
    is the cheapest available detector for a misplaced PUC.

    Args:
        ctx: shared context.
        puc_glob: glob for the PUC cells.
        puc_regex: exact filter on top of it.
        strategy: ``"pairs"`` (default, recommended) or ``"split"``, the old
            behaviour of thresholding on x. ``"split"`` is kept only as an
            escape hatch and is known to mislabel across the overlap.
        split_x: boundary for ``"split"``; defaults to the die bbox midpoint.
        cache: reuse a previous result.

    Returns:
        ``({instance key: "TE"|"TM"}, faults)``. A PUC whose cell name does not
        appear exactly twice is absent from the map and described in ``faults``.
    """
    key = ("polarization", puc_glob, puc_regex, strategy, split_x)
    if cache and key in ctx._role_cache:
        return ctx._role_cache[key]

    instances = find_instances(
        ctx.die, puc_glob, name_regex=puc_regex, with_ports=False
    )
    out: dict[tuple[str, int, int], str] = {}
    faults: list[str] = []

    if strategy == "split":
        boundary = ctx.split_x if split_x is None else split_x
        for inst in instances:
            out[inst.key] = "TE" if inst.x < boundary else "TM"
        ctx._role_cache[key] = (out, faults)
        return out, faults

    if strategy != "pairs":
        raise ValueError(f"unknown strategy {strategy!r}; use 'pairs' or 'split'")

    by_cell: dict[str, list[PlacedInstance]] = {}
    for inst in instances:
        by_cell.setdefault(inst.cell, []).append(inst)

    offsets: list[tuple[str, float]] = []
    for cell, group in sorted(by_cell.items()):
        if len(group) != 2:
            faults.append(
                f"{cell} is instanced {len(group)} times; polarization is decided "
                "by pairing the two halves, so exactly 2 are required"
            )
            continue
        lo, hi = sorted(group, key=lambda i: i.x)
        if abs(hi.x - lo.x) < 1e-6:
            faults.append(f"{cell}: both instances share an x, so TE/TM is undecidable")
            continue
        out[lo.key], out[hi.key] = "TE", "TM"
        offsets.append((cell, hi.x - lo.x))

    if offsets:
        values = sorted(v for _, v in offsets)
        median = values[len(values) // 2]
        for cell, value in offsets:
            if abs(value - median) > 1.0:
                faults.append(
                    f"{cell}: its two instances are {value:.3f} um apart, but the "
                    f"block offset is {median:.3f} um -- one of them is misplaced"
                )

    ctx._role_cache[key] = (out, faults)
    return out, faults


def block_offset(ctx: PadMapContext, **kwargs) -> float | None:
    """The x distance between the TE and TM halves, from the PUC pairing.

    Worth printing on a real run: it is a single number that should match the
    floorplan, and a wrong one means the pairing has gone astray.

    Args:
        ctx: shared context.
        **kwargs: passed through to :func:`puc_polarizations`.

    Returns:
        The median offset in um, or None if no cell paired.
    """
    pol, _ = puc_polarizations(ctx, **kwargs)
    te = {k[0]: k[1] for k, v in pol.items() if v == "TE"}
    tm = {k[0]: k[1] for k, v in pol.items() if v == "TM"}
    deltas = sorted((tm[c] - te[c]) / 1000 for c in te.keys() & tm.keys())
    return deltas[len(deltas) // 2] if deltas else None


# --------------------------------------------------------------------------- #
# rules: shared port-role pass
# --------------------------------------------------------------------------- #

_ARM = {"e1": "bot", "e4": "bot", "e2": "top", "e3": "top"}
GROUND_GROUP_SIZES = (2, 3)
"""PUC ground pads are joined in groups of two or three -- never one, never four."""
BIAS_GROUP_SIZES = (2,)
"""PD bias pads are joined strictly in pairs, unlike PUC grounds."""


@dataclass(frozen=True)
class PortRole:
    """What one electrical port of one component turned out to be wired to.

    ``role`` is one of:

    ``signal``       exactly one pad on the net.
    ``group``        a legal joined group (PUC ground, or PD bias pair).
    ``open``         no metal at any attachment point.
    ``dangling``     metal and a net, but the net reaches no pad.
    ``ambiguous``    two attachment points landed on different nets.
    ``overreaching`` more pads than a legal group can have.
    ``undefined``    the attachment offset cannot be derived for this port.

    The role says what the port *reaches*, not what it means, and the two rule
    families use it in opposite directions.  On a PUC either port of an arm may
    be the signal, so the role decides: a lone pad is the signal, a group is the
    ground.  On a PD and a thermistor the port name already fixes the meaning, so
    the role is checked against it instead -- a PD's ``e2`` that reaches three
    pads is an error, not a reclassification to ground.
    """

    role: str
    pads: tuple[int, ...] = ()
    probes: tuple[str, ...] = ()
    nets: tuple[str, ...] = ()
    note: str = ""


@dataclass(frozen=True)
class InstancePorts:
    """One component instance and the resolved role of each electrical port."""

    instance: PlacedInstance
    roles: dict[str, PortRole]

    @property
    def puc(self) -> PlacedInstance:
        """Alias kept so PUC-side code reads naturally."""
        return self.instance

    def with_role(self, role: str) -> list[str]:
        """Port names having ``role``, in sorted order."""
        return [n for n in sorted(self.roles) if self.roles[n].role == role]


PucPorts = InstancePorts  # backwards-compatible name


def puc_probe_candidates(
    name: str,
    port: tuple[float, float, float],
    centre: tuple[float, float],
    offset: float = 5.5,
) -> list[tuple[float, float, str]]:
    """Attachment points for one PUC electrical port: the port, and the offset.

    See :func:`port_probe_points` for the rotation-free form of the offset.

    Args:
        name: port name. Unused here -- all four PUC ports behave alike -- but
            present because :func:`port_roles` calls every candidate function
            with the same signature.
        port: ``(x, y, orientation degrees)`` in the die frame.
        centre: the component centre, which fixes "laterally away".
        offset: um, the diagonal offset. Exactly 5.5 here.

    Returns:
        ``[(x, y, label), ...]``, the label naming which candidate it is.
    """
    at_port, at_offset = port_probe_points(port, centre, offset)
    return [(*at_port, "port"), (*at_offset, "offset")]


def pd_probe_candidates(
    name: str,
    port: tuple[float, float, float],
    centre: tuple[float, float],
    offset: float = 15.8,
    offset_ports: tuple[str, ...] = ("e1",),
    offset_orientations: tuple[float, ...] = (90.0,),
) -> list[tuple[float, float, str]]:
    """Attachment points for one PD electrical port.

    Only ``e1`` on a 90 degree PD has a second possibility, 15.8 um *backwards
    along the port normal*.  Expressed that way rather than as a literal
    ``y - 15.8`` so that it cannot be misapplied to another orientation: at 90
    degrees the normal is +y, which reproduces the measured value exactly, and
    the same expression stays correct if a further variant ever appears.

    Args:
        name: port name; only ``offset_ports`` get a second candidate.
        port: ``(x, y, orientation degrees)`` in the die frame.
        centre: the component centre. Unused -- the PD offset has no lateral
            term -- but part of the shared candidate-function signature.
        offset: um backwards along the normal. Exactly 15.8 here.
        offset_ports: which ports may attach off-port.
        offset_orientations: the orientations at which they may.

    Returns:
        ``[(x, y, label), ...]``: one entry, or two for ``e1`` at 90 degrees.
    """
    px, py, angle = port
    out = [(px, py, "port")]
    if name in offset_ports and any(
        abs((angle - a) % 360.0) < 1e-6 for a in offset_orientations
    ):
        rad = math.radians(angle)
        out.append((px - offset * math.cos(rad), py - offset * math.sin(rad), "offset"))
    return out


def port_roles(
    ctx: PadMapContext,
    *,
    glob: str,
    regex: str,
    ports: tuple[str, ...],
    probe_layer: str = "m3",
    candidates_fn=puc_probe_candidates,
    group_sizes: tuple[int, ...] = GROUND_GROUP_SIZES,
    probe_halfwidth: float = 1.0,
    cache_key: Any = None,
    cache: bool = True,
) -> list[InstancePorts]:
    """Probe every electrical port of every matching instance and classify it.

    One batched pass for the whole die: all attachment points of all instances
    are tested against ``probe_layer`` in a single call, then each live point is
    resolved to a net and thence to the pads that net reaches.  The pad count
    gives the role -- one pad is ``signal``, a legal group size is ``group``.

    Shared by every rule that needs it, and cached on the context, because
    running it twice would not only double the cost but allow two rules to
    disagree about the same port.

    Args:
        ctx: shared context.
        glob: anchored KLayout glob for the component cells, pushed into the
            iterator so non-matching cells are never visited.
        regex: exact ``re.fullmatch`` filter on top of the glob.
        ports: the electrical port names to probe; others on the cell are
            ignored.
        probe_layer: stack layer the terminals sit on -- ``"m3"`` for PUCs,
            ``"m2"`` for PDs.
        candidates_fn: ``(port name, port, centre) -> [(x, y, label)]``, the
            places a route may attach to that port.
        group_sizes: legal joined-group sizes; more pads than the maximum is
            ``overreaching``.
        probe_halfwidth: um. A bare point test fails on a grid-snapped route
            edge, so each probe is a box of this half-width.
        cache_key: extra key material, so two configurations of the same cells
            do not collide in the cache.
        cache: reuse a previous result for the same arguments.

    Returns:
        One :class:`InstancePorts` per instance, in discovery order.
    """
    key = (glob, regex, ports, probe_layer, group_sizes, probe_halfwidth, cache_key)
    if cache and key in ctx._role_cache:
        return ctx._role_cache[key]

    found = find_instances(ctx.die, glob, name_regex=regex)

    points: list[tuple[float, float]] = []
    owner: list[tuple[int, str, str]] = []
    undefined: set[tuple[int, str]] = set()
    for i, inst in enumerate(found):
        for name, port in inst.ports.items():
            if name not in ports:
                continue
            try:
                candidates = candidates_fn(name, port, (inst.x, inst.y))
            except ValueError:
                undefined.add((i, name))
                continue
            for x, y, label in candidates:
                points.append((x, y))
                owner.append((i, name, label))

    live = ctx.probe_live(points, probe_halfwidth, layer=probe_layer)

    hits: dict[int, dict[str, dict[str, Any]]] = {i: {} for i in range(len(found))}
    for k in sorted(live):
        i, name, label = owner[k]
        net = ctx.net_at(*points[k], layer=probe_layer)
        if net is None:  # metal present but not part of any extracted net
            continue
        rec = hits[i].setdefault(name, {"nets": {}, "probes": []})
        rec["probes"].append(label)
        rec["nets"][net.expanded_name()] = tuple(ctx.pads_of_net(net))

    out: list[InstancePorts] = []
    for i, inst in enumerate(found):
        roles: dict[str, PortRole] = {}
        for name in ports:
            if (i, name) in undefined:
                roles[name] = PortRole(
                    "undefined", note="attachment offset undefined for this port"
                )
                continue
            rec = hits[i].get(name)
            if rec is None:
                roles[name] = PortRole(
                    "open", note=f"no {probe_layer.upper()} at any probe point"
                )
                continue
            probes = tuple(rec["probes"])
            if len(rec["nets"]) > 1:
                roles[name] = PortRole(
                    "ambiguous",
                    pads=tuple(sorted({p for v in rec["nets"].values() for p in v})),
                    probes=probes,
                    nets=tuple(sorted(rec["nets"])),
                    note=f"probes hit different nets {sorted(rec['nets'])}",
                )
                continue
            net_name, pads = next(iter(rec["nets"].items()))
            if not pads:
                role = "dangling"
            elif len(pads) == 1:
                role = "signal"
            elif len(pads) in group_sizes:
                role = "group"
            else:
                role = "overreaching"
            roles[name] = PortRole(
                role,
                pads=pads,
                probes=probes,
                nets=(net_name,),
                note=f"{role} via {'+'.join(probes)}, pads={list(pads)}",
            )
        out.append(InstancePorts(inst, roles))

    if cache:
        ctx._role_cache[key] = out
    return out


def puc_port_roles(
    ctx: PadMapContext,
    *,
    puc_glob: str = "puc*",
    puc_regex: str = r"puc(mua)?\d+",
    probe_offset: float = 5.5,
    probe_halfwidth: float = 1.0,
    cache: bool = True,
) -> list[InstancePorts]:
    """:func:`port_roles` for PUCs: MT3, ``e1..e4``, the diagonal offset rule.

    Args:
        ctx: shared context.
        puc_glob: anchored glob for the PUC cells.
        puc_regex: exact filter on top of it; the default admits ``puc<n>`` and
            ``pucmua<n>`` only.
        probe_offset: um, the diagonal attachment offset. Exactly 5.5 here.
        probe_halfwidth: um probe box half-width.
        cache: reuse a previous result for the same arguments.

    Returns:
        One :class:`InstancePorts` per PUC instance, in discovery order.
    """
    return port_roles(
        ctx,
        glob=puc_glob,
        regex=puc_regex,
        ports=("e1", "e2", "e3", "e4"),
        probe_layer="m3",
        candidates_fn=lambda n, p, c: puc_probe_candidates(n, p, c, probe_offset),
        group_sizes=GROUND_GROUP_SIZES,
        probe_halfwidth=probe_halfwidth,
        cache_key=("puc", probe_offset),
        cache=cache,
    )


def pd_port_roles(
    ctx: PadMapContext,
    *,
    pd_glob: str = "lateral_pd_puc*",
    pd_regex: str = r"lateral_pd_puc(mua)?\d+",
    probe_offset: float = 15.8,
    probe_halfwidth: float = 1.0,
    cache: bool = True,
) -> list[InstancePorts]:
    """:func:`port_roles` for PDs: MT2, ``e1``/``e2``, the 90 degree offset.

    ``e1`` is the bias port and ``e2`` the signal, fixed by name.

    Args:
        ctx: shared context.
        pd_glob: anchored glob for the PD cells.
        pd_regex: exact filter on top of it; the default admits
            ``lateral_pd_puc<n>`` and ``lateral_pd_pucmua<n>``.
        probe_offset: um. Applies to ``e1`` at 90 degrees only, where a route may
            attach 15.8 um backwards along the port normal.
        probe_halfwidth: um probe box half-width.
        cache: reuse a previous result for the same arguments.

    Returns:
        One :class:`InstancePorts` per PD instance, in discovery order.
    """
    return port_roles(
        ctx,
        glob=pd_glob,
        regex=pd_regex,
        ports=("e1", "e2"),
        probe_layer="m2",
        candidates_fn=lambda n, p, c: pd_probe_candidates(n, p, c, probe_offset),
        group_sizes=BIAS_GROUP_SIZES,
        probe_halfwidth=probe_halfwidth,
        cache_key=("pd", probe_offset),
        cache=cache,
    )


def _port_report(pp: InstancePorts) -> dict[str, Any]:
    """The common part of a per-instance diagnostic record."""
    return {
        "cell": pp.instance.cell,
        "kind": pp.instance.kind,
        "number": pp.instance.number,
        "x": pp.instance.x,
        "y": pp.instance.y,
        "ports": {n: r.note for n, r in pp.roles.items()},
    }


# --------------------------------------------------------------------------- #
# rule: PUC signal pads
# --------------------------------------------------------------------------- #

PIC_NAME_ROW = re.compile(
    r"(PUC\d+_(top|bot)(_MUA)?|PD\d+(_(top|bot))?_(MESH|MUA))_(TE|TM)$"
)
"""Matches the pad names that carry a PIC name: PUC and PD *signal* rows.

Ground, bias and chain pads are excluded because they are shared between
components -- a joined ground group has no single owning instance, so there is no
one netlist path to report.
"""

SIGNAL_KIND_FIELD = {"puc": "", "pucmua": "MUA"}
"""Extra name field per PUC kind: a mesh PUC has none, a MUA PUC is tagged.

Kept as a table rather than an ``if`` so that a new PUC variant is a one-line
addition here, and so an unrecognised kind is a ``KeyError`` at the point of
naming rather than a silently untagged name.
"""


def puc_signal_name(kind: str, number: str, arm: str, polarization: str) -> str:
    """The signal pad name for one PUC arm.

    ``puc<n>``    -> ``PUC<n>_<top|bot>_<TE|TM>``
    ``pucmua<n>`` -> ``PUC<n>_<top|bot>_MUA_<TE|TM>``

    Args:
        kind: leading alphabetic part of the cell name, ``"puc"`` or ``"pucmua"``.
        number: trailing digits of the cell name.
        arm: ``"top"`` or ``"bot"``.
        polarization: ``"TE"`` or ``"TM"``.

    Returns:
        The pad name.

    Raises:
        KeyError: for a PUC kind with no entry in :data:`SIGNAL_KIND_FIELD`.
    """
    fields = ["PUC" + number, arm]
    if SIGNAL_KIND_FIELD[kind]:
        fields.append(SIGNAL_KIND_FIELD[kind])
    fields.append(polarization)
    return "_".join(fields)


def assign_puc_signals(
    ctx: PadMapContext,
    *,
    puc_glob: str = "puc*",
    puc_regex: str = r"puc(mua)?\d+",
    probe_offset: float = 5.5,
    probe_halfwidth: float = 1.0,
    ground_strategy: Literal["joined_island"] = "joined_island",
    polarization_strategy: str = "pairs",
) -> tuple[dict[int, Assignment], list[dict[str, Any]]]:
    """Name the signal pad of each PUC arm.

    ``PUC<n>_<top|bot>_<TE|TM>`` for a mesh PUC, and
    ``PUC<n>_<top|bot>_MUA_<TE|TM>`` for a ``pucmua`` -- see
    :func:`puc_signal_name`.

    Each arm (``e1``/``e4`` top, ``e2``/``e3`` bottom) must have exactly one port
    reaching a lone pad; that pad is the signal.  The other port of the arm goes
    to a joined ground group, which :func:`assign_puc_grounds` names.

    Args:
        ctx: shared context.
        puc_glob: see :func:`puc_port_roles`.
        puc_regex: see :func:`puc_port_roles`.
        probe_offset: see :func:`puc_port_roles`.
        probe_halfwidth: see :func:`puc_port_roles`.
        ground_strategy: how signal is told from ground. ``"joined_island"``
            uses the pad count on the net and needs no floorplan input; kept as a
            parameter because an explicit ground-region list is a drop-in
            replacement.
        polarization_strategy: ``"pairs"`` (default) resolves TE/TM by pairing
            each PUC cell's two instances -- see :func:`puc_polarizations`.
            ``"split"`` thresholds on x instead and is known to mislabel where
            the halves overlap; it exists only as an escape hatch.

    Returns:
        ``(assignments, diagnostics)``. A PUC whose polarization cannot be
        resolved yields ``ERROR`` rather than a name with a guessed suffix.

    Raises:
        ValueError: for an unknown ``ground_strategy``.
    """
    if ground_strategy != "joined_island":
        raise ValueError(f"unknown ground_strategy {ground_strategy!r}")

    per_puc = puc_port_roles(
        ctx,
        puc_glob=puc_glob,
        puc_regex=puc_regex,
        probe_offset=probe_offset,
        probe_halfwidth=probe_halfwidth,
    )
    polarization, pol_faults = puc_polarizations(
        ctx, puc_glob=puc_glob, puc_regex=puc_regex, strategy=polarization_strategy
    )

    assignments: dict[int, Assignment] = {}
    diagnostics: list[dict[str, Any]] = []

    for pp in per_puc:
        report = _port_report(pp)
        pol = polarization.get(pp.puc.key)
        if pol is None:
            why = (
                f"{pp.puc.cell}: polarization unresolved, so the name would be "
                "wrong; " + ("; ".join(pol_faults[:2]) or "no pairing found")
            )
            report["top_signal"] = report["bot_signal"] = "ERROR"
            report["polarization_reason"] = why
            for pad_idx in sorted({p for r in pp.roles.values() for p in r.pads}):
                assignments[pad_idx] = Assignment("ERROR", 0, "puc_signal", why)
            diagnostics.append(report)
            continue
        report["polarization"] = pol

        for arm in ("top", "bot"):
            names = [n for n in ("e1", "e2", "e3", "e4") if _ARM[n] == arm]
            signals = [n for n in names if pp.roles[n].role == "signal"]

            if len(signals) == 1:
                pad_idx = pp.roles[signals[0]].pads[0]
                name = puc_signal_name(pp.puc.kind, pp.puc.number, arm, pol)
                held = assignments.get(pad_idx)
                if held is not None and held.name != name:
                    assignments[pad_idx] = Assignment(
                        "ERROR",
                        0,
                        "puc_signal",
                        f"claimed by both {held.name} and {name}",
                    )
                else:
                    assignments[pad_idx] = Assignment(
                        name,
                        1,
                        "puc_signal",
                        f"{pp.puc.cell}.{signals[0]} -> lone pad on its net",
                        component=pp.instance.origin_key,
                    )
                report[f"{arm}_signal"] = name
            else:
                why = (
                    f"{pp.puc.cell} {arm} arm has {len(signals)} signal candidates "
                    f"among {names}: "
                    + ", ".join(f"{n}={pp.roles[n].role}" for n in names)
                )
                report[f"{arm}_signal"] = "ERROR"
                report[f"{arm}_reason"] = why
                for pad_idx in sorted({p for n in names for p in pp.roles[n].pads}):
                    assignments[pad_idx] = Assignment("ERROR", 0, "puc_signal", why)

        diagnostics.append(report)

    return assignments, diagnostics


# --------------------------------------------------------------------------- #
# rule: PUC ground pads
# --------------------------------------------------------------------------- #

GND_NAME = {"puc": "GND_MESH", "pucmua": "GND_MUA"}
"""MESH or MUA is decided by the PUC's component name, never by position."""


def _group_geometry(
    ctx: PadMapContext, pads: tuple[int, ...]
) -> tuple[str | None, float, str]:
    """Axis, centre-to-centre span and a note for a candidate ground group.

    Returns ``(axis, span, note)`` with ``axis`` ``"row"`` (pads differ in x),
    ``"column"`` (differ in y) or ``None`` if the pads are not collinear.
    """
    xs = [ctx.pad_by_index[i].x for i in pads]
    ys = [ctx.pad_by_index[i].y for i in pads]
    dx, dy = max(xs) - min(xs), max(ys) - min(ys)
    if dy <= 1e-6 < dx:
        return "row", dx, ""
    if dx <= 1e-6 < dy:
        return "column", dy, ""
    return None, 0.0, f"pads not collinear (dx={dx:.3f}, dy={dy:.3f} um)"


def _neck_points(
    ctx: PadMapContext, pads: tuple[int, ...], axis: str, neck_offset: float
) -> list[tuple[float, float]]:
    """Probe points either side of the join, between each consecutive pad pair.

    A solid ground join is as wide as the pads it covers (65.656 um), whereas a
    continuity-chain bar is 20 um.  Sampling ``neck_offset`` transversely from
    the join centreline therefore hits metal for a ground join and empty space
    for a chain bar -- which matters because the two have *identical* bounding
    boxes: 65.656 + 180 = 245.656 either way, so no bbox test can separate them.

    Both sides are probed, and both must hit, so that a stray route passing on
    one side cannot fake a solid join.
    """
    keyed = sorted(
        pads,
        key=lambda i: ctx.pad_by_index[i].x if axis == "row" else ctx.pad_by_index[i].y,
    )
    points: list[tuple[float, float]] = []
    for a, b in zip(keyed, keyed[1:], strict=False):
        pa, pb = ctx.pad_by_index[a], ctx.pad_by_index[b]
        mx, my = 0.5 * (pa.x + pb.x), 0.5 * (pa.y + pb.y)
        if axis == "row":
            points += [(mx, my + neck_offset), (mx, my - neck_offset)]
        else:
            points += [(mx + neck_offset, my), (mx - neck_offset, my)]
    return points


def assign_puc_grounds(
    ctx: PadMapContext,
    *,
    puc_glob: str = "puc*",
    puc_regex: str = r"puc(mua)?\d+",
    probe_offset: float = 5.5,
    probe_halfwidth: float = 1.0,
    pad_diameter: float = 65.656,
    join_lengths: tuple[float, float] = (245.656, 425.656),
    neck_offset: float = 25.0,
    tolerance: float = 0.05,
    verify_neck: bool = True,
) -> tuple[dict[int, Assignment], list[dict[str, Any]]]:
    """Name every PUC ground pad ``GND_MESH`` or ``GND_MUA``.

    Driven from the PUCs rather than from the geometry, because a joined island
    carries nothing that says MESH or MUA -- that comes from the component name
    of the PUC feeding it, which is only knowable by arriving from the PUC.

    Each PUC must have exactly two ground ports, one per arm, and both must reach
    the *same* joined group.  The group is then verified geometrically before any
    pad is named: two or three pads, collinear, spaced so that the covered extent
    matches a real join, and -- unless ``verify_neck`` is off -- a solid join
    rather than a 20 um chain bar.

    Args:
        ctx: shared context.
        puc_glob: see :func:`puc_port_roles`.
        puc_regex: see :func:`puc_port_roles`.
        probe_offset: see :func:`puc_port_roles`.
        probe_halfwidth: see :func:`puc_port_roles`.
        pad_diameter: um. Used with the pad span to reconstruct the join extent,
            which is what makes the dimension check independent of pad pitch.
        join_lengths: um, the measured join lengths for a 2- and a 3-pad group
            (245.656 and 425.656 here). The transverse dimension is
            ``pad_diameter`` and is not checked separately.
        neck_offset: um from the join centreline for the neck probe. Must sit
            between half a chain bar (10) and half a pad (32.828); 25 leaves
            margin on both sides.
        tolerance: um tolerance on the join length check.
        verify_neck: run the neck probe. Off skips one batched probe pass at the
            cost of not distinguishing a solid join from a chain bar.

    Returns:
        ``(assignments, diagnostics)``. Every pad of every verified group gets
        ``signal_ground = 0``; pads of a failed group get ``ERROR``.
    """
    per_puc = puc_port_roles(
        ctx,
        puc_glob=puc_glob,
        puc_regex=puc_regex,
        probe_offset=probe_offset,
        probe_halfwidth=probe_halfwidth,
    )

    # collect candidate groups first, so all neck probes go in one batched pass
    candidates: list[dict[str, Any]] = []
    for pp in per_puc:
        grounds = pp.with_role("group")
        arms = {_ARM[n] for n in grounds}
        pad_sets = {pp.roles[n].pads for n in grounds}
        fault = None
        if len(grounds) != 2 or arms != {"top", "bot"}:
            fault = (
                f"{pp.puc.cell} has {len(grounds)} ground ports {grounds} "
                f"(expected exactly one per arm): "
                + ", ".join(f"{n}={pp.roles[n].role}" for n in ("e1", "e2", "e3", "e4"))
            )
        elif len(pad_sets) != 1:
            fault = (
                f"{pp.puc.cell} ground ports reach different groups: "
                + " vs ".join(str(sorted(s)) for s in pad_sets)
            )
        pads = (
            next(iter(pad_sets))
            if len(pad_sets) == 1
            else tuple(sorted({p for n in grounds for p in pp.roles[n].pads}))
        )
        candidates.append({"pp": pp, "pads": pads, "fault": fault, "ports": grounds})

    # geometry checks
    probe_points: list[tuple[float, float]] = []
    for cand in candidates:
        pads = cand["pads"]
        if cand["fault"] is not None or not pads:
            continue
        if len(pads) not in GROUND_GROUP_SIZES:
            cand["fault"] = (
                f"ground group of {len(pads)} pads; only {GROUND_GROUP_SIZES} are valid"
            )
            continue
        axis, span, note = _group_geometry(ctx, pads)
        if axis is None:
            cand["fault"] = note
            continue
        expected = join_lengths[len(pads) - 2]
        if abs(span + pad_diameter - expected) > tolerance:
            cand["fault"] = (
                f"join extent {span + pad_diameter:.3f} um does not match the "
                f"{len(pads)}-pad join length {expected} um"
            )
            continue
        cand["axis"] = axis
        if verify_neck:
            points = _neck_points(ctx, pads, axis, neck_offset)
            cand["neck"] = range(len(probe_points), len(probe_points) + len(points))
            probe_points += points

    live = ctx.probe_live(probe_points, probe_halfwidth) if probe_points else set()

    assignments: dict[int, Assignment] = {}
    diagnostics: list[dict[str, Any]] = []

    for cand in candidates:
        pp: PucPorts = cand["pp"]
        pads: tuple[int, ...] = cand["pads"]
        report = _port_report(pp)
        report["ground_ports"] = cand["ports"]
        report["ground_pads"] = list(pads)

        if cand["fault"] is None and verify_neck and "neck" in cand:
            missing = [k for k in cand["neck"] if k not in live]
            if missing:
                cand["fault"] = (
                    f"no metal {neck_offset} um off the join centreline at "
                    f"{len(missing)} of {len(cand['neck'])} probe points: the pads "
                    "are bridged by something narrower than a ground join"
                )

        if cand["fault"] is not None:
            report["ground"] = "ERROR"
            report["ground_reason"] = cand["fault"]
            for pad_idx in pads:
                assignments[pad_idx] = Assignment(
                    "ERROR", 0, "puc_ground", cand["fault"]
                )
            diagnostics.append(report)
            continue

        name = GND_NAME.get(pp.puc.kind)
        if name is None:
            why = f"unknown PUC kind {pp.puc.kind!r}: cannot tell MESH from MUA"
            report["ground"] = "ERROR"
            report["ground_reason"] = why
            for pad_idx in pads:
                assignments[pad_idx] = Assignment("ERROR", 0, "puc_ground", why)
            diagnostics.append(report)
            continue

        report["ground"] = name
        for pad_idx in pads:
            held = assignments.get(pad_idx)
            if held is not None and held.name != name:
                why = (
                    f"group shared between a {pp.puc.kind} and something naming it "
                    f"{held.name}"
                )
                assignments[pad_idx] = Assignment("ERROR", 0, "puc_ground", why)
                report["ground"] = "ERROR"
                report["ground_reason"] = why
            else:
                assignments[pad_idx] = Assignment(
                    name,
                    0,
                    "puc_ground",
                    f"{pp.puc.cell}.{'+'.join(cand['ports'])} -> "
                    f"{len(pads)}-pad joined group",
                )
        diagnostics.append(report)

    return assignments, diagnostics


# --------------------------------------------------------------------------- #
# rule: PD signal and bias pads
# --------------------------------------------------------------------------- #

PD_OWNER = re.compile(r"lateral_pd_(?P<owner>(?P<kind>puc(?:mua)?)(?P<number>\d+))$")
"""A PD cell names the PUC it serves: ``lateral_pd_pucmua1204``.

Parsed as a whole rather than as "the number 1204", because ``puc<n>`` and
``pucmua<n>`` may share a number -- so the owner is identified by full cell name
and the kind is read from the same match rather than inferred separately.
"""

PD_KIND_FIELD = {"puc": "MESH", "pucmua": "MUA"}
"""MESH or MUA for a PD, from its owner's kind. Unlike a PUC signal name, a
mesh PD carries an explicit ``MESH`` field."""

PD_PORTS = {"e1": "bias", "e2": "signal"}
"""Fixed by port name, not inferred from what the port reaches.

This inverts the PUC rule, where the pad count *decides* whether a port is
signal or ground.  Here the meaning is known up front, so the pad count becomes
an assertion instead: ``e2`` must reach exactly one pad and ``e1`` exactly two,
and anything else is an error rather than a reclassification.
"""


@dataclass(frozen=True)
class PdOwner:
    """The PUC a PD serves, resolved from the PD's own cell name."""

    cell: str
    """Owner PUC cell name, e.g. ``"pucmua1204"``."""
    kind: str
    """``"puc"`` or ``"pucmua"``."""
    number: str
    instance: PlacedInstance | None = None
    """The owner's layout *instance*. ``None`` is an error: a PD naming a PUC
    that is not in the layout, or none on the PD's own side of the die."""
    polarization: str = ""
    """``"TE"`` or ``"TM"``, from the owner instance's x."""

    @property
    def key(self) -> tuple[str, str]:
        """Identity of the owner as an *instance*, not a cell.

        A PUC cell is instanced once per polarization, so ``pucmua10`` names two
        different PUCs -- one TE, one TM -- each with its own pair of PDs.
        Grouping PDs by cell name alone merges them and reports four PDs on one
        PUC; the polarization is what separates them.
        """
        return (self.cell, self.polarization)


def parse_pd_owner(cell: str) -> tuple[str, str, str] | None:
    """Split a PD cell name into its owner PUC.

    ``lateral_pd_pucmua1204`` -> ``("pucmua1204", "pucmua", "1204")``.

    Args:
        cell: the PD's cell name.

    Returns:
        ``(owner cell, kind, number)``, or None if the name does not carry an
        owner. The owner is kept as a whole cell name because ``puc<n>`` and
        ``pucmua<n>`` may share a number, making the number alone ambiguous.
    """
    match = PD_OWNER.match(cell)
    if match is None:
        return None
    return match["owner"], match["kind"], match["number"]


def pd_signal_name(kind: str, number: str, arm: str | None, polarization: str) -> str:
    """The signal pad name for one PD.

    ``lateral_pd_puc<n>``    -> ``PD<n>_MESH_<TE|TM>``
    ``lateral_pd_pucmua<n>`` -> ``PD<n>_<top|bot>_MUA_<TE|TM>``

    A mesh PUC has exactly one PD, so there is nothing to disambiguate and no
    arm field; a MUA PUC always has two, so the arm is required.

    Args:
        kind: owner kind, ``"puc"`` or ``"pucmua"``.
        number: owner number.
        arm: ``"top"``/``"bot"`` for a MUA PD, ``None`` for a mesh PD.
        polarization: ``"TE"`` or ``"TM"``.

    Returns:
        The pad name.

    Raises:
        KeyError: for an owner kind with no entry in :data:`PD_KIND_FIELD`.
        ValueError: if a MUA PD has no arm, or a mesh PD has one.
    """
    field = PD_KIND_FIELD[kind]
    if kind == "pucmua" and arm is None:
        raise ValueError("a MUA PD needs a top/bot field: its PUC always has two")
    if kind == "puc" and arm is not None:
        raise ValueError("a mesh PD must not carry a top/bot field")
    parts = ["PD" + number]
    if arm is not None:
        parts.append(arm)
    parts += [field, polarization]
    return "_".join(parts)


def resolve_pd_owners(
    ctx: PadMapContext,
    pds: list[InstancePorts],
    *,
    puc_glob: str = "puc*",
    puc_regex: str = r"puc(mua)?\d+",
    polarization_strategy: str = "pairs",
    owner_margin: float = 3.0,
) -> tuple[dict[int, PdOwner], dict[int, str | None], list[str]]:
    """Resolve each PD's owner PUC and, for MUA PDs, its arm.

    The owner comes from the PD's own cell name, so the association is exact --
    no traversal, no proximity, no tolerance.  Looking the owner up in the layout
    then buys two things for free: the PUC's x, so polarization is taken from the
    *PUC* and a PD near the die midline can never disagree with its own PUC; and
    a validation that the named PUC exists at all.

    The arm is decided by comparing a ``pucmua``'s two PDs against *each other* --
    higher y is ``top`` -- rather than against a die-wide row position.  Same
    answer while the floorplan holds, but it cannot be silently inverted by a
    layout change, and two PDs at the same y become a visible error instead of an
    arbitrary ordering.

    Args:
        ctx: shared context.
        pds: the PD role records, from :func:`pd_port_roles`.
        puc_glob: glob for the owner lookup.
        puc_regex: exact filter for the owner lookup.
        polarization_strategy: passed to :func:`puc_polarizations`.
        owner_margin: how much further the second-nearest instance of the named
            cell must be than the nearest, for the nearest to count as the owner.
            The two instances of a PUC cell are a whole block apart and a PD sits
            beside its own PUC, so the real ratio is large; a PD that fails this
            is reported rather than assigned to a coin-flip winner.

    Returns:
        ``(owners, arms, faults)`` keyed by index into ``pds``. ``arms`` holds
        ``None`` for mesh PDs. ``faults`` holds one message per PD, empty where
        the PD is fine.
    """
    # cell name -> every instance of it, since a PUC cell is instanced once per
    # polarization and the two are different PUCs with different PDs
    by_cell: dict[str, list[PlacedInstance]] = {}
    for inst in find_instances(
        ctx.die, puc_glob, name_regex=puc_regex, with_ports=False
    ):
        by_cell.setdefault(inst.cell, []).append(inst)
    polarization, _ = puc_polarizations(
        ctx, puc_glob=puc_glob, puc_regex=puc_regex, strategy=polarization_strategy
    )

    owners: dict[int, PdOwner] = {}
    faults: list[str] = [""] * len(pds)
    for i, pp in enumerate(pds):
        parsed = parse_pd_owner(pp.instance.cell)
        if parsed is None:
            faults[i] = (
                f"{pp.instance.cell!r} does not name its owner PUC; expected "
                "lateral_pd_puc<n> or lateral_pd_pucmua<n>"
            )
            continue
        cell, kind, number = parsed
        instances = by_cell.get(cell, [])
        instance = None
        if not instances:
            faults[i] = f"{pp.instance.cell} names {cell}, which is not in the layout"
        else:
            # A PD sits beside its own PUC, and the two instances of a PUC cell are
            # a whole block apart, so the nearer one is the owner by a wide margin.
            # The midline cannot be used here: the halves overlap in x.
            ranked = sorted(
                instances,
                key=lambda inst: (inst.x - pp.instance.x) ** 2
                + (inst.y - pp.instance.y) ** 2,
            )
            near = math.dist((ranked[0].x, ranked[0].y), (pp.instance.x, pp.instance.y))
            far = (
                math.dist((ranked[1].x, ranked[1].y), (pp.instance.x, pp.instance.y))
                if len(ranked) > 1
                else float("inf")
            )
            if far < owner_margin * max(near, 1e-9):
                faults[i] = (
                    f"{pp.instance.cell} is {near:.1f} um from one {cell} and "
                    f"{far:.1f} um from another: the owner is ambiguous"
                )
            else:
                instance = ranked[0]

        pol = polarization.get(instance.key) if instance is not None else None
        if instance is not None and pol is None and not faults[i]:
            faults[i] = (
                f"{cell}: polarization unresolved, so {pp.instance.cell} cannot "
                "be named"
            )
        owners[i] = PdOwner(cell, kind, number, instance, pol or "")

    # group by owner to settle top/bot and the per-kind PD count
    grouped: dict[tuple[str, str], list[int]] = {}
    for i, owner in owners.items():
        if owner.instance is not None:  # a PD with no owner cannot be grouped
            grouped.setdefault(owner.key, []).append(i)

    arms: dict[int, str | None] = {}
    for (cell, pol), members in grouped.items():
        kind = owners[members[0]].kind
        label = f"{cell} ({pol})"
        if kind == "puc":
            if len(members) != 1:
                for i in members:
                    faults[i] = (
                        f"{label} has {len(members)} PDs; "
                        "a mesh PUC must have exactly 1"
                    )
            for i in members:
                arms[i] = None
            continue

        if len(members) != 2:
            for i in members:
                faults[i] = (
                    f"{label} has {len(members)} PDs; a MUA PUC must have exactly 2"
                )
            for i in members:
                arms[i] = None
            continue

        a, b = sorted(members, key=lambda i: pds[i].instance.y, reverse=True)
        if abs(pds[a].instance.y - pds[b].instance.y) < 1e-6:
            for i in (a, b):
                faults[i] = f"{label}: its two PDs share a y, so top/bot is undecidable"
            arms[a] = arms[b] = None
        else:
            arms[a], arms[b] = "top", "bot"

    return owners, arms, faults


def _pd_records(
    ctx: PadMapContext,
    pd_glob: str,
    pd_regex: str,
    probe_offset: float,
    probe_halfwidth: float,
    puc_glob: str,
    puc_regex: str,
):
    """Shared front half of both PD rules: roles, owners, arms and faults."""
    pds = pd_port_roles(
        ctx,
        pd_glob=pd_glob,
        pd_regex=pd_regex,
        probe_offset=probe_offset,
        probe_halfwidth=probe_halfwidth,
    )
    owners, arms, faults = resolve_pd_owners(
        ctx, pds, puc_glob=puc_glob, puc_regex=puc_regex
    )
    return pds, owners, arms, faults


def assign_pd_signals(
    ctx: PadMapContext,
    *,
    pd_glob: str = "lateral_pd_puc*",
    pd_regex: str = r"lateral_pd_puc(mua)?\d+",
    puc_glob: str = "puc*",
    puc_regex: str = r"puc(mua)?\d+",
    probe_offset: float = 15.8,
    probe_halfwidth: float = 1.0,
) -> tuple[dict[int, Assignment], list[dict[str, Any]]]:
    """Name each PD's signal pad, reached from ``e2``.

    ``PD<n>_MESH_<TE|TM>`` for a mesh PD and ``PD<n>_<top|bot>_MUA_<TE|TM>`` for
    a MUA one -- see :func:`pd_signal_name`.  ``e2`` is the signal port by
    definition, so reaching anything other than exactly one pad is an error.

    Args:
        ctx: shared context.
        pd_glob: glob for the PD cells.
        pd_regex: exact filter on top of it.
        puc_glob: glob for the owner lookup.
        puc_regex: exact filter for the owner lookup.
        probe_offset: um, the 90 degree ``e1`` offset. Unused for ``e2``, which
            never attaches off-port, but it keys the shared role pass.
        probe_halfwidth: um probe box half-width.

    Returns:
        ``(assignments, diagnostics)``.
    """
    pds, owners, arms, faults = _pd_records(
        ctx, pd_glob, pd_regex, probe_offset, probe_halfwidth, puc_glob, puc_regex
    )

    assignments: dict[int, Assignment] = {}
    diagnostics: list[dict[str, Any]] = []

    for i, pp in enumerate(pds):
        report = _port_report(pp)
        role = pp.roles["e2"]
        report["owner"] = owners[i].cell if i in owners else None
        report["arm"] = arms.get(i)

        fault = faults[i]
        if not fault and role.role != "signal":
            fault = (
                f"{pp.instance.cell}.e2 is the signal port but reached "
                f"{len(role.pads)} pads ({role.role}): {role.note}"
            )

        if fault:
            report["signal"] = "ERROR"
            report["signal_reason"] = fault
            for pad_idx in role.pads:
                assignments[pad_idx] = Assignment("ERROR", 0, "pd_signal", fault)
            diagnostics.append(report)
            continue

        owner = owners[i]
        try:
            name = pd_signal_name(
                owner.kind, owner.number, arms.get(i), owner.polarization
            )
        except (KeyError, ValueError) as exc:
            report["signal"] = "ERROR"
            report["signal_reason"] = str(exc)
            for pad_idx in role.pads:
                assignments[pad_idx] = Assignment("ERROR", 0, "pd_signal", str(exc))
            diagnostics.append(report)
            continue

        pad_idx = role.pads[0]
        held = assignments.get(pad_idx)
        if held is not None and held.name != name:
            why = f"claimed by both {held.name} and {name}"
            assignments[pad_idx] = Assignment("ERROR", 0, "pd_signal", why)
            report["signal"] = "ERROR"
            report["signal_reason"] = why
        else:
            assignments[pad_idx] = Assignment(
                name,
                1,
                "pd_signal",
                f"{pp.instance.cell}.e2 -> lone pad, owner {owner.cell}",
                component=pp.instance.origin_key,
            )
            report["signal"] = name
        diagnostics.append(report)

    return assignments, diagnostics


def assign_pd_bias(
    ctx: PadMapContext,
    *,
    pd_glob: str = "lateral_pd_puc*",
    pd_regex: str = r"lateral_pd_puc(mua)?\d+",
    puc_glob: str = "puc*",
    puc_regex: str = r"puc(mua)?\d+",
    probe_offset: float = 15.8,
    probe_halfwidth: float = 1.0,
    pad_diameter: float = 65.656,
    join_length: float = 245.656,
    neck_offset: float = 25.0,
    tolerance: float = 0.05,
    verify_neck: bool = True,
) -> tuple[dict[int, Assignment], list[dict[str, Any]]]:
    """Name each PD's bias pads ``BIAS_MESH`` or ``BIAS_MUA``, reached from ``e1``.

    A bias group is strictly a pair -- unlike a PUC ground group, where three is
    legal -- and is verified the same way: collinear, spaced so the covered
    extent matches ``join_length``, and neck-probed to distinguish a solid join
    from a 20 um continuity bar, which has an identical bounding box.

    Up to four PDs may share one pair, and they are always of one kind, so every
    PD naming a given pair must agree on MESH vs MUA; disagreement is an error
    rather than a last-writer-wins.

    Args:
        ctx: shared context.
        pd_glob: glob for the PD cells.
        pd_regex: exact filter on top of it.
        puc_glob: glob for the owner lookup.
        puc_regex: exact filter for the owner lookup.
        probe_offset: um, the 90 degree ``e1`` offset.
        probe_halfwidth: um probe box half-width.
        pad_diameter: um, used with the pad span to reconstruct the join extent.
        join_length: um, the measured 2-pad join length.
        neck_offset: um from the join centreline for the neck probe.
        tolerance: um tolerance on the join length check.
        verify_neck: run the neck probe.

    Returns:
        ``(assignments, diagnostics)``.
    """
    pds, owners, arms, faults = _pd_records(
        ctx, pd_glob, pd_regex, probe_offset, probe_halfwidth, puc_glob, puc_regex
    )

    candidates: list[dict[str, Any]] = []
    probe_points: list[tuple[float, float]] = []
    for i, pp in enumerate(pds):
        role = pp.roles["e1"]
        cand: dict[str, Any] = {"i": i, "pads": role.pads, "fault": faults[i]}
        candidates.append(cand)

        if not cand["fault"] and role.role != "group":
            cand["fault"] = (
                f"{pp.instance.cell}.e1 is the bias port but reached "
                f"{len(role.pads)} pads ({role.role}): {role.note}"
            )
        if cand["fault"]:
            continue
        if len(role.pads) not in BIAS_GROUP_SIZES:
            cand["fault"] = (
                f"bias group of {len(role.pads)} pads; a bias group is always a pair"
            )
            continue
        axis, span, note = _group_geometry(ctx, role.pads)
        if axis is None:
            cand["fault"] = note
            continue
        if abs(span + pad_diameter - join_length) > tolerance:
            cand["fault"] = (
                f"join extent {span + pad_diameter:.3f} um does not match the "
                f"bias join length {join_length} um"
            )
            continue
        if verify_neck:
            points = _neck_points(ctx, role.pads, axis, neck_offset)
            cand["neck"] = range(len(probe_points), len(probe_points) + len(points))
            probe_points += points

    live = ctx.probe_live(probe_points, probe_halfwidth) if probe_points else set()

    assignments: dict[int, Assignment] = {}
    diagnostics: list[dict[str, Any]] = []

    for cand in candidates:
        i = cand["i"]
        pp = pds[i]
        pads: tuple[int, ...] = cand["pads"]
        report = _port_report(pp)
        report["owner"] = owners[i].cell if i in owners else None
        report["bias_pads"] = list(pads)

        if not cand["fault"] and verify_neck and "neck" in cand:
            missing = [k for k in cand["neck"] if k not in live]
            if missing:
                cand["fault"] = (
                    f"no metal {neck_offset} um off the join centreline at "
                    f"{len(missing)} of {len(cand['neck'])} probe points: the pads "
                    "are bridged by something narrower than a bias join"
                )

        if cand["fault"]:
            report["bias"] = "ERROR"
            report["bias_reason"] = cand["fault"]
            for pad_idx in pads:
                assignments[pad_idx] = Assignment("ERROR", 0, "pd_bias", cand["fault"])
            diagnostics.append(report)
            continue

        owner = owners[i]
        name = f"BIAS_{PD_KIND_FIELD[owner.kind]}"
        report["bias"] = name
        for pad_idx in pads:
            held = assignments.get(pad_idx)
            if held is not None and held.name != name:
                why = (
                    f"bias pair claimed as both {held.name} and {name}: "
                    "a pair is never shared between a puc and a pucmua"
                )
                assignments[pad_idx] = Assignment("ERROR", 0, "pd_bias", why)
                report["bias"] = "ERROR"
                report["bias_reason"] = why
            else:
                assignments[pad_idx] = Assignment(
                    name,
                    0,
                    "pd_bias",
                    f"{pp.instance.cell}.e1 -> 2-pad joined group, owner {owner.cell}",
                )
        diagnostics.append(report)

    return assignments, diagnostics


# --------------------------------------------------------------------------- #
# rule: thermistor pads
# --------------------------------------------------------------------------- #

TH_PORTS = {"e1": "S", "e2": "G"}
"""Thermistor ports: ``e1`` signal, ``e2`` ground. Fixed by name, like the PD."""


def th_port_roles(
    ctx: PadMapContext,
    *,
    th_glob: str = "serie_thermistor*",
    th_regex: str = r"serie_thermistor.*",
    probe_halfwidth: float = 1.0,
    cache: bool = True,
) -> list[InstancePorts]:
    """:func:`port_roles` for thermistors: MT1, ``e1``/``e2``, no offset.

    Thermistor terminals leave on MT1 rather than MT3, and neither port has an
    alternative attachment point, so each port has exactly one probe.  Both pads
    are standalone -- no joined groups -- hence ``group_sizes=()``: any port
    reaching more than one pad is ``overreaching`` rather than a group.

    Args:
        ctx: shared context.
        th_glob: anchored glob for the thermistor cells.
        th_regex: exact filter on top of it.
        probe_halfwidth: um probe box half-width.
        cache: reuse a previous result for the same arguments.

    Returns:
        One :class:`InstancePorts` per thermistor, in discovery order.
    """
    return port_roles(
        ctx,
        glob=th_glob,
        regex=th_regex,
        ports=("e1", "e2"),
        probe_layer="m1",
        candidates_fn=lambda n, p, c: [(p[0], p[1], "port")],
        group_sizes=(),
        probe_halfwidth=probe_halfwidth,
        cache_key=("th",),
        cache=cache,
    )


def _split_at_largest_gap(values: list[float]) -> float:
    """Threshold separating 'within a row' from 'between rows' in sorted gaps.

    Row spacing is far larger than the placement jitter inside a row, so the
    sorted gaps fall into two obvious clusters and the threshold is the midpoint
    of the widest jump between them.  Deriving it beats a fixed tolerance because
    thermistors are placed loosely -- they share neither an x nor a y -- so any
    constant would be either too tight for the jitter or loose enough to merge
    two rows.
    """
    gaps = sorted(values)
    if len(gaps) < 2:
        return (gaps[0] / 2) if gaps else 0.0
    jumps = [(gaps[i + 1] - gaps[i], i) for i in range(len(gaps) - 1)]
    _, at = max(jumps)
    return 0.5 * (gaps[at] + gaps[at + 1])


def order_thermistors(
    instances: list[PlacedInstance],
    *,
    rows: int | None = None,
    row_tolerance: float | None = None,
) -> list[int]:
    """Reading order -- left to right, top to bottom -- for loosely placed parts.

    Thermistors share neither an x nor a y, so they cannot be clustered on exact
    coordinates the way the pad lattice is.  Rows are recovered from the *gaps*
    between consecutive y values instead: within a row the gaps are jitter, and
    between rows they are the row pitch, and the two are separated by a wide
    margin.

    Args:
        instances: the thermistors, any order.
        rows: expected row count. When given, the y sequence is cut at the
            ``rows - 1`` largest gaps, which is exact even if a row's jitter
            happens to rival another row's spacing. Prefer this when the count is
            known -- there are nine on this die, in three rows.
        row_tolerance: explicit um threshold; two thermistors are in the same row
            if their y values differ by less than this. Overrides the derived
            threshold.

    Returns:
        Indices into ``instances``, in reading order.
    """
    if not instances:
        return []

    order = sorted(range(len(instances)), key=lambda i: -instances[i].y)
    ys = [instances[i].y for i in order]
    gaps = [ys[i] - ys[i + 1] for i in range(len(ys) - 1)]  # descending y

    if len(instances) == 1 or not gaps:
        return order

    if rows is not None and rows > 1:
        cuts = {
            i
            for _, i in sorted(((g, i) for i, g in enumerate(gaps)), reverse=True)[
                : rows - 1
            ]
        }
    else:
        threshold = (
            row_tolerance if row_tolerance is not None else _split_at_largest_gap(gaps)
        )
        cuts = {i for i, g in enumerate(gaps) if g > threshold}

    out: list[int] = []
    row: list[int] = [order[0]]
    for i, idx in enumerate(order[1:]):
        if i in cuts:
            out += sorted(row, key=lambda j: instances[j].x)
            row = []
        row.append(idx)
    out += sorted(row, key=lambda j: instances[j].x)
    return out


def assign_thermistors(
    ctx: PadMapContext,
    *,
    th_glob: str = "serie_thermistor*",
    th_regex: str = r"serie_thermistor.*",
    probe_halfwidth: float = 1.0,
    rows: int | None = None,
    row_tolerance: float | None = None,
    start_index: int = 0,
) -> tuple[dict[int, Assignment], list[dict[str, Any]]]:
    """Name each thermistor's two pads ``TH_<n>_S`` and ``TH_<n>_G``.

    The number comes from the thermistor's position among the others -- reading
    order, left to right then top to bottom -- not from its cell name, so it is
    assigned by :func:`order_thermistors` over the whole die at once.

    Args:
        ctx: shared context.
        th_glob: glob for the thermistor cells.
        th_regex: exact filter on top of it.
        probe_halfwidth: um probe box half-width.
        rows: expected row count, passed to :func:`order_thermistors`.
        row_tolerance: explicit row threshold in um.
        start_index: number of the first thermistor. Defaults to 0.

    Returns:
        ``(assignments, diagnostics)``. The signal pad gets ``signal_ground = 1``
        and the ground pad 0.
    """
    ths = th_port_roles(
        ctx, th_glob=th_glob, th_regex=th_regex, probe_halfwidth=probe_halfwidth
    )
    instances = [pp.instance for pp in ths]
    order = order_thermistors(instances, rows=rows, row_tolerance=row_tolerance)
    number_of = {idx: start_index + n for n, idx in enumerate(order)}

    assignments: dict[int, Assignment] = {}
    diagnostics: list[dict[str, Any]] = []

    for i, pp in enumerate(ths):
        number = number_of[i]
        report = _port_report(pp)
        report["th_number"] = number

        for port, suffix in TH_PORTS.items():
            role = pp.roles[port]
            name = f"TH_{number}_{suffix}"
            if role.role != "signal":  # exactly one pad, both ports alike
                why = (
                    f"{pp.instance.cell} at ({pp.instance.x:.1f}, "
                    f"{pp.instance.y:.1f}).{port} should reach exactly one pad "
                    f"but is {role.role}: {role.note}"
                )
                report[suffix] = "ERROR"
                report[f"{suffix}_reason"] = why
                for pad_idx in role.pads:
                    assignments[pad_idx] = Assignment("ERROR", 0, "thermistor", why)
                continue

            pad_idx = role.pads[0]
            held = assignments.get(pad_idx)
            if held is not None and held.name != name:
                why = f"claimed by both {held.name} and {name}"
                assignments[pad_idx] = Assignment("ERROR", 0, "thermistor", why)
                report[suffix] = "ERROR"
                report[f"{suffix}_reason"] = why
            else:
                assignments[pad_idx] = Assignment(
                    name,
                    1 if suffix == "S" else 0,
                    "thermistor",
                    f"{pp.instance.cell}.{port} -> lone pad",
                )
                report[suffix] = name

        diagnostics.append(report)

    return assignments, diagnostics


# --------------------------------------------------------------------------- #
# rule: DC continuity chains
# --------------------------------------------------------------------------- #

DC_BAR = (180.0, 20.0)
"""The on-die link between two chain pads: 180 um long, 20 um wide.

Note this is *not* what gets named.  The ring is a daisy chain closed through the
package, so the on-die bars are the links that already exist and the thing that
carries a ``DC`` number is the **gap** between them -- the pair of pads facing
each other with no metal in between, which the flip-chip bump will bridge.
"""


@dataclass(frozen=True)
class DcConnection:
    """One numbered element of a chain: a gap, or a dangling end pad.

    A gap holds the two pads facing each other across it.  A dangling end holds
    one: the pad at the very start or end of an open chain, which has a bar on
    one side and nothing on the other.  Squares are closed, so every connection
    in one is a pair.
    """

    pads: tuple[int, ...]
    kind: str
    """``"gap"`` or ``"end"``."""


def _dc_axis(box: tuple[float, float, float, float]) -> str:
    """``"x"`` for a zone running along the top or bottom, ``"y"`` for a side."""
    x0, y0, x1, y1 = box
    return "x" if (x1 - x0) >= (y1 - y0) else "y"


def _dc_direction(
    box: tuple[float, float, float, float],
    centre: tuple[float, float],
    override: int | None = None,
) -> int:
    """Traversal sign along the zone's long axis, going clockwise round the die.

    Clockwise from the top-left means the top edge runs +x, the right edge -y,
    the bottom edge -x and the left edge +y.  Which edge a zone is on follows
    from which side of the die centre it sits.

    That inference only means anything for a zone on the ring.  A chain away from
    the border -- one crossing the middle of the die, say -- sits near the centre
    on one axis or both, so the sign it would get depends on which side of the
    centre line it happens to fall by a few microns, and could flip on a small
    floorplan change.  Such a zone should be given an explicit ``override``.

    Args:
        box: the zone rectangle.
        centre: the die centre.
        override: ``+1`` or ``-1`` to set the sign directly, ``None`` to infer.

    Returns:
        ``+1`` to traverse in increasing x (or y), ``-1`` for decreasing.
    """
    if override is not None:
        return 1 if override >= 0 else -1
    x0, y0, x1, y1 = box
    if _dc_axis(box) == "x":
        return 1 if 0.5 * (y0 + y1) > centre[1] else -1  # top -> +x, bottom -> -x
    return -1 if 0.5 * (x0 + x1) > centre[0] else 1  # right -> -y, left -> +y


def _dc_rows(
    ctx: PadMapContext,
    pads: list[int],
    axis: str,
    tol: float,
    centre: tuple[float, float],
) -> list[list[int]]:
    """Split zone pads into rows by their transverse coordinate.

    Rows come back **outermost first** -- ordered by distance from the die
    centre, not by ascending coordinate. That is the order the walk visits them:
    a square is entered on the row nearest the die edge and returns along the
    inner one, so ordering by raw coordinate would run the numbering backwards on
    the top and right edges.
    """

    def across(i: int) -> float:
        """The pad's coordinate transverse to the zone's long axis."""
        return ctx.pad_by_index[i].y if axis == "x" else ctx.pad_by_index[i].x

    mid = centre[1] if axis == "x" else centre[0]
    labels, centres = _cluster([across(i) for i in pads], tol)
    rows: list[list[int]] = [[] for _ in centres]
    for pad, label in zip(pads, labels, strict=True):
        rows[label].append(pad)
    order = sorted(range(len(centres)), key=lambda k: -abs(centres[k] - mid))
    return [rows[k] for k in order]


def _dc_bars(
    ctx: PadMapContext, pads: list[int]
) -> tuple[dict[int, int], list[tuple[int, int]], list[str]]:
    """Pads joined on-die, by net. Returns (partner map, bars, faults).

    Two pads bridged by a bar share a net; two pads across a gap do not.  Net
    identity is therefore the whole of bar detection -- no geometry needed --
    and the geometry check that follows is there to catch the one thing net
    identity cannot see: a *ground* join, 65.656 um wide, sitting in the ring.
    """
    partner: dict[int, int] = {}
    bars: list[tuple[int, int]] = []
    faults: list[str] = []
    seen: set[str] = set()
    for pad in pads:
        p = ctx.pad_by_index[pad]
        net = ctx.net_at(p.x, p.y)
        if net is None:
            continue
        name = net.expanded_name()
        if name in seen:
            continue
        seen.add(name)
        members = [i for i in ctx.pads_of_net(net) if i in set(pads)]
        if len(members) == 1:
            continue  # a lone pad: legal at the end of an open chain
        if len(members) != 2:
            faults.append(
                f"net {name} joins {len(members)} chain pads; a chain bar joins 2"
            )
            continue
        a, b = members
        partner[a], partner[b] = b, a
        bars.append((a, b))
    return partner, bars, faults


def _dc_connections(
    ctx: PadMapContext,
    rows: list[list[int]],
    partner: dict[int, int],
    axis: str,
    direction: int,
) -> tuple[list[DcConnection], list[str]]:
    """Walk a block and return its numbered connections in traversal order.

    A **square** (two rows) is a closed serpentine: in at the near end, along the
    outer row, across at the far end, back along the inner row.  Its connections
    are the near vertical gap, the outer row's gaps in traversal order, the far
    vertical gap, then the inner row's gaps in reverse -- which is the order the
    numbers follow, not a scan of one row and then the other.

    A **chain** (one row) is the same walk unfolded, and may begin or end on a
    pad with a bar on one side and nothing on the other; that pad is a connection
    on its own.
    """

    def along(i: int) -> float:
        """The pad's coordinate along the zone's long axis."""
        return ctx.pad_by_index[i].x if axis == "x" else ctx.pad_by_index[i].y

    faults: list[str] = []
    ordered = [sorted(row, key=lambda i: direction * along(i)) for row in rows]

    def row_gaps(row: list[int]) -> list[DcConnection]:
        """Gaps between consecutive pads of one row: every pair not bar-joined."""
        out: list[DcConnection] = []
        for a, b in zip(row, row[1:], strict=False):
            if partner.get(a) != b:
                out.append(DcConnection((a, b), "gap"))
        return out

    if len(ordered) == 1:
        row = ordered[0]
        out: list[DcConnection] = []
        if row and partner.get(row[0]) == (row[1] if len(row) > 1 else None):
            out.append(DcConnection((row[0],), "end"))  # dangling start
        out += row_gaps(row)
        if len(row) > 1 and partner.get(row[-1]) == row[-2]:
            out.append(DcConnection((row[-1],), "end"))  # dangling finish
        return out, faults

    if len(ordered) != 2:
        return [], [f"block has {len(ordered)} rows; expected 1 (chain) or 2 (square)"]

    outer, inner = ordered
    if not outer or not inner:
        return [], ["block has an empty row"]

    out = [DcConnection((outer[0], inner[0]), "gap")]  # near end, across the rows
    out += row_gaps(outer)
    out.append(DcConnection((outer[-1], inner[-1]), "gap"))  # far end
    out += list(reversed(row_gaps(inner)))
    return out, faults


def assign_dc_chains(
    ctx: PadMapContext,
    zones: Sequence[tuple[float, float, float, float]],
    *,
    row_tolerance: float = 1.0,
    bar: tuple[float, float] = DC_BAR,
    neck_offset: float = 25.0,
    tolerance: float = 0.05,
    verify_bars: bool = True,
    start_index: int = 1,
    on_overlap: Literal["first", "error"] = "first",
    directions: Sequence[int | None] | None = None,
) -> tuple[dict[int, Assignment], list[dict[str, Any]]]:
    """Name the continuity-chain pads ``DC<block>.<n>``.

    Args:
        ctx: shared context.
        zones: rectangles ``(xmin, ymin, xmax, ymax)`` in um covering the ring,
            in order -- ``DC1`` first, then clockwise from the top-left.

            A zone may cover a whole region (all three rows), in which case it
            yields two blocks: the square on the two rows nearest the die edge,
            then the straight chain on the inner row, taking two consecutive
            ``DC`` indices. That is usually what you want -- one rectangle per
            region rather than two, and the square and chain cannot then
            disagree about where the region starts and ends. A zone may also
            cover just one of them: two rows is read as a square, one row as a
            chain.
        row_tolerance: um. Two pads are in the same row if their transverse
            coordinates are within this.
        bar: ``(length, width)`` of the on-die link, for the geometry check.
        neck_offset: um from the bar centreline for the width probe. Must sit
            between half a bar (10) and half a pad (32.828).
        tolerance: um tolerance on the bar length check.
        verify_bars: probe each bar to confirm it is the narrow chain link and
            not a wide ground join, which shares its bounding box exactly.
        start_index: number of the first connection in a block. Defaults to 1.
        on_overlap: what to do with a pad claimed by two zones -- take the
            ``"first"`` zone in the list (the earlier block owns a shared corner
            pad), or call it an ``"error"``.

    Returns:
        ``(assignments, diagnostics)``. Both pads of a gap share the name;
        a dangling end pad carries its number alone. All get
        ``signal_ground = 0``.
    """
    centre = (
        0.5 * (ctx.die_bbox.left + ctx.die_bbox.right),
        0.5 * (ctx.die_bbox.bottom + ctx.die_bbox.top),
    )

    claimed: dict[int, int] = {}
    per_zone: list[list[int]] = []
    overlaps: list[tuple[int, int, int]] = []
    for z, box in enumerate(zones):
        x0, y0, x1, y1 = box
        members: list[int] = []
        for pad in ctx.pads:
            if min(x0, x1) <= pad.x <= max(x0, x1) and min(y0, y1) <= pad.y <= max(
                y0, y1
            ):
                if pad.index in claimed:
                    overlaps.append((pad.index, claimed[pad.index], z))
                    continue
                claimed[pad.index] = z
                members.append(pad.index)
        per_zone.append(members)

    assignments: dict[int, Assignment] = {}
    diagnostics: list[dict[str, Any]] = []

    if overlaps and on_overlap == "error":
        for pad_idx, first, second in overlaps:
            why = f"pad lies in both DC{first + 1} and DC{second + 1}"
            assignments[pad_idx] = Assignment("ERROR", 0, "dc_chain", why)

    # bar geometry probes, batched across every block
    probe_points: list[tuple[float, float]] = []
    probe_owner: list[tuple[int, int, int]] = []
    zone_bars: list[list[tuple[int, int]]] = []
    zone_partner: list[dict[int, int]] = []
    zone_faults: list[list[str]] = []
    for z, members in enumerate(per_zone):
        partner, bars, faults = _dc_bars(ctx, members)
        zone_partner.append(partner)
        zone_bars.append(bars)
        zone_faults.append(faults)
        if not verify_bars:
            continue
        for a, b in bars:
            pa, pb = ctx.pad_by_index[a], ctx.pad_by_index[b]
            span = math.dist((pa.x, pa.y), (pb.x, pb.y))
            if abs(span - bar[0]) > tolerance:
                faults.append(
                    f"bar spans {span:.3f} um, not the {bar[0]} um chain link"
                )
                continue
            mx, my = 0.5 * (pa.x + pb.x), 0.5 * (pa.y + pb.y)
            horizontal = abs(pa.y - pb.y) < abs(pa.x - pb.x)
            for sign in (1, -1):
                probe_points.append(
                    (mx, my + sign * neck_offset)
                    if horizontal
                    else (mx + sign * neck_offset, my)
                )
                probe_owner.append((z, a, b))

    live = ctx.probe_live(probe_points, 1.0) if probe_points else set()
    wide: set[tuple[int, int, int]] = {probe_owner[k] for k in live}

    # A zone may hold one block or two: three rows is a square (the two rows
    # nearest the die edge) plus the straight chain on the inner row, which is
    # how the ring is actually drawn, so one rectangle per region is enough.
    blocks: list[dict[str, Any]] = []
    for z, members in enumerate(per_zone):
        if not members:
            blocks.append({"zone": z, "rows": [], "shape": "empty", "faults": []})
            continue
        axis = _dc_axis(zones[z])
        rows = _dc_rows(ctx, members, axis, row_tolerance, centre)
        if len(rows) == 3:
            blocks.append(
                {"zone": z, "rows": rows[:2], "shape": "square", "faults": []}
            )
            blocks.append({"zone": z, "rows": rows[2:], "shape": "chain", "faults": []})
        elif len(rows) == 2:
            blocks.append({"zone": z, "rows": rows, "shape": "square", "faults": []})
        elif len(rows) == 1:
            blocks.append({"zone": z, "rows": rows, "shape": "chain", "faults": []})
        else:
            blocks.append(
                {
                    "zone": z,
                    "rows": rows,
                    "shape": "?",
                    "faults": [
                        f"zone holds {len(rows)} rows; expected 1 (chain), 2 (square) "
                        "or 3 (square plus chain)"
                    ],
                }
            )

    for n_block, block in enumerate(blocks):
        z = block["zone"]
        label = f"DC{n_block + 1}"
        rows = block["rows"]
        members = [i for row in rows for i in row]
        report: dict[str, Any] = {
            "block": label,
            "zone": zones[z],
            "shape": block["shape"],
            "pads": len(members),
            "rows": len(rows),
            "direction": _dc_direction(
                zones[z], centre, directions[z] if directions is not None else None
            ),
        }
        faults = list(zone_faults[z]) + list(block["faults"])

        # a bar with metal beside it is a ground join, not a chain link: the two
        # have identical bounding boxes, so only the width probe separates them
        member_set = set(members)
        for z2, a, _ in wide:
            if z2 == z and a in member_set:
                faults.append(
                    f"the link between two pads is wider than {bar[1]} um: it is a "
                    "ground join, not a chain bar"
                )

        if not members:
            report["status"] = "empty"
            diagnostics.append(report)
            continue

        axis = _dc_axis(zones[z])
        direction = _dc_direction(
            zones[z], centre, directions[z] if directions is not None else None
        )
        connections, walk_faults = _dc_connections(
            ctx, rows, zone_partner[z], axis, direction
        )
        faults += walk_faults
        report["connections"] = len(connections)

        used = [p for c in connections for p in c.pads]
        if len(set(used)) != len(used):
            faults.append("a pad appears in two connections")
        missing = set(members) - set(used)
        if missing:
            faults.append(
                f"{len(missing)} pads belong to no connection: the chain is broken"
            )
        if len(rows) == 2 and any(c.kind == "end" for c in connections):
            faults.append("a square must be closed, but has a dangling end pad")

        if faults:
            report["status"] = "ERROR"
            report["reason"] = "; ".join(faults[:3])
            for pad_idx in members:
                assignments[pad_idx] = Assignment(
                    "ERROR", 0, "dc_chain", report["reason"]
                )
            diagnostics.append(report)
            continue

        report["status"] = "ok"
        for n, connection in enumerate(connections, start=start_index):
            name = f"{label}.{n}"
            for pad_idx in connection.pads:
                assignments[pad_idx] = Assignment(
                    name,
                    0,
                    "dc_chain",
                    f"{connection.kind} {n} of {len(connections)} in {label}",
                )
        diagnostics.append(report)

    return assignments, diagnostics


# --------------------------------------------------------------------------- #
# rule: dummy pads
# --------------------------------------------------------------------------- #


def assign_dummies(
    ctx: PadMapContext,
    *,
    pad_diameter: float = 65.656,
    margin: float = 1.0,
) -> tuple[dict[int, Assignment], list[dict[str, Any]]]:
    """Name every electrically isolated pad ``DUMMY``.

    A dummy serves nothing, and the test is entirely on MT3: the pad's net must
    reach no other pad and its MT3 geometry must not extend beyond the pad
    itself.  Overlap on any other layer is irrelevant -- a dummy may sit on top
    of silicon, MT1, MT2 or anything else, and routinely does -- so only the MT3
    extent is measured.

    Deliberately not "whatever no other rule claimed".  Deriving dummies by
    elimination would turn every failure elsewhere into a confident ``DUMMY``:
    a PUC whose probe missed, a PD whose owner was absent, a chain pad outside
    its zone would all silently become dummies. Testing the pad directly means a
    pad that is neither properly connected *nor* isolated stays unresolved, which
    is what an ``ERROR`` is for.

    Args:
        ctx: shared context.
        pad_diameter: um, the pad's own extent on MT3.
        margin: um of slack on that extent, absorbing the polygon approximation
            of the circle and any grid snapping. Must stay well below the
            distance to a neighbouring pad.

    Returns:
        ``(assignments, diagnostics)``. Dummies get ``signal_ground = 0``; pads
        that are *not* isolated are left entirely to the other rules.
    """
    half = 0.5 * pad_diameter + margin
    assignments: dict[int, Assignment] = {}
    connected = 0

    for pad in ctx.pads:
        net = ctx.net_at(pad.x, pad.y)
        if net is None:
            # no MT3 at the pad centre at all: not a pad-shaped thing, leave it
            continue
        if len(ctx.pads_of_net(net)) != 1:
            connected += 1
            continue
        region = ctx.l2n.shapes_of_net(net, ctx.l["m3"], True)
        if region is None or region.is_empty():
            continue
        box = region.bbox().to_dtype(ctx.dbu)
        if (
            box.left >= pad.x - half
            and box.right <= pad.x + half
            and box.bottom >= pad.y - half
            and box.top <= pad.y + half
        ):
            assignments[pad.index] = Assignment(
                "DUMMY", 0, "dummy", "MT3 does not extend beyond the pad"
            )
        else:
            connected += 1

    diagnostics = [
        {
            "pads": len(ctx.pads),
            "dummies": len(assignments),
            "connected": connected,
        }
    ]
    return assignments, diagnostics


# --------------------------------------------------------------------------- #
# PIC names from the netlist
# --------------------------------------------------------------------------- #

_PIC_LEAF = re.compile(r"(?P<cell>(?:lateral_pd_)?puc(?:mua)?\d+)(?:_|$)")
"""Matches the cell name at the start of a netlist path's last segment.

Admits both a PUC (``puc2592_5656435_m12999830``) and a PD
(``lateral_pd_pucmua25_2141403_10329000_A90``), and captures the *whole* cell
name so a PD never collides with the PUC it is named after: ``lateral_pd_puc25``
and ``puc25`` are different keys.
"""


@dataclass(frozen=True)
class PicNames:
    """Full hierarchical netlist names for the PUC instances, ready to look up.

    Built by :func:`load_pic_names`. Lookup is by
    :attr:`PlacedInstance.origin_key`.
    """

    exact: dict[tuple[str, int, int], str]
    """Placement matched to the nearest nanometre."""
    by_cell: dict[str, list[tuple[float, float, str]]]
    """``{cell: [(x, y, path)]}``, for the nearest-placement fallback."""
    tolerance: float = 5.0
    """um within which a placement still counts as the same instance.

    Generous on purpose.  A component edit can move a placement by a micron or
    two without anything being wrong, and a tight tolerance turns that into a
    column of ``ERROR``.  Being generous costs nothing here because candidates
    are only ever compared *within one cell*, and a cell's two instances are a
    whole block -- over 11 mm -- apart, so nothing else is within thousands of um
    to be confused with.
    """
    ratio: float = 10.0
    """How much further the runner-up must be than the nearest candidate.

    The guard that makes a loose tolerance safe: if two placements of one cell
    are comparably close, the match is reported ambiguous rather than resolved to
    whichever won by a hair.
    """

    def match(self, key: tuple[str, int, int] | None) -> tuple[str | None, float, str]:
        """Resolve one instance, with the evidence for why it did or did not.

        Args:
            key: an :attr:`PlacedInstance.origin_key`, or None.

        Returns:
            ``(name, distance in um, note)``. ``name`` is None when unresolved.
            The distance is what distinguishes the two ways a match can fail --
            absent from the netlist, or present but placed somewhere the layout
            disagrees with -- and a constant non-zero distance across many PUCs
            means the netlist is stale rather than that anything is misplaced.
        """
        if key is None:
            return None, float("inf"), "no component recorded for this pad"
        hit = self.exact.get(key)
        if hit is not None:
            return hit, 0.0, "exact placement"

        cell, kx, ky = key
        x, y = kx / 1000, ky / 1000
        candidates = sorted(
            (
                (math.dist((px, py), (x, y)), path)
                for px, py, path in self.by_cell.get(cell, ())
            ),
            key=lambda t: t[0],
        )
        if not candidates:
            return None, float("inf"), f"no {cell} placement in the netlist"
        best_d, best = candidates[0]
        if best_d > self.tolerance:
            return (
                None,
                best_d,
                (
                    f"nearest {cell} placement is {best_d:.3f} um away, beyond the "
                    f"{self.tolerance} um tolerance"
                ),
            )
        if len(candidates) > 1 and candidates[1][0] < best_d * self.ratio:
            return (
                None,
                best_d,
                (
                    f"two {cell} placements are comparably close "
                    f"({best_d:.3f} and {candidates[1][0]:.3f} um): ambiguous"
                ),
            )
        return best, best_d, f"nearest placement, {best_d:.3f} um away"

    def get(self, key: tuple[str, int, int] | None) -> str | None:
        """The netlist name for one instance, or None if unresolved."""
        return self.match(key)[0]

    def __len__(self) -> int:
        """How many PUC instances the netlist placed."""
        return len(self.exact)


def load_pic_names(
    netlist: str | dict[str, Any],
    *,
    cell_pattern: re.Pattern[str] = _PIC_LEAF,
    tolerance: float = 5.0,
    ratio: float = 10.0,
) -> tuple[PicNames, list[str]]:
    """Read the full hierarchical name of every PUC instance from the netlist.

    The netlist is the authority on its own names, so the name is read from it
    rather than reconstructed from the layout. Rebuilding the path would mean
    hardcoding gdsfactory's ``<cell>_<dx>_<dy>`` instance-naming convention,
    which breaks silently if an instance was named explicitly or the convention
    shifts -- and a wrong-but-plausible path is nearly impossible to spot in a
    20,000-row sheet.

    Matching is on ``(leaf cell name, placement x, placement y)``. ``placements``
    holds absolute die-frame coordinates, and the cell name alone is not unique
    because every PUC cell is instanced twice, so the coordinate is what
    separates the TE instance from the TM one. Note that a placement is the
    instance's *origin*, not its bbox centre, which is why
    :attr:`PlacedInstance.origin` exists.

    Args:
        netlist: path to the netlist JSON, or an already-loaded dict.
        cell_pattern: matches the cell name at the start of an instance path's
            last segment. The default admits ``puc<n>`` and ``pucmua<n>``.
        tolerance: um. Absorbs both the float representation in the JSON
            (``2948.955000000001``) and a component edit that shifts a placement
            by a micron or two, while staying far below the distance between two
            instances of one cell, which is a whole block. See
            :attr:`PicNames.tolerance`.
        ratio: ambiguity guard for the fallback. See :attr:`PicNames.ratio`.

    Returns:
        ``(PicNames, faults)``. ``faults`` reports placements with no usable
        coordinates and two entries claiming one position.
    """
    if isinstance(netlist, str):
        import json
        from pathlib import Path

        data = json.loads(Path(netlist).read_text())
    else:
        data = netlist

    placements = data.get("placements", data)
    faults: list[str] = []
    exact: dict[tuple[str, int, int], str] = {}
    by_cell: dict[str, list[tuple[float, float, str]]] = {}

    for path, place in placements.items():
        leaf = str(path).split("~")[-1]
        match = cell_pattern.match(leaf)
        if match is None:
            continue
        cell = match["cell"]
        try:
            x, y = float(place["x"]), float(place["y"])
        except (KeyError, TypeError, ValueError):
            faults.append(f"{path}: placement has no usable x/y")
            continue
        key = (cell, round(x * 1000), round(y * 1000))
        if key in exact and exact[key] != path:
            faults.append(f"two netlist entries place {cell} at ({x}, {y})")
        exact[key] = path
        by_cell.setdefault(cell, []).append((x, y, path))

    return PicNames(exact, by_cell, tolerance, ratio), faults


def pic_match_report(
    ctx: PadMapContext,
    pic_names: PicNames,
    *,
    globs: Sequence[tuple[str, str]] = (
        ("puc*", r"puc(mua)?\d+"),
        ("lateral_pd_puc*", r"lateral_pd_puc(mua)?\d+"),
    ),
    unmatched_only: bool = True,
) -> list[dict[str, Any]]:
    """Why each component did or did not find its netlist entry.

    Run this when the ``PIC name`` column has ``ERROR`` rows. It puts the
    layout's placement beside the netlist's candidates for the same cell, as
    deltas, which separates the two ways a match can fail: the instance is absent
    from the netlist, or it is present somewhere the layout disagrees with. In
    the second case the delta *is* the disagreement -- a small constant one
    across many components means the netlist is stale, not that anything moved.

    Args:
        ctx: shared context.
        pic_names: from :func:`load_pic_names`.
        globs: ``(glob, regex)`` pairs for the cells to check. The default covers
            PUCs and PDs, which are the rows that carry a PIC name.
        unmatched_only: report only the instances that failed.

    Returns:
        One dict per instance: its cell, computed origin, the nearest netlist
        placements as deltas, and the note explaining the outcome.
    """
    out: list[dict[str, Any]] = []
    for glob, regex in globs:
        for inst in find_instances(ctx.die, glob, name_regex=regex, with_ports=False):
            name, distance, note = pic_names.match(inst.origin_key)
            if unmatched_only and name is not None:
                continue
            nearest = sorted(
                (
                    (math.dist((px, py), inst.origin), px, py, path)
                    for px, py, path in pic_names.by_cell.get(inst.cell, ())
                ),
                key=lambda t: t[0],
            )[:2]
            out.append(
                {
                    "cell": inst.cell,
                    "layout_origin": (
                        round(inst.origin[0], 3),
                        round(inst.origin[1], 3),
                    ),
                    "matched": name,
                    "distance_um": (
                        None if distance == float("inf") else round(distance, 3)
                    ),
                    "note": note,
                    "nearest": [
                        {
                            "dx": round(px - inst.origin[0], 3),
                            "dy": round(py - inst.origin[1], 3),
                            "path": path,
                        }
                        for _, px, py, path in nearest
                    ],
                }
            )
    return out


# --------------------------------------------------------------------------- #
# merge and output
# --------------------------------------------------------------------------- #


def merge_assignments(
    ctx: PadMapContext,
    *sources: dict[int, Assignment],
    unresolved: str = UNRESOLVED,
) -> dict[int, Assignment]:
    """Combine the per-rule assignment dicts into one decision per pad.

    Each rule works independently and none of them can see what the others
    concluded, so the only place a contradiction can be caught is here.  A pad
    two rules both want, with different names, is exactly the "doubt" case that
    was specified to become ``ERROR`` -- and the evidence records which two rules
    disagreed, since that is the part that tells you where to look.

    Two rules agreeing on the same name is not a conflict and is left alone.

    Args:
        ctx: the shared context, for the full pad list.
        *sources: assignment dicts, one per rule, in the order the rules ran.
        unresolved: name for a pad no rule claimed. See :data:`UNRESOLVED` for
            why this is not ``"DUMMY"`` by default.

    Returns:
        One :class:`Assignment` for every pad in ``ctx.pads``.
    """
    merged: dict[int, Assignment] = {}
    for source in sources:
        for idx, incoming in source.items():
            held = merged.get(idx)
            if held is None:
                merged[idx] = incoming
                continue
            if held.name == incoming.name:
                continue
            if held.name == "ERROR" or incoming.name == "ERROR":
                error, other = (
                    (held, incoming) if held.name == "ERROR" else (incoming, held)
                )
                merged[idx] = Assignment(
                    "ERROR",
                    0,
                    f"{error.source}+{other.source}",
                    f"{error.evidence}; also claimed as {other.name}",
                )
                continue
            merged[idx] = Assignment(
                "ERROR",
                0,
                f"{held.source}+{incoming.source}",
                f"claimed as {held.name} by {held.source} and "
                f"{incoming.name} by {incoming.source}",
            )

    for pad in ctx.pads:
        merged.setdefault(
            pad.index, Assignment(unresolved, 0, "", "no rule claimed this pad")
        )
    return merged


def pad_mapping_rows(
    ctx: PadMapContext,
    merged: dict[int, Assignment],
    *,
    decimals: int = 3,
    with_diagnostics: bool = False,
    pic_names: PicNames | None = None,
) -> list[dict[str, Any]]:
    """The spreadsheet rows, ordered by ``PAD_ID``.

    Args:
        ctx: shared context.
        merged: output of :func:`merge_assignments`.
        decimals: rounding for the coordinates, in um.
        with_diagnostics: append the ``source`` and ``evidence`` columns, plus
            ``PIC x_location`` and ``PIC y_location`` -- the serving component's
            own placement, filled only on the rows that carry a PIC name. Off by
            default so the sheet holds only the specified columns; worth turning
            on while ``ERROR`` rows are still being chased down.
        pic_names: from :func:`load_pic_names`. When given, a ``PIC name``
            column is added, filled on ``PUC*`` signal rows only and left blank
            elsewhere -- a ground pad is shared between components, so it has no
            single PIC name. A PUC signal row whose instance is absent from the
            netlist gets ``ERROR`` in this column and keeps its ``name``, so a
            lookup failure stays distinguishable from a naming failure.

    Returns:
        One dict per pad, in ``PAD_ID`` order.
    """
    rows: list[dict[str, Any]] = []
    for pad in sorted(
        ctx.pads, key=lambda p: int(p.pad_id.removeprefix("flipchip_pad"))
    ):
        a = merged.get(pad.index) or Assignment(UNRESOLVED, 0)
        row: dict[str, Any] = {
            "Pad Name": pad.pad_id,
            "X Coord": round(pad.x, decimals),
            "Y Coord": round(pad.y, decimals),
            "Signal/Ground": a.signal_ground,
            "Net name": a.name,
        }
        carries_pic = bool(PIC_NAME_ROW.match(a.name))
        if pic_names is not None:
            row["PIC name"] = (
                (pic_names.get(a.component) or "ERROR") if carries_pic else ""
            )
        if with_diagnostics:
            # the serving component's own position, for the rows that name one.
            # Taken from the component key rather than looked up, so it needs no
            # netlist and is available even when the netlist match failed --
            # which is exactly when it is most useful, since comparing it with
            # the netlist placement is what identifies a stale netlist.
            if carries_pic and a.component is not None:
                row["PIC x_location"] = round(a.component[1] / 1000, decimals)
                row["PIC y_location"] = round(a.component[2] / 1000, decimals)
            else:
                row["PIC x_location"] = ""
                row["PIC y_location"] = ""
            row["source"] = a.source
            row["evidence"] = a.evidence
        rows.append(row)
    return rows


def write_pad_mapping(
    ctx: PadMapContext,
    *sources: dict[int, Assignment],
    path: str = "pad_mapping.xlsx",
    unresolved: str = UNRESOLVED,
    decimals: int = 3,
    diagnostics_sheet: bool = True,
    pic_names: PicNames | None = None,
) -> dict[str, int]:
    """Merge the rule outputs and write the pad mapping spreadsheet.

    Args:
        ctx: shared context.
        *sources: one assignment dict per rule.
        path: output ``.xlsx`` path.
        unresolved: name for unclaimed pads.
        decimals: coordinate rounding, um.
        diagnostics_sheet: also write a ``diagnostics`` sheet carrying the source
            rule and the evidence per pad. The primary sheet keeps only the
            specified columns either way; without this, an ``ERROR`` row gives no
            clue why, which makes a 20k-pad sheet hard to act on.
        pic_names: from :func:`load_pic_names`; adds the ``PIC name`` column.

    Returns:
        A tally by name category: ``{"pads", "named", "error", "unresolved"}``,
        plus ``"pic_missing"`` when ``pic_names`` was given.
    """
    import pandas as pd

    merged = merge_assignments(ctx, *sources, unresolved=unresolved)
    rows = pad_mapping_rows(ctx, merged, decimals=decimals, pic_names=pic_names)

    with pd.ExcelWriter(path, engine="openpyxl") as xls:
        pd.DataFrame(rows).to_excel(xls, sheet_name="pad_mapping", index=False)
        if diagnostics_sheet:
            pd.DataFrame(
                pad_mapping_rows(
                    ctx,
                    merged,
                    decimals=decimals,
                    with_diagnostics=True,
                    pic_names=pic_names,
                )
            ).to_excel(xls, sheet_name="diagnostics", index=False)

    tally = {
        "pads": len(rows),
        "named": sum(1 for r in rows if r["Net name"] not in ("ERROR", unresolved)),
        "error": sum(1 for r in rows if r["Net name"] == "ERROR"),
        "unresolved": sum(1 for r in rows if r["Net name"] == unresolved),
    }
    if pic_names is not None:
        tally["pic_missing"] = sum(1 for r in rows if r.get("PIC name") == "ERROR")
    return tally
