"""Fill the acute metal notches where a route enters a chamfered flip-chip pad.

The problem
-----------
A routing band meets an octagonal pad on one of its 45 degree chamfer faces.
The band's own edge is axis aligned, so the two edges converge at 45 degrees and
the wedge of empty space between them pinches to zero.  The metal is continuous
through the apex -- this is not a broken connection -- but the DRC deck measures
minimum spacing with acute edge pairs included, so the wedge is reported as a
spacing violation wherever the two edges come within ``distance`` of each other.

The fix
-------
Fill the wedge back from the apex far enough that the two surviving edges are no
longer within ``distance``.  Two facts drive the geometry:

*   **How far back.**  For a 45 degree wedge the perpendicular gap at an offset
    ``a`` from the apex is ``a / sqrt(2)``, so clearing a ``d`` micron rule needs
    ``a >= d * sqrt(2)``.  At the usual ``d = 2`` that is 2.829 um, which is why
    the checker reports edges exactly 2828 dbu long.  ``DEFAULT_DEPTH`` adds
    margin on top.

*   **What shape.**  Cutting a 45 degree wedge with a straight line always
    produces two corners summing to 225 degrees, so a single cut perpendicular to
    one of the two edges gives 90 and 135 and nothing sharper.  More than one cut
    segment is strictly worse -- the sum is 225 however many segments you use, so
    three corners average 75.  A rectangle achieves the single perpendicular cut
    only if its three other edges are *buried* inside existing metal; otherwise
    they cross the wedge a second time and regenerate a 45 degree corner a few
    microns away.  :func:`patch_die` verifies burial and falls back to the right
    triangle, whose two remaining sides lie exactly on the existing metal edges
    and so can never stick out.

Canonical frame
---------------
Every site is reduced to one orientation before the patch is built::

    apex at the origin
    band metal  = {y < 0}, its exposed edge running in -x
    pad metal   = {y > -x}, its exposed edge running in (-1, +1)
    empty wedge = {0 < y < -x}

The eight dihedral images of that frame cover every way a band can meet a
chamfer, so one prototype cell plus a ``kdb.Trans`` serves the whole die.

Verification is not optional here and :func:`patch_die` always runs it: the same
``space_check`` that found the sites must return nothing afterwards, and the
merged polygon count must be unchanged, since a patch that lowered it would have
bridged two nets that were previously separate.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

import klayout.db as kdb

__all__ = [
    "DEFAULT_DEPTH",
    "PatchReport",
    "Site",
    "canonical_transforms",
    "find_sites",
    "min_depth_for",
    "patch_die",
    "verify",
]

DEFAULT_DISTANCE = 2.0
"""Spacing rule in um, as measured by the deck (rule 28.S.1 is 2.00 um)."""

DEFAULT_DEPTH = 3.0
"""How far back from the apex the wedge is filled, in um.

Must exceed ``distance * sqrt(2)`` (2.829 um at the 2 um rule).  The default
leaves the two surviving edges 3.0 um apart against a 2.0 um requirement.
"""

DEFAULT_BURY = 0.5
"""Overshoot in um past the apex, into metal, on the two buried sides."""

DEFAULT_CLEAR = 1.0
"""Extra depth in um beyond ``depth`` on the fourth side.

