"""Place metal dummies in the gaps between densely packed Si waveguides.

The problem
-----------
The foundry deck fails the waveguide bundles on minimum metal density: over a
band a few hundred microns wide there is Si everywhere and no metal at all.  The
fix the foundry asks for is a column of 1.5 x 1.5 um MT1/MT2 squares dropped
into the channel between two waveguides, repeated every fourth waveguide, so the
density window sees metal without any of it sitting on top of a guide.

What this module is given
-------------------------
A list of axis-aligned rectangles, each covering a band of parallel waveguides
*including* the 90 degree bends where the bundle enters and leaves.  The zone of
parallel guides is not marked -- it is recovered from the geometry.

Algorithm
---------
Every rectangle is handled independently, and the whole rectangle is one
corridor: the waveguides run along the rectangle's long axis, so a rectangle
taller than it is wide is a *vertical* corridor and a wider one is *horizontal*.
There is never a rectangle containing both.

Horizontal corridors are rotated into the vertical frame before anything else
happens, so exactly one code path builds the fill:

1.  Clip Si to the rectangle and merge.  Each surviving polygon is one waveguide.
2.  Take the polygon edges parallel to the corridor.  An edge qualifies as a
    *wall* only if it is at least ``min_wall_length`` long and at least
    ``min_wall_frac`` of the rectangle's length; that is what discards the short
    stubs a bend leaves inside the rectangle, so a guide that only clips a corner
    cannot shift the index of every guide behind it.
3.  Order the waveguides across the corridor -- ascending x for a vertical
    corridor, which is descending y once a horizontal one is rotated back, so the
    first guide is the leftmost or the uppermost as required.
4.  Gap *i* sits between guide *i* and guide *i+1*, and is selected when
    ``(i - 1) % period == 0``: gaps 1-2, 5-6, 9-10 at the default period of 4.
5.  A selected gap is bounded by the facing walls of its two guides.  The dummy
    column is centred between them and runs over the overlap of the two spans,
    which is what stops the column before the bend.
6.  Squares are laid on a ``size + gap`` lattice anchored at the low end of that
    overlap and are kept only if they fall wholly inside
    ``rectangle - Si(+wg_clearance) - keepouts(+keepout_clearance)``.  Because
    the lattice is absolute, a keepout punched through the middle of a column
    removes squares without shifting the ones past it, so the column resumes in
    phase.

Two clearances that look contradictory in a DRC report
------------------------------------------------------
``keepout_clearance`` (5 um by default) applies to the pre-existing MT1/MT2 --
snapshotted before anything is placed -- and is a stay-clear-of-real-routing
margin, not a spacing rule.  Dummy-to-dummy spacing is the foundry's ``gap``
(0.9 um).  The two never collide because the snapshot is taken up front.

Nothing here trusts itself: :func:`verify` re-derives every invariant from the
geometry that was actually written, and :func:`fill_rectangles` always runs it.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

import klayout.db as kdb

__all__ = [
    "DEFAULT_KEEPOUT_LAYERS",
    "DUMMY_CELL_NAME",
    "FillReport",
    "GapResult",
    "DummySpec",
    "LayerSpec",
    "MT1_LAYER",
    "MT2_LAYER",
    "RectangleReport",
    "SI_LAYER",
    "Verification",
    "fill_component",
    "fill_rectangles",
    "verify",
]

LayerSpec = tuple[int, int]
"""A layer as a ``(layer, datatype)`` pair."""

SI_LAYER: LayerSpec = (171, 0)
"""Drawn Si waveguide."""

MT1_LAYER: LayerSpec = (8, 0)
"""First metal, one of the two dummy layers."""

MT2_LAYER: LayerSpec = (18, 0)
"""Second metal, stacked on MT1 with the same footprint and no via."""

DEFAULT_KEEPOUT_LAYERS: tuple[LayerSpec, ...] = (
    (174, 0),
    (259, 0),
    (8, 0),
    (18, 0),
    (118, 131),
)
"""Layers a dummy must stay ``keepout_clearance`` away from.

