"""Place a border (ring) of identical rectangles just inside the die edge.

The border is built as four independent *runs* (N, E, S, W).  Each run is a
fixed-pitch lattice of identical rectangles whose long axis follows the die
edge, so the same ``size`` is reused on every side (auto-rotated by 90 deg on
the vertical runs).

By default the vertical runs (W/E) own the corners and the horizontal runs
(N/S) are inset by ``width + separation`` so nothing overlaps::

    +---------------------------------------------+  <- die bbox
    |                                             |
    |   []   [][][][][][][][][][][][][][]   []    |  <- N run (inset)
    |   []                                  []    |
    |   []          <- border_separation    []    |
    |   []                                  []    |
    |   []   [][][][][][][][][][][][][][]   []    |  <- S run (inset)
    |                                             |
    +---------------------------------------------+
      ^ W run owns the corner        ^ E run owns the corner

Slots that fall within ``keepout_distance`` of any shape on ``keepout_layers``
are skipped *without* shifting the lattice, so indices and positions of every
other rectangle are unaffected (phase-preserving skip).  Skipped slots are
still reported in the result with ``placed=False`` so the blocked positions
stay addressable.

Works with a ``gdsfactory.Component``, a ``kfactory.KCell`` or a raw
``klayout.db.Cell``.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

import klayout.db as kdb

__all__ = ["BorderRect", "border_rectangles"]


# --------------------------------------------------------------------------- #
# result type
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class BorderRect:
    """One lattice slot of a border run.

    Attributes:
        side: ``"N"``, ``"E"``, ``"S"`` or ``"W"``.
        index: Position along the run, counted from the lattice origin.
            Horizontal runs are indexed left -> right, vertical runs
            bottom -> top.  Indices are *never* renumbered when a slot is
            skipped, so ``index`` is a stable address into the lattice.
        box: Slot geometry in um (whether or not it was placed).
        placed: True if the rectangle was written to the die.
        blocked_by_keepout: True if the slot was skipped because of a keepout.
        end_fill: True for a shortened rectangle added by ``end_fill="fill"``
            to consume the slack at the end of a run.
    """

    side: str
    index: int
    box: kdb.DBox
    placed: bool
    blocked_by_keepout: bool = False
    end_fill: bool = False

    @property
    def center(self) -> kdb.DPoint:
        return self.box.center()


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
_SIDE_ALIASES = {
    "n": "N",
    "north": "N",
    "top": "N",
    "t": "N",
    "up": "N",
    "e": "E",
    "east": "E",
    "right": "E",
    "r": "E",
    "s": "S",
    "south": "S",
    "bottom": "S",
    "b": "S",
    "down": "S",
    "w": "W",
    "west": "W",
    "left": "W",
    "l": "W",
}
_HORIZONTAL = ("N", "S")
_VERTICAL = ("W", "E")
_ALL_SIDES = ("N", "E", "S", "W")


def _kdb_cell(die: Any) -> kdb.Cell:
    """Return the underlying ``klayout.db.Cell`` of a gdsfactory/kfactory cell."""
    if isinstance(die, kdb.Cell):
        return die
    for attr in ("kdb_cell", "_kdb_cell"):
        cell = getattr(die, attr, None)
        if isinstance(cell, kdb.Cell):
            return cell
    raise TypeError(
        f"cannot get a klayout Cell from {type(die).__name__!r}; pass a "
        "gdsfactory Component, kfactory KCell or klayout.db.Cell"
    )


def _layer_index(layout: kdb.Layout, layer: Any) -> int:
    """Resolve a layer spec to a layer index in ``layout``."""
    if isinstance(layer, int):  # LayerEnum is an int subclass -> already an index
        return int(layer)
    if isinstance(layer, kdb.LayerInfo):
        return layout.layer(layer)
    try:  # let the active PDK resolve names / (layer, datatype) tuples
        import gdsfactory as gf

        return int(gf.get_layer(layer))
    except Exception:
        pass
    if isinstance(layer, tuple | list) and len(layer) == 2:
        return layout.layer(kdb.LayerInfo(int(layer[0]), int(layer[1])))
    if isinstance(layer, str):
        return layout.layer(kdb.LayerInfo(layer))
    raise TypeError(f"cannot resolve layer spec {layer!r}")


def _normalize_sides(sides: Iterable[str]) -> tuple[str, ...]:
    out: list[str] = []
    for side in sides:
        key = str(side).strip().lower()
        norm = _SIDE_ALIASES.get(key)
        if norm is None:
            raise ValueError(f"unknown side {side!r}; use N/E/S/W")
        if norm not in out:
            out.append(norm)
    return tuple(s for s in _ALL_SIDES if s in out)  # canonical N, E, S, W order


def _dbu(value: float, dbu: float) -> int:
    return int(round(float(value) / dbu))


def _is_coord_quad(obj: Any) -> bool:
    """True for a plain ``(x1, y1, x2, y2)`` sequence of numbers."""
    return (
        isinstance(obj, tuple | list)
        and len(obj) == 4
        and all(isinstance(v, int | float) and not isinstance(v, bool) for v in obj)
    )


def _as_dbox(spec: Any, dbu: float) -> kdb.DBox:
    """Coerce a box spec to a ``kdb.DBox`` (um) without losing precision."""
    if isinstance(spec, kdb.DBox):
        return spec  # NB: kdb.DBox(DBox) picks the integer ctor and truncates
    if isinstance(spec, kdb.Box):
        return spec.to_dtype(dbu)
    if _is_coord_quad(spec):
        return kdb.DBox(*(float(v) for v in spec))
    raise TypeError(
        f"cannot interpret {spec!r} as a box; pass a kdb.DBox, kdb.Box or "
        "(x1, y1, x2, y2) in um"
    )


def _insert_keepout_item(region: kdb.Region, item: Any, dbu: float) -> None:
    """Insert one keepout item (um or dbu geometry, or a coord quad) in dbu."""
    if isinstance(item, kdb.Region):
        region.insert(item)
    elif _is_coord_quad(item):
        region.insert(kdb.DBox(*(float(v) for v in item)).to_itype(dbu))
    elif isinstance(item, kdb.DBox | kdb.DPolygon | kdb.DSimplePolygon | kdb.DPath):
        region.insert(item.to_itype(dbu))
    elif isinstance(item, kdb.Box | kdb.Polygon | kdb.SimplePolygon | kdb.Path):
        region.insert(item)
    else:
        raise TypeError(f"cannot interpret {item!r} as keepout geometry")


def _keepout_region(
    cell: kdb.Cell,
    layout: kdb.Layout,
    keepout_layers: Iterable[Any],
    extra_keepout: Any,
    distance_dbu: int,
) -> kdb.Region:
    """Merged, over-sized keepout region in dbu (flat, not layout-bound)."""
    region = kdb.Region()
    for spec in keepout_layers:
        region.insert(cell.begin_shapes_rec(_layer_index(layout, spec)))
    region = region.merged()  # materialize now: deep regions die with the layout

    if extra_keepout is not None:
        single = isinstance(
            extra_keepout,
            kdb.Region
            | kdb.Box
            | kdb.DBox
            | kdb.Polygon
            | kdb.DPolygon
            | kdb.SimplePolygon
            | kdb.DSimplePolygon
            | kdb.Path
            | kdb.DPath,
        ) or _is_coord_quad(extra_keepout)
        items = [extra_keepout] if single else list(extra_keepout)
        extra = kdb.Region()
        for item in items:
            _insert_keepout_item(extra, item, layout.dbu)
        region += extra
        region = region.merged()

    if distance_dbu and not region.is_empty():
        region = region.sized(distance_dbu).merged()
    return region


def _lattice(span: int, length: int, separation: int, align: str) -> tuple[int, int]:
    """Return ``(count, start_offset)`` for a fixed-pitch run of ``span`` dbu."""
    if span < length:
        return 0, 0
    pitch = length + separation
    count = (span + separation) // pitch if pitch > 0 else 1
    if align == "start":
        return count, 0
    used = count * length + (count - 1) * separation
    return count, (span - used) // 2


# --------------------------------------------------------------------------- #
# main entry point
# --------------------------------------------------------------------------- #
def border_rectangles(
    die: Any,
    layer: Any,
    size: tuple[float, float] = (20.0, 5.0),
    border_separation: float = 10.0,
    separation: float = 2.0,
    sides: Sequence[str] = ("N", "E", "S", "W"),
    keepout_layers: Sequence[Any] = (),
    keepout_distance: float = 0.0,
    extra_keepout: Any = None,
    die_bbox: kdb.DBox | None = None,
    corner_owner: str = "vertical",
    align: str = "start",
    end_fill: str = "none",
    min_end_length: float | None = None,
) -> dict[str, list[BorderRect]]:
    """Draw a border of identical rectangles just inside the die edge.

    Args:
        die: Cell to draw into (gdsfactory Component, kfactory KCell or
            ``klayout.db.Cell``).
        layer: Layer for the rectangles (index, ``(layer, datatype)``, name or
            ``kdb.LayerInfo``).
        size: ``(length_along_run, width_across_run)`` in um.  The long axis
            always follows the die edge, i.e. the rectangle is rotated 90 deg
            on the W/E runs.
        border_separation: Distance in um from the die edge to the outer edge
            of the rectangles (edge to edge).
        separation: Gap in um between consecutive rectangles of a run, and
            between a horizontal run and the corner-owning vertical run.
        sides: Any subset of ``("N", "E", "S", "W")`` (aliases such as
            ``"top"`` / ``"left"`` are accepted).  Corner insets are only
            applied for adjacent sides that are actually being drawn.
        keepout_layers: Layer specs whose shapes block slots.
        keepout_distance: Minimum clearance in um between a rectangle and any
            keepout shape.  A rectangle exactly at this distance is kept.
        extra_keepout: Optional additional keepout as a ``kdb.Region`` or an
            iterable of boxes/polygons (um types are converted).
        die_bbox: Explicit die outline in um.  Defaults to the cell bbox over
            all layers.
        corner_owner: ``"vertical"`` (default) lets the W/E runs reach the
            corners and insets the N/S runs; ``"horizontal"`` does the
            opposite; ``"none"`` insets nothing (runs may meet at corners).
        align: ``"start"`` (default) anchors each run at its corner;
            ``"center"`` centers the lattice on the edge.
        end_fill: What to do with the leftover slack at the end of a run (the
            gap that shows up in the corners because the pitch rarely divides
            the edge evenly).  ``"none"`` (default) leaves it empty;
            ``"fill"`` adds a shortened rectangle that consumes the slack,
            keeping ``separation`` from the last full rectangle; ``"stretch"``
            lengthens the outermost lattice rectangle instead, adding no extra
            shape.  Fillers are keepout-checked like any other slot.
        min_end_length: Minimum length in um for an ``end_fill="fill"``
            rectangle, to avoid slivers.  Defaults to the rectangle width, so
            a filler is never narrower than it is long.  Ignored by
            ``"stretch"``.

    Returns:
        ``{side: [BorderRect, ...]}`` for each requested side.  The first
        ``count`` entries are the lattice slots in order, so
        ``result[side][i].index == i``; any ``end_fill="fill"`` rectangles are
        appended after them with ``end_fill=True`` and ``index`` of ``-1``
        (head of the run) or ``count`` (tail).  Blocked slots are included with
        ``placed=False``; filter with ``[r for r in result["N"] if r.placed]``
        if you only want the drawn ones.
    """
    if corner_owner not in ("vertical", "horizontal", "none"):
        raise ValueError("corner_owner must be 'vertical', 'horizontal' or 'none'")
    if align not in ("start", "center"):
        raise ValueError("align must be 'start' or 'center'")
    if end_fill not in ("none", "fill", "stretch"):
        raise ValueError("end_fill must be 'none', 'fill' or 'stretch'")

    cell = _kdb_cell(die)
    layout = cell.layout()
    dbu = layout.dbu
    layer_index = _layer_index(layout, layer)
    wanted = _normalize_sides(sides)
    if not wanted:
        return {}

    length = _dbu(size[0], dbu)
    width = _dbu(size[1], dbu)
    if length <= 0 or width <= 0:
        raise ValueError(f"size must be positive, got {size!r}")
    sep = _dbu(separation, dbu)
    border = _dbu(border_separation, dbu)
    keepout_dbu = _dbu(keepout_distance, dbu)

    outline = cell.bbox() if die_bbox is None else _as_dbox(die_bbox, dbu).to_itype(dbu)
    if outline.empty():
        raise ValueError("die outline is empty; pass die_bbox explicitly")

    inner = outline.enlarged(-border, -border)
    if inner.width() <= 0 or inner.height() <= 0:
        raise ValueError(
            f"border_separation={border_separation} leaves no room inside the die"
        )

    keepout = _keepout_region(cell, layout, keepout_layers, extra_keepout, keepout_dbu)

    # corner reservation: only inset where the neighbouring run actually exists
    inset_h = width + sep if corner_owner == "vertical" else 0
    inset_v = width + sep if corner_owner == "horizontal" else 0
    lo_inset = {
        "N": inset_h if "W" in wanted else 0,
        "S": inset_h if "W" in wanted else 0,
        "W": inset_v if "S" in wanted else 0,
        "E": inset_v if "S" in wanted else 0,
    }
    hi_inset = {
        "N": inset_h if "E" in wanted else 0,
        "S": inset_h if "E" in wanted else 0,
        "W": inset_v if "N" in wanted else 0,
        "E": inset_v if "N" in wanted else 0,
    }

    min_end = width if min_end_length is None else _dbu(min_end_length, dbu)

    result: dict[str, list[BorderRect]] = {}
    shapes = cell.shapes(layer_index)

    for side in wanted:
        horizontal = side in _HORIZONTAL
        if horizontal:
            axis_lo = inner.left + lo_inset[side]
            axis_hi = inner.right - hi_inset[side]
            cross_lo = inner.top - width if side == "N" else inner.bottom
        else:
            axis_lo = inner.bottom + lo_inset[side]
            axis_hi = inner.top - hi_inset[side]
            cross_lo = inner.right - width if side == "E" else inner.left

        count, offset = _lattice(axis_hi - axis_lo, length, sep, align)

        def emit(a0: int, a1: int, index: int, is_end_fill: bool) -> BorderRect:
            """Keepout-check the interval ``[a0, a1]`` and draw it if free."""
            if horizontal:  # noqa: B023
                rect = kdb.Box(a0, cross_lo, a1, cross_lo + width)  # noqa: B023
            else:
                rect = kdb.Box(cross_lo, a0, cross_lo + width, a1)  # noqa: B023
            inside = outline.contains(rect.p1) and outline.contains(rect.p2)
            blocked = (
                not keepout.is_empty() and not (kdb.Region(rect) & keepout).is_empty()
            )
            placed = inside and not blocked
            if placed:
                shapes.insert(rect)
            return BorderRect(
                side=side,  # noqa: B023
                index=index,
                box=rect.to_dtype(dbu),
                placed=placed,
                blocked_by_keepout=blocked,
                end_fill=is_end_fill,
            )

        run: list[BorderRect] = []
        for i in range(count):
            a0 = axis_lo + offset + i * (length + sep)
            a1 = a0 + length
            if end_fill == "stretch":  # absorb the slack into the outer slots
                if i == 0:
                    a0 = axis_lo
                if i == count - 1:
                    a1 = axis_hi
            run.append(emit(a0, a1, i, False))

        if end_fill == "fill":
            if count == 0:  # edge shorter than one rectangle: one filler
                if axis_hi - axis_lo >= min_end:
                    run.append(emit(axis_lo, axis_hi, 0, True))
            else:
                head = axis_lo + offset - sep - axis_lo
                tail = axis_hi - (
                    axis_lo + offset + (count - 1) * (length + sep) + length + sep
                )
                if head >= min_end:
                    run.append(emit(axis_lo, axis_lo + head, -1, True))
                if tail >= min_end:
                    run.append(emit(axis_hi - tail, axis_hi, count, True))

        result[side] = run

    return result