The rectangle's far edge must clear the chamfer over the whole width of the
patch, which needs strictly more than ``depth``; this is that margin.
"""


def min_depth_for(distance: float = DEFAULT_DISTANCE) -> float:
    """Smallest fill depth that clears a spacing rule on a 45 degree wedge.

    Args:
        distance: The spacing rule in um.

    Returns:
        The minimum depth in um, ``distance * sqrt(2)``.
    """
    return distance * math.sqrt(2.0)


@dataclass(frozen=True)
class Site:
    """One acute notch, reduced to the canonical frame.

    Attributes:
        apex: Where the two edges' infinite lines meet, in dbu.  Always on grid
            for an axis-aligned/45 degree pair.
        trans: The dihedral element mapping the canonical frame onto this site,
            including the translation to ``apex``.
        axis_edge: The axis-aligned edge of the reported pair, in dbu.
        diag_edge: The 45 degree edge of the reported pair, in dbu.
    """

    apex: kdb.Point
    trans: kdb.Trans
    axis_edge: kdb.Edge
    diag_edge: kdb.Edge


@dataclass
class PatchReport:
    """Outcome of a :func:`patch_die` run.

    Attributes:
        sites: Every acute notch found.
        fallback: Indices into ``sites`` that fell back to the right triangle
            because a rectangle would not have been fully buried.
        unhandled: Edge pairs that were not an axis-aligned/45 degree wedge and
            so were left alone.  Should be empty; anything here needs looking at
            by hand before tape-out.
        remaining: Sites still reported by ``space_check`` after patching.  Must
            be empty.
        polygons_before: Merged polygon count on the layer before patching.
        polygons_after: Merged polygon count after.  A drop means a patch
            bridged two previously separate nets.
    """

    sites: list[Site]
    fallback: set[int]
    unhandled: list[kdb.EdgePair]
    remaining: list[kdb.EdgePair]
    polygons_before: int
    polygons_after: int

    @property
    def rectangles(self) -> int:
        """How many sites were patched with a rectangle."""
        return len(self.sites) - len(self.fallback)

    @property
    def triangles(self) -> int:
        """How many sites fell back to the triangle."""
        return len(self.fallback)

    def shape_of(self, index: int) -> str:
        """Which prototype was placed at ``sites[index]``.

        Args:
            index: Index into ``sites``.

        Returns:
            Either ``"rect"`` or ``"tri"``.
        """
        return "tri" if index in self.fallback else "rect"

    @property
    def clean(self) -> bool:
        """True if every invariant held."""
        return (
            not self.unhandled
            and not self.remaining
            and self.polygons_before == self.polygons_after
        )

    def __str__(self) -> str:
        """Render the report as an aligned summary block."""
        lines = [
            f"sites            {len(self.sites)}",
            f"  rectangles     {self.rectangles}",
            f"  triangles      {self.triangles}",
            f"  unhandled      {len(self.unhandled)}",
            f"remaining        {len(self.remaining)}",
            f"polygons         {self.polygons_before} -> {self.polygons_after}",
            f"clean            {self.clean}",
        ]
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# frame handling
# --------------------------------------------------------------------------- #

_CANON_AXIS = kdb.Vector(-1, 0)
"""Direction the band's exposed edge runs, from the apex, in canonical frame."""

_CANON_DIAG = kdb.Vector(-1, 1)
"""Direction the chamfer's exposed edge runs, from the apex, canonical frame."""


def canonical_transforms() -> list[kdb.Trans]:
    """The eight dihedral elements, as rotation/mirror pairs with no shift."""
    return [
        kdb.Trans(rot, mirror, 0, 0) for mirror in (False, True) for rot in range(4)
    ]


def _layer_index(layout: kdb.Layout, layer: Any) -> int:
    """Resolve a layer spec to a layer index in ``layout``.

    Args:
        layout: The layout to resolve against.
        layer: An index, a ``(layer, datatype)`` pair, or a ``kdb.LayerInfo``.

    Returns:
        The layer index.

    Raises:
        TypeError: If the spec cannot be interpreted.
    """
    if isinstance(layer, int):
        return layer
    if isinstance(layer, kdb.LayerInfo):
        return layout.layer(layer)
    if isinstance(layer, tuple | list) and len(layer) == 2:
        return layout.layer(kdb.LayerInfo(int(layer[0]), int(layer[1])))
    raise TypeError(f"cannot resolve layer spec {layer!r}")