MT1 and MT2 are in the list on purpose: existing metal repels dummies, and the
snapshot is taken before any dummy is placed so dummies do not repel each other
by this distance.
"""

DUMMY_CELL_NAME = "WG_DUMMY_MT12"
"""Name of the prototype cell holding one MT1 and one MT2 square."""


@dataclass(frozen=True)
class DummySpec:
    """Everything dimensional about the fill, in microns.

    Attributes:
        size: Edge length of the square dummy.
        gap: Edge-to-edge spacing between consecutive dummies in a column, so
            the lattice pitch is ``size + gap``.
        wg_clearance: Smallest allowed distance from a dummy to Si.  Not a
            foundry rule; it exists so a dummy can never touch a guide.
        keepout_clearance: Distance a dummy must keep from every keepout layer.
        period: Fill one gap out of every ``period`` waveguides.
        min_wall_length: Absolute floor on the length of a wall, which discards
            the stubs left by a bend.
        min_wall_frac: A wall must also span this fraction of the rectangle's
            length along the corridor.
        min_overlap_frac: Two facing walls must overlap by this fraction of the
            shorter of the two before their gap is filled.
        si_layer: Waveguide layer.
        dummy_layers: Layers the square is drawn on.
        keepout_layers: Layers to stay clear of.
    """

    size: float = 1.5
    gap: float = 0.9
    wg_clearance: float = 0.1
    keepout_clearance: float = 10.0
    period: int = 4
    min_wall_length: float = 10.0
    min_wall_frac: float = 0.05
    min_overlap_frac: float = 0.30
    si_layer: LayerSpec = SI_LAYER
    dummy_layers: tuple[LayerSpec, ...] = (MT1_LAYER, MT2_LAYER, (8, 31), (18, 31))
    keepout_layers: tuple[LayerSpec, ...] = DEFAULT_KEEPOUT_LAYERS

    def __post_init__(self) -> None:
        """Reject a spec that cannot produce geometry.

        Raises:
            ValueError: If a dimension is not positive or the period is below 1.
        """
        if self.size <= 0:
            raise ValueError(f"size must be positive, got {self.size}")
        if self.gap <= 0:
            raise ValueError(f"gap must be positive, got {self.gap}")
        if self.period < 1:
            raise ValueError(f"period must be >= 1, got {self.period}")
        if self.wg_clearance < 0 or self.keepout_clearance < 0:
            raise ValueError("clearances must not be negative")
        if not self.dummy_layers:
            raise ValueError("at least one dummy layer is required")

    @property
    def pitch(self) -> float:
        """Centre-to-centre spacing of dummies along a column, in um."""
        return self.size + self.gap

    @property
    def min_channel(self) -> float:
        """Narrowest clear channel that can still take a dummy, in um."""
        return self.size + 2.0 * self.wg_clearance


@dataclass
class GapResult:
    """Outcome for one gap between two adjacent waveguides.

    Attributes:
        index: 1-based gap index; gap ``i`` lies between guides ``i`` and
            ``i + 1``, counted across the corridor.
        selected: Whether the period rule chose this gap.
        skipped: Reason the gap was not filled, or ``None`` if it was.
        channel: Clear distance between the two facing walls, in um.
        overlap: Length of the filled run along the corridor, in um.
        placed: Dummies written.
        blocked: Lattice sites dropped because a keepout or the rectangle edge
            cut into them.
    """

    index: int
    selected: bool
    skipped: str | None = None
    channel: float = 0.0
    overlap: float = 0.0
    placed: int = 0
    blocked: int = 0


@dataclass
class RectangleReport:
    """Outcome for one passed rectangle.

    Attributes:
        box: The rectangle, in um.
        orientation: ``"vertical"`` or ``"horizontal"``, from the aspect ratio.
        waveguides: Guides that contributed a qualifying wall.
        ignored: Si polygons with no qualifying wall, discarded before indexing.
        gaps: Every gap, selected or not.
        placed: Dummies written in this rectangle.
        density: Dummy area over rectangle area, per dummy layer.
    """

    box: kdb.DBox
    orientation: str
    waveguides: int
    ignored: int
    gaps: list[GapResult] = field(default_factory=list)
    placed: int = 0
    density: float = 0.0

    @property
    def skipped(self) -> list[GapResult]:
        """Selected gaps that were not filled, with their reasons."""
        return [g for g in self.gaps if g.selected and g.skipped]


@dataclass
class Verification:
    """Invariants re-derived from the geometry that was written.

    Attributes:
        spacing: Dummy pairs closer than ``spec.gap``.
        keepout: Dummies within ``keepout_clearance`` of a keepout.
        waveguide: Dummies within ``wg_clearance`` of Si.
        outside: Dummies not wholly inside a passed rectangle.
        layers_agree: Whether every dummy layer carries the same footprint.
    """

    spacing: int = 0
    keepout: int = 0
    waveguide: int = 0
    outside: int = 0
    layers_agree: bool = True

    def absorb(self, other: Verification) -> None:
        """Fold another rectangle's result into this one.

        Args:
            other: The result to add.
        """
        self.spacing += other.spacing
        self.keepout += other.keepout
        self.waveguide += other.waveguide
        self.outside += other.outside
        self.layers_agree = self.layers_agree and other.layers_agree

    @property
    def ok(self) -> bool:
        """True when every invariant held."""
        return (
            self.spacing == 0
            and self.keepout == 0
            and self.waveguide == 0
            and self.outside == 0
            and self.layers_agree
        )


@dataclass
class FillReport:
    """Result of a whole fill run.

    Attributes:
        rectangles: Per-rectangle detail, in the order they were passed.
        verification: Invariants checked after writing.
        instances: Array instances inserted, one per uninterrupted run.
    """

    rectangles: list[RectangleReport] = field(default_factory=list)
    verification: Verification = field(default_factory=Verification)
    instances: int = 0

    @property
    def placed(self) -> int:
        """Total dummies written."""
        return sum(r.placed for r in self.rectangles)

    @property
    def skipped(self) -> int:
        """Total selected gaps that could not be filled."""
        return sum(len(r.skipped) for r in self.rectangles)

    @property
    def ok(self) -> bool:
        """True when every invariant held."""
        return self.verification.ok


@dataclass(frozen=True)
class _Wall:
    """One face of a waveguide, in the canonical vertical frame, in dbu.

    Attributes:
        u: Position across the corridor.
        v0: Low end along the corridor.
        v1: High end along the corridor.
        outward: ``+1`` when the empty side is at larger ``u``, else ``-1``.
        guide: Index of the owning Si polygon.
    """

    u: int
    v0: int
    v1: int
    outward: int
    guide: int

    @property
    def length(self) -> int:
        """Extent along the corridor, in dbu."""
        return self.v1 - self.v0


@dataclass
class _Run:
    """An uninterrupted stretch of dummies, in die coordinates, in dbu.

    Attributes:
        first: Centre of the first dummy.
        step: Centre-to-centre vector to the next dummy.
        count: Number of dummies.
    """

    first: kdb.Point
    step: kdb.Vector
    count: int


def _as_dbox(box: Any) -> kdb.DBox:
    """Coerce a rectangle into a :class:`klayout.db.DBox` in um.

    Args:
        box: A ``DBox``, a ``Box`` already in um, or a ``(left, bottom, right,
            top)`` sequence.

    Returns:
        The rectangle as a ``DBox``.

    Raises:
        TypeError: If the value is not a recognised rectangle.
        ValueError: If the rectangle is empty.
    """
    if isinstance(box, kdb.DBox):
        out = box
    elif isinstance(box, kdb.Box):
        out = kdb.DBox(
            float(box.left), float(box.bottom), float(box.right), float(box.top)
        )
    elif isinstance(box, Sequence) and len(box) == 4:
        left, bottom, right, top = (float(v) for v in box)
        out = kdb.DBox(left, bottom, right, top)
    else:
        raise TypeError(f"cannot read {box!r} as a rectangle")
    if out.width() <= 0 or out.height() <= 0:
        raise ValueError(f"rectangle {out} is empty")
    return out


def _local_region(
    layout: kdb.Layout,
    cell: kdb.Cell,
    layers: Iterable[LayerSpec],
    box: kdb.Box,
    reach: int = 0,
) -> kdb.Region:
    """Merged shapes on ``layers`` near ``box``, and nothing else.

    Only shapes within ``reach`` of the rectangle can influence a dummy inside
    it, so the query is bounded.  This matters enormously: the die carries
    millions of metal shapes and a whole-die extract followed by a 5 um size
    costs minutes, while the same work over a 3 mm by 64 um strip is
    milliseconds.

    Args:
        layout: Layout owning the cell.
        cell: Top cell to walk.
        layers: Layer/datatype pairs to collect.
        box: Region of interest, in dbu.
        reach: How far outside ``box`` a shape may sit and still matter, in dbu.

    Returns:
        The merged region.  Kept in the caller's scope on purpose: a region
        built from a shape iterator stays bound to its layout.
    """
    query = box.enlarged(reach, reach)
    region = kdb.Region()
    for layer, datatype in layers:
        index = layout.find_layer(layer, datatype)
        if index is None:
            continue
        region += kdb.Region(cell.begin_shapes_rec_touching(index, query))
    return region.merged()


def _canonical(orientation: str) -> kdb.Trans:
    """Transform taking die coordinates into the canonical vertical frame.

    In the canonical frame waveguides always run along ``y`` and are indexed by
    ascending ``x``.  For a horizontal corridor that means a 90 degree rotation,
    which maps ascending canonical ``x`` onto descending die ``y`` -- the
    uppermost guide first, as specified.

    Args:
        orientation: ``"vertical"`` or ``"horizontal"``.

    Returns:
        The transform.

    Raises:
        ValueError: If the orientation is not one of the two.
    """
    if orientation == "vertical":
        return kdb.Trans(kdb.Trans.R0)
    if orientation == "horizontal":
        return kdb.Trans(kdb.Trans.R90)
    raise ValueError(f"unknown orientation {orientation!r}")


def _walls(si: kdb.Region, min_length: int) -> tuple[list[_Wall], int]:
    """Extract the corridor-parallel faces of every waveguide.

    Args:
        si: Merged Si, already clipped to the rectangle and in the canonical
            frame, so a wall is a vertical edge.
        min_length: Shortest edge that may become a wall, in dbu.

    Returns:
        The walls, and the number of Si polygons that produced none.
    """
    walls: list[_Wall] = []
    ignored = 0
    for guide, polygon in enumerate(si.each()):
        found = 0
        for edge in polygon.each_edge():
            if edge.p1.x != edge.p2.x:
                continue
            v0, v1 = sorted((edge.p1.y, edge.p2.y))
            if v1 - v0 < min_length:
                continue
            # A hull edge runs with the interior on one fixed side; probing is
            # cheaper than trusting the winding and immune to it.
            probe = kdb.Point(edge.p1.x + 2, (v0 + v1) // 2)
            outward = -1 if polygon.inside(probe) else 1
            walls.append(_Wall(edge.p1.x, v0, v1, outward, guide))
            found += 1
        if not found:
            ignored += 1
    return walls, ignored


def _order_guides(walls: Sequence[_Wall]) -> list[int]:
    """Order waveguides across the corridor.

    Args:
        walls: Qualifying walls.

    Returns:
        Guide indices sorted by the mean position of their walls, which for a
        straight run is the centre of the run.
    """
    means: dict[int, list[int]] = {}
    for wall in walls:
        means.setdefault(wall.guide, []).append(wall.u)
    return sorted(means, key=lambda g: sum(means[g]) / len(means[g]))


def _facing(walls: Sequence[_Wall], guide: int, outward: int) -> _Wall | None:
    """Pick the wall of ``guide`` that faces into the gap.

    Args:
        walls: Qualifying walls.
        guide: Guide to look at.
        outward: ``+1`` for the face looking at larger ``u``, ``-1`` for smaller.

    Returns:
        The outermost such wall, or ``None`` if the guide has none.
    """
    candidates = [w for w in walls if w.guide == guide and w.outward == outward]
    if not candidates:
        return None
    return max(candidates, key=lambda w: w.u * outward)


def _lattice(v0: int, v1: int, size: int, pitch: int) -> list[int]:
    """Low edges of the whole squares fitting in a span.

    Anchored at ``v0`` so the lattice is absolute: a keepout removes sites
    without moving the ones beyond it.

    Args:
        v0: Low end of the span, in dbu.
        v1: High end of the span, in dbu.
        size: Square edge, in dbu.
        pitch: Centre-to-centre spacing, in dbu.

    Returns:
        The low edge of each site, ascending.
    """
    sites = []
    v = v0
    while v + size <= v1:
        sites.append(v)
        v += pitch
    return sites


def _plan_rectangle(
    box: kdb.DBox,
    si: kdb.Region,
    keepout: kdb.Region,
    spec: DummySpec,
    dbu: float,
) -> tuple[RectangleReport, list[_Run]]:
    """Work out where the dummies go in one rectangle.

    Args:
        box: The rectangle, in um.
        si: Whole-die Si, merged.
        keepout: Whole-die keepouts, merged and already grown.
        spec: Fill dimensions.
        dbu: Database unit in um.

    Returns:
        The report for this rectangle and the runs to instantiate, the latter in
        die coordinates and dbu.
    """
    orientation = "vertical" if box.height() >= box.width() else "horizontal"
    to_canon = _canonical(orientation)
    from_canon = to_canon.inverted()

    frame = box.to_itype(dbu).transformed(to_canon)
    size = int(round(spec.size / dbu))
    pitch = int(round(spec.pitch / dbu))
    channel_min = int(round(spec.min_channel / dbu))
    wall_min = max(
        int(round(spec.min_wall_length / dbu)),
        int(round(spec.min_wall_frac * frame.height())),
    )

    clipped = (si & kdb.Region(box.to_itype(dbu))).merged()
    canon_si = clipped.transformed(to_canon)
    walls, ignored = _walls(canon_si, wall_min)
    order = _order_guides(walls)

    report = RectangleReport(
        box=box, orientation=orientation, waveguides=len(order), ignored=ignored
    )

    allowed = (
        kdb.Region(frame)
        - canon_si.sized(int(round(spec.wg_clearance / dbu)))
        - keepout.transformed(to_canon)
    ).merged()

    runs: list[_Run] = []
    for i in range(1, len(order)):
        selected = (i - 1) % spec.period == 0
        result = GapResult(index=i, selected=selected)
        report.gaps.append(result)
        if not selected:
            continue

        low = _facing(walls, order[i - 1], +1)
        high = _facing(walls, order[i], -1)
        if low is None or high is None:
            result.skipped = "a bounding wall is missing"
            continue
        if high.u <= low.u:
            result.skipped = "walls do not bound an open channel"
            continue

        result.channel = (high.u - low.u) * dbu
        v0, v1 = max(low.v0, high.v0), min(low.v1, high.v1)
        result.overlap = max(0, v1 - v0) * dbu
        shorter = min(low.length, high.length)
        if v1 - v0 < spec.min_overlap_frac * shorter:
            result.skipped = (
                f"walls overlap over {result.overlap:.2f} um, under "
                f"{spec.min_overlap_frac:.0%} of the shorter wall "
                f"({shorter * dbu:.2f} um)"
            )
            continue
        if high.u - low.u < channel_min:
            result.skipped = (
                f"channel is {result.channel:.3f} um, under the "
                f"{spec.min_channel:.3f} um a dummy needs"
            )
            continue

        centre = (low.u + high.u) // 2
        sites = _lattice(v0, v1, size, pitch)
        if not sites:
            result.skipped = f"run of {result.overlap:.2f} um holds no whole dummy"
            continue

        candidates = kdb.Region()
        for v in sites:
            candidates.insert(
                kdb.Box(centre - size // 2, v, centre - size // 2 + size, v + size)
            )
        kept = {p.bbox().bottom for p in candidates.inside(allowed).each()}
        result.placed = len(kept)
        result.blocked = len(sites) - len(kept)

        step = from_canon * kdb.Vector(0, pitch)
        run: list[int] = []
        for v in sites + [None]:  # type: ignore[list-item]
            if v is not None and v in kept:
                run.append(v)
                continue
            if run:
                centre_pt = from_canon * kdb.Point(centre, run[0] + size // 2)
                runs.append(_Run(centre_pt, step, len(run)))
                run = []

    report.placed = sum(r.count for r in runs)
    area = box.width() * box.height()
    report.density = report.placed * spec.size * spec.size / area if area else 0.0
    return report, runs


def _prototype(layout: kdb.Layout, spec: DummySpec, name: str) -> kdb.Cell:
    """Fetch or build the single-dummy cell.

    Args:
        layout: Layout to hold the cell.
        spec: Fill dimensions.
        name: Cell name; an existing cell of that name is reused.

    Returns:
        A cell holding one square per dummy layer, centred on the origin.
    """
    existing = layout.cell(name)
    if existing is not None:
        return existing
    cell = layout.create_cell(name)
    half = spec.size / 2.0
    box = kdb.DBox(-half, -half, half, half)
    for layer, datatype in spec.dummy_layers:
        cell.shapes(layout.layer(layer, datatype)).insert(box)
    return cell


def verify(
    added: Sequence[kdb.Region],
    rectangles: Sequence[kdb.DBox],
    si: kdb.Region,
    keepout: kdb.Region,
    spec: DummySpec,
    dbu: float,
) -> Verification:
    """Re-derive every invariant from the geometry that was written.

    Only the geometry this run added is checked.  Pre-existing metal is not,
    since a die under repair may hold violations that are not ours and a
    verification that inherited them could never pass.

    Args:
        added: What this run put on each dummy layer, in ``spec.dummy_layers``
            order and already merged.
        rectangles: The rectangles that were passed in.
        si: Whole-die Si, merged.
        keepout: Whole-die keepouts, merged and already grown.
        spec: Fill dimensions.
        dbu: Database unit in um.

    Returns:
        The counts; :attr:`Verification.ok` is true when all are zero.
    """
    out = Verification()
    dummies = added[0]
    out.spacing = dummies.space_check(int(round(spec.gap / dbu))).size()
    out.keepout = dummies.interacting(keepout).count()
    grown_si = si.sized(int(round(spec.wg_clearance / dbu)))
    out.waveguide = dummies.interacting(grown_si).count()
    frame = kdb.Region()
    for box in rectangles:
        frame.insert(box.to_itype(dbu))
    out.outside = dummies.not_inside(frame.merged()).count()
    for other in added[1:]:
        if not (dummies ^ other).is_empty():
            out.layers_agree = False
    return out


def fill_rectangles(
    layout: kdb.Layout,
    cell: kdb.Cell,
    rectangles: Iterable[Any],
    spec: DummySpec | None = None,
    cell_name: str = DUMMY_CELL_NAME,
) -> FillReport:
    """Fill every rectangle with dummy columns and verify the result.

    Args:
        layout: Layout to modify.
        cell: Top cell the dummies are inserted into.
        rectangles: Axis-aligned rectangles in um, each a ``DBox`` or a
            ``(left, bottom, right, top)`` sequence.
        spec: Fill dimensions; the defaults are the v7b numbers.
        cell_name: Name for the prototype cell.

    Returns:
        The report, including the verification.

    Raises:
        ValueError: If a rectangle is malformed, or if verification fails --
            geometry is left in place so it can be inspected.
    """
    spec = spec or DummySpec()
    dbu = layout.dbu
    boxes = [_as_dbox(b) for b in rectangles]
    keepout_reach = int(round(spec.keepout_clearance / dbu)) + 1
    wg_reach = int(round(spec.wg_clearance / dbu)) + 1

    # Everything each rectangle needs is gathered before anything is inserted,
    # so a dummy in one rectangle never becomes a 5 um keepout for the next.
    contexts = []
    for box in boxes:
        frame = box.to_itype(dbu)
        si = _local_region(layout, cell, [spec.si_layer], frame, wg_reach)
        keepout = _local_region(
            layout, cell, spec.keepout_layers, frame, keepout_reach
        ).sized(int(round(spec.keepout_clearance / dbu)))
        before = [
            _local_region(layout, cell, [layer], frame) for layer in spec.dummy_layers
        ]
        contexts.append((frame, si, keepout, before))

    report = FillReport()
    plans: list[list[_Run]] = []
    for box, (_, si, keepout, _) in zip(boxes, contexts):
        rect_report, runs = _plan_rectangle(box, si, keepout, spec, dbu)
        report.rectangles.append(rect_report)
        plans.append(runs)

    if any(plans):
        prototype = _prototype(layout, spec, cell_name)
        for runs in plans:
            for run in runs:
                cell.insert(
                    kdb.CellInstArray(
                        prototype.cell_index(),
                        kdb.Trans(kdb.Vector(run.first.x, run.first.y)),
                        run.step,
                        kdb.Vector(0, 0),
                        run.count,
                        1,
                    )
                )
                report.instances += 1

    for box, (frame, si, keepout, before) in zip(boxes, contexts):
        added = [
            (_local_region(layout, cell, [layer], frame) - was).merged()
            for layer, was in zip(spec.dummy_layers, before)
        ]
        report.verification.absorb(verify(added, [box], si, keepout, spec, dbu))
    report.verification = verify(added, boxes, si, keepout, spec, dbu)
    if not report.verification.ok:
        raise ValueError(f"verification failed: {report.verification}")
    return report


def fill_component(
    component: Any,
    rectangles: Iterable[Any],
    spec: DummySpec | None = None,
    cell_name: str = DUMMY_CELL_NAME,
) -> FillReport:
    """Fill a live gdsfactory component in place.

    Args:
        component: A ``gdsfactory.Component``; its own cell is modified.
        rectangles: Axis-aligned rectangles in um.
        spec: Fill dimensions.
        cell_name: Name for the prototype cell.

    Returns:
        The report, including the verification.
    """
    return fill_rectangles(
        component.kcl.layout, component.kdb_cell, rectangles, spec, cell_name
    )
