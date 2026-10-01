"""Collect circle components from a gdsfactory die and organise them into a
die-wide matrix indexed by (row, col), based on each circle's ABSOLUTE
position in the die frame.

Approach
--------
Circles are nested (die -> container -> circle), so a circle instance's own
x/y is relative to its container. Instead of composing transforms by hand we
lean on KLayout's recursive instance iterator (exposed on every gdsfactory
Component via `.kdb_cell.begin_instances_rec()`):

  * `it.targets = "*circle*"` reports only instances whose target cell name
    matches the glob, at any nesting depth;
  * `it.trans() * it.inst_trans()` is the full transform mapping the target
    cell's own coordinates into the top (die) frame - it already folds in every
    container translation, rotation and mirror above it.

We map each circle's bbox centre up to the die frame, then cluster the absolute
x's into columns and y's into rows (tolerance-based, single-linkage on the
sorted gaps). Only rows/columns that actually contain a circle exist - no
synthetic empty slots are invented. Intersections with no circle are `None`.

Tested against gdsfactory 9.12.0.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import gdsfactory as gf
from kfactory import kdb


@dataclass
class Circle:
    """One circle instance, with its absolute centre in the die frame (um)
    and its ports already transformed into the die coordinate frame."""

    name: str  # referenced cell name (e.g. "circle_...")
    x: float  # absolute centre x, microns
    y: float  # absolute centre y, microns
    ports: dict = field(default_factory=dict)  # {port_name: die-frame Port}
    row: int = -1  # assigned row index (0 = top by default)
    col: int = -1  # assigned column index (0 = left)

    def __getitem__(self, port_name: str):
        """circle["e1"] -> the port in the die frame, ready for `connect`."""
        return self.ports[port_name]

    @property
    def port_names(self) -> list[str]:
        return list(self.ports)


@dataclass
class CircleMatrix:
    circles: list[Circle]  # every circle found, flat
    col_x: list[float]  # x centre of each column (left->right)
    row_y: list[float]  # y centre of each row (order per `origin`)
    grid: list[list[Circle | None]]  # grid[row][col], None where empty
    by_index: dict[tuple[int, int], Circle]  # {(col, row): Circle}

    def __getitem__(self, row: int) -> list[Circle | None]:
        """m[row] -> the row list, so m[row][col] -> Circle | None,
        and m[row][col]["e1"] -> that circle's e1 port in die coords."""
        return self.grid[row]

    @property
    def shape(self) -> tuple[int, int]:
        return len(self.row_y), len(self.col_x)

    def __str__(self) -> str:
        nrows, ncols = self.shape
        lines = [
            f"CircleMatrix: {nrows} rows x {ncols} cols, {len(self.circles)} circles"
        ]
        for r in range(nrows):
            cells = ["  O  " if self.grid[r][c] else "  .  " for c in range(ncols)]
            lines.append(f"row {r}: " + "".join(cells))
        return "\n".join(lines)


def _as_dbu_box(area, dbu: float):
    """Normalise a scan area into a kdb.Box in database units (die frame).

    Accepts: None (no restriction), a (xmin, ymin, xmax, ymax) tuple in microns,
    a kdb.DBox (microns), or a kdb.Box (already DBU). Tuples are normalised so
    the corners may be given in any order.
    """
    if area is None:
        return None
    if isinstance(area, kdb.Box):
        return area
    if isinstance(area, kdb.DBox):
        return kdb.Box(
            round(area.left / dbu),
            round(area.bottom / dbu),
            round(area.right / dbu),
            round(area.top / dbu),
        )
    x0, y0, x1, y1 = area
    return kdb.Box(
        round(min(x0, x1) / dbu),
        round(min(y0, y1) / dbu),
        round(max(x0, x1) / dbu),
        round(max(y0, y1) / dbu),
    )