def _kdb_cell(cell: Any) -> kdb.Cell:
    """Return the underlying ``klayout.db.Cell`` of a gdsfactory/kfactory cell.

    Args:
        cell: A ``klayout.db.Cell``, or anything exposing one as ``kdb_cell``.

    Returns:
        The KLayout cell.

    Raises:
        TypeError: If no cell can be found.
    """
    if isinstance(cell, kdb.Cell):
        return cell
    for attr in ("kdb_cell", "_kdb_cell"):
        inner = getattr(cell, attr, None)
        if isinstance(inner, kdb.Cell):
            return inner
    raise TypeError(f"cannot get a klayout Cell from {type(cell).__name__!r}")


def _unit(vector: kdb.Vector) -> tuple[int, int]:
    """Reduce a vector to the smallest integer pair with the same direction.

    Args:
        vector: Any non-zero vector in dbu.

    Returns:
        ``(dx, dy)`` with the common factor divided out.
    """
    g = math.gcd(abs(vector.x), abs(vector.y)) or 1
    return (vector.x // g, vector.y // g)


def _outward(edge: kdb.Edge, apex: kdb.Point) -> kdb.Vector:
    """Direction in which ``edge`` runs away from ``apex``.

    The reported segments are clipped to the region where the two edges are
    within the rule distance, so an edge does not necessarily start at the apex.
    Taking the farther endpoint is correct either way.

    Args:
        edge: One edge of the reported pair.
        apex: The wedge apex.

    Returns:
        A vector from the apex towards the far end of the edge.
    """
    d1, d2 = apex.distance(edge.p1), apex.distance(edge.p2)
    far = edge.p2 if d2 >= d1 else edge.p1
    return far - apex


def _intersect(a: kdb.Edge, b: kdb.Edge) -> kdb.Point | None:
    """Intersection of the two edges' infinite lines, rounded to dbu.

    Args:
        a: First edge.
        b: Second edge.

    Returns:
        The intersection point, or None if the lines are parallel.
    """
    ax, ay = a.d().x, a.d().y
    bx, by = b.d().x, b.d().y
    det = ax * by - ay * bx
    if det == 0:
        return None
    dx, dy = b.p1.x - a.p1.x, b.p1.y - a.p1.y
    t = (dx * by - dy * bx) / det
    return kdb.Point(round(a.p1.x + t * ax), round(a.p1.y + t * ay))


def _classify(pair: kdb.EdgePair) -> Site | None:
    """Reduce one reported edge pair to a :class:`Site`.

    Pairs that are not an axis-aligned edge meeting a 45 degree edge are
    rejected rather than guessed at.

    Args:
        pair: An edge pair from ``Region.space_check``.

    Returns:
        The site, or None if the pair does not match the expected motif.
    """
    e1, e2 = pair.first, pair.second
    apex = _intersect(e1, e2)
    if apex is None:
        return None

    dirs = [_unit(_outward(e, apex)) for e in (e1, e2)]
    axis = [d for d in dirs if 0 in d]
    diag = [d for d in dirs if abs(d[0]) == abs(d[1]) != 0]
    if len(axis) != 1 or len(diag) != 1:
        return None

    for trans in canonical_transforms():
        if (
            _unit(trans * _CANON_AXIS) == axis[0]
            and _unit(trans * _CANON_DIAG) == diag[0]
        ):
            placed = kdb.Trans(kdb.Vector(apex.x, apex.y)) * trans
            axis_edge = e1 if 0 in dirs[0] else e2
            diag_edge = e2 if 0 in dirs[0] else e1
            return Site(apex, placed, axis_edge, diag_edge)
    return None


# --------------------------------------------------------------------------- #
# finding
# --------------------------------------------------------------------------- #


def _flat_region(cell: kdb.Cell, layer_index: int) -> kdb.Region:
    """Merged, layout-independent region for a layer under ``cell``.

    ``begin_shapes_rec`` yields a deep region bound to its parent layout, which
    reads as empty once that layout leaves scope; merging materialises it.

    Args:
        cell: Top cell to collect from.
        layer_index: Layer to collect.

    Returns:
        A flat merged region in dbu.
    """
    return kdb.Region(cell.begin_shapes_rec(layer_index)).merged()


def find_sites(
    cell: Any,
    layer: Any,
    distance: float = DEFAULT_DISTANCE,
) -> tuple[list[Site], list[kdb.EdgePair]]:
    """Locate every acute notch on ``layer``.

    Runs the same measurement the deck runs: a minimum-spacing check with acute
    edge pairs included.  Corners of 90 degrees or more are excluded by
    ``ignore_angle``, which is why an ordinary rectangle corner is not reported.

    Args:
        cell: Top cell (``klayout.db.Cell`` or a gdsfactory/kfactory wrapper).
        layer: Layer spec, e.g. ``(28, 0)``.
        distance: The spacing rule in um.

    Returns:
        ``(sites, unhandled)`` -- the notches that matched the axis/45 motif,
        and any reported pair that did not.
    """
    kcell = _kdb_cell(cell)
    layout = kcell.layout()
    region = _flat_region(kcell, _layer_index(layout, layer))
    pairs = region.space_check(
        round(distance / layout.dbu), False, kdb.Region.Euclidian, 90, None, None
    )

    sites: list[Site] = []
    unhandled: list[kdb.EdgePair] = []
    for pair in pairs.each():
        site = _classify(pair)
        if site is None:
            unhandled.append(pair)
        else:
            sites.append(site)
    return sites, unhandled


# --------------------------------------------------------------------------- #
# patch geometry
# --------------------------------------------------------------------------- #


def _prototypes(
    dbu: float, depth: float, bury: float, clear: float
) -> tuple[kdb.Polygon, kdb.Polygon]:
    """Rectangle and triangle prototypes in the canonical frame, in dbu.

    The rectangle's only exposed edge is the one at ``x = -depth``, running from
    the band edge up to the chamfer; the other three sit inside existing metal.
    The triangle's two other sides lie exactly along the existing edges, so it is
    buried unconditionally and serves as the fallback.

    Args:
        dbu: Database unit in um.
        depth: Fill depth back from the apex, in um.
        bury: Overshoot past the apex into metal, in um.
        clear: Extra depth beyond ``depth`` on the far side, in um.

    Returns:
        ``(rectangle, triangle)`` as polygons in dbu.
    """
    a = round(depth / dbu)
    b = round(bury / dbu)
    d = a + round(clear / dbu)
    rect = kdb.Polygon(kdb.Box(-a, -b, b, d))
    tri = kdb.Polygon([kdb.Point(0, 0), kdb.Point(-a, 0), kdb.Point(-a, a)])
    return rect, tri


def _overflowing(
    sites: Sequence[Site],
    metal: kdb.Region,
    rect: kdb.Polygon,
    tri: kdb.Polygon,
) -> set[int]:
    """Indices of sites whose rectangle would not be fully buried.

    Computed as one global boolean rather than per site: the metal a rectangle
    adds must lie inside the wedge triangle, so anything left over after
    subtracting existing metal and the triangles is a rectangle sticking out.
    On a clean die that leftover is empty and no site is touched.

    Args:
        sites: The sites to test.
        metal: Existing merged metal, in dbu.
        rect: Rectangle prototype, canonical frame.
        tri: Triangle prototype, canonical frame.

    Returns:
        The set of offending indices into ``sites``.
    """
    rects = kdb.Region([rect.transformed(s.trans) for s in sites])
    tris = kdb.Region([tri.transformed(s.trans) for s in sites])
    overflow = (rects - metal) - tris
    if overflow.is_empty():
        return set()
    return {
        i
        for i, s in enumerate(sites)
        if not (kdb.Region(rect.transformed(s.trans)) & overflow).is_empty()
    }


# --------------------------------------------------------------------------- #
# top level
# --------------------------------------------------------------------------- #


def patch_die(
    cell: Any,
    layer: Any,
    distance: float = DEFAULT_DISTANCE,
    depth: float = DEFAULT_DEPTH,
    bury: float = DEFAULT_BURY,
    clear: float = DEFAULT_CLEAR,
    cell_name: str = "MT3_ACUTE_PATCH",
) -> PatchReport:
    """Find and fill every acute notch on ``layer``, then verify the result.

    Patches are written as instances of two prototype cells inside one container
    cell placed in ``cell``, so the whole fix can be reviewed -- or deleted -- as
    a single object, and so several thousand sites cost a few hundred bytes.

    Args:
        cell: Top cell to patch, modified in place.
        layer: Layer spec, e.g. ``(28, 0)``.
        distance: The spacing rule in um.
        depth: Fill depth back from the apex, in um.  Must exceed
            ``min_depth_for(distance)``.
        bury: Overshoot past the apex into metal, in um.
        clear: Extra depth beyond ``depth`` on the far side, in um.
        cell_name: Name of the container cell holding the patches.

    Returns:
        A :class:`PatchReport`.  Check ``report.clean`` before shipping.

    Raises:
        ValueError: If ``depth`` is too small to clear ``distance``.
    """
    need = min_depth_for(distance)
    if depth <= need:
        raise ValueError(
            f"depth={depth} um cannot clear a {distance} um rule on a 45 degree "
            f"wedge; needs more than {need:.4f} um"
        )

    kcell = _kdb_cell(cell)
    layout = kcell.layout()
    layer_index = _layer_index(layout, layer)
    dbu = layout.dbu

    metal_before = _flat_region(kcell, layer_index)
    polygons_before = metal_before.count()

    sites, unhandled = find_sites(kcell, layer, distance)
    rect, tri = _prototypes(dbu, depth, bury, clear)
    fallback = _overflowing(sites, metal_before, rect, tri)

    container = layout.create_cell(cell_name)
    proto_rect = layout.create_cell(f"{cell_name}_RECT")
    proto_tri = layout.create_cell(f"{cell_name}_TRI")
    proto_rect.shapes(layer_index).insert(rect)
    proto_tri.shapes(layer_index).insert(tri)

    for i, site in enumerate(sites):
        proto = proto_tri if i in fallback else proto_rect
        container.insert(kdb.CellInstArray(proto.cell_index(), site.trans))
    kcell.insert(kdb.CellInstArray(container.cell_index(), kdb.Trans()))

    metal_after = _flat_region(kcell, layer_index)
    remaining = verify(kcell, layer, distance)
    return PatchReport(
        sites=sites,
        fallback=fallback,
        unhandled=unhandled,
        remaining=remaining,
        polygons_before=polygons_before,
        polygons_after=metal_after.count(),
    )


def verify(
    cell: Any, layer: Any, distance: float = DEFAULT_DISTANCE
) -> list[kdb.EdgePair]:
    """Re-run the spacing check and return whatever is still reported.

    Args:
        cell: Top cell.
        layer: Layer spec.
        distance: The spacing rule in um.

    Returns:
        The surviving edge pairs; empty on a clean die.
    """
    kcell = _kdb_cell(cell)
    layout = kcell.layout()
    region = _flat_region(kcell, _layer_index(layout, layer))
    pairs = region.space_check(
        round(distance / layout.dbu), False, kdb.Region.Euclidian, 90, None, None
    )
    return list(pairs.each())


def patch_boxes(sites: Iterable[Site], dbu: float) -> list[tuple[float, float]]:
    """Patch centres in um, for the CSV the foundry will review.

    Args:
        sites: The patched sites.
        dbu: Database unit in um.

    Returns:
        ``(x, y)`` of each apex, in um.
    """
    return [(s.apex.x * dbu, s.apex.y * dbu) for s in sites]