def find_circles(
    die: gf.Component,
    name_glob: str = "*circle*",
    name_regex: str | None = None,
    area=None,
    area_mode: str = "center",
) -> list[Circle]:
    """Return every instance in `die` (any depth) whose target cell name matches
    `name_glob`, with its absolute centre in the die coordinate frame (um).

    name_glob  : fast KLayout glob prefilter on the cell name (anchored, full
                 match). Cheap but can't express "digits only, no trailing".
    name_regex : optional exact filter applied on top of the glob via
                 re.fullmatch. Use e.g. r"circle\\d+" to keep circle0, circle12
                 while rejecting circle_escape and circle0_extra.
    area       : optional scan window in DIE coordinates. None (default) scans
                 the whole die. Give (xmin, ymin, xmax, ymax) in microns, or a
                 kdb.DBox / kdb.Box. The window is pushed down into KLayout's
                 iterator, so circles outside it are never even visited.
    area_mode  : how a circle is judged against `area`.
                 "center"      -> its absolute centre lies inside (inclusive).
                                  Default: unambiguous for circles straddling
                                  the edge, and what you usually want for a grid.
                 "overlapping" -> its bbox genuinely overlaps the area.
                 "touching"    -> its bbox merely touches the area (most generous).
    """
    if area_mode not in ("center", "overlapping", "touching"):
        raise ValueError(
            f"area_mode must be 'center', 'overlapping' or 'touching', got {area_mode!r}"
        )

    dbu = die.kcl.dbu
    pat = re.compile(name_regex) if name_regex else None
    box = _as_dbu_box(area, dbu)

    it = die.kdb_cell.begin_instances_rec()
    it.targets = name_glob  # glob filter on target cell names
    if box is not None:
        it.region = box
        # For "center" we prefilter generously (touching) and then test the
        # centre exactly in Python - a centre inside the box always implies the
        # bbox touches the box, so this superset is safe.
        it.overlapping = area_mode == "overlapping"

    # Inclusive micron bounds for the exact "center" test.
    if box is not None:
        bx0, by0 = box.left * dbu, box.bottom * dbu
        bx1, by1 = box.right * dbu, box.top * dbu

    circles: list[Circle] = []
    while not it.at_end():
        raw = it.inst_cell()  # kdb.Cell (the circle)
        if pat is not None and not pat.fullmatch(raw.name):
            it.next()
            continue
        full = it.trans() * it.inst_trans()  # target-cell -> die frame (DBU)
        centre = full * raw.bbox().center()  # kdb.Point in DBU
        cx, cy = centre.x * dbu, centre.y * dbu

        # Exact centre-in-area test (the iterator region was only a prefilter).
        if box is not None and area_mode == "center":
            if not (bx0 <= cx <= bx1 and by0 <= cy <= by1):
                it.next()
                continue

        # Push every port through the same transform so it lands in die coords.
        # Port.copy() wants a micron complex transform, so convert DBU -> um.
        dtrans = kdb.DCplxTrans(full, dbu)
        kcell = die.kcl[raw.cell_index()]  # kfactory KCell (has .ports)
        ports = {p.name: p.copy(dtrans) for p in kcell.ports}

        circles.append(Circle(raw.name, cx, cy, ports=ports))
        it.next()
    return circles


def _cluster(values: list[float], tol: float) -> tuple[list[int], list[float]]:
    """Group values whose sorted neighbours are within `tol`. Returns
    (label_per_value, cluster_centres) with clusters ordered ascending."""
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


def build_matrix(
    die: gf.Component,
    name_glob: str = "*circle*",
    name_regex: str | None = None,
    area=None,
    area_mode: str = "center",
    tol: float = 1.0,
    origin: str = "top-left",
) -> CircleMatrix:
    """Build a die-wide matrix of circles.

    name_glob  : fast KLayout glob prefilter on the cell name (anchored, full
                 match). Cheap but can't express "digits only, no trailing".
    name_regex : optional exact filter applied on top of the glob via
                 re.fullmatch. Use e.g. r"circle\\d+" to keep circle0, circle12
                 while rejecting circle_escape and circle0_extra.
    area    : optional scan window in die coordinates, as
              (xmin, ymin, xmax, ymax) in microns (or a kdb.DBox / kdb.Box).
              None (default) scans the whole die. NOTE that row/column indices
              are always relative to the circles actually scanned, so with an
              area set, col 0 is the leftmost circle *inside the window*, not
              the leftmost on the die.
    area_mode : "center" (default), "overlapping" or "touching" - see
              find_circles() for the precise meaning.
    tol     : microns. Two circles are in the same column/row if their x/y
              centres are within `tol`. Keep it below the smallest gap between
              distinct columns/rows and above any placement jitter.
    origin  : which corner is (row 0, col 0).
              "top-left"    -> row 0 = highest y, col 0 = lowest x  (matches the diagram)
              "bottom-left" -> row 0 = lowest y,  col 0 = lowest x
    """

    circles = find_circles(die, name_glob, name_regex, area, area_mode)
    if not circles:
        return CircleMatrix([], [], [], [], {})

    col_lbl, col_centres = _cluster([c.x for c in circles], tol)  # ascending x
    row_lbl, row_centres = _cluster([c.y for c in circles], tol)  # ascending y
    nrows, ncols = len(row_centres), len(col_centres)

    top_down = origin.startswith("top")
    row_y = list(reversed(row_centres)) if top_down else list(row_centres)

    grid: list[list[Circle | None]] = [[None] * ncols for _ in range(nrows)]
    by_index: dict[tuple[int, int], Circle] = {}
    for i, c in enumerate(circles):
        col = col_lbl[i]
        row = (nrows - 1 - row_lbl[i]) if top_down else row_lbl[i]
        c.col, c.row = col, row
        grid[row][col] = c
        by_index[(col, row)] = c  # (col, row) to match the diagram's labels

    return CircleMatrix(circles, col_centres, row_y, grid, by_index)


if __name__ == "__main__":
    # Minimal demo when run directly; see test_circle_matrix.py for the real check.
    die = gf.Component("die_demo")
    cont = gf.Component("container_demo")
    for cx, cy in [(0, 0), (10, 0), (0, -10), (10, -20)]:
        cont.add_ref(gf.components.circle(radius=2)).move((cx, cy))
    die.add_ref(cont).move((5, 5))
    m = build_matrix(die, name_glob="circle*", tol=1.0)
    print(m)
    print("by_index keys (col,row):", sorted(m.by_index))
