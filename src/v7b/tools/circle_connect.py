"""Connect checkerboard-filled circles with axis-aligned rectangles.

Takes the sparse row/column matrix produced by ``circle_matrix`` /
``checkerboard_fill`` and pairs up circles that are ``step`` indices apart
along one matrix axis, then draws one rectangle per pair, centre to centre.

Pairing is staggered (brick offset) row to row by default, so a circle
belongs to at most one connection and the pattern alternates::

    row 0:  O===O   O===O   O
    row 1:  O   O===O   O===O
    row 2:  O===O   O===O   O

Runs are broken wherever the index step is not exactly ``step``, so a
keepout hole in the lattice never gets bridged.

Slotting the connections
------------------------
Two routes, both measured on a 300x300 lattice (22,350 links, 335,250 slots):

    connect_circles + fill_region      7.70 s      2.82 MB
    place_connectors (one cell)        0.09 s      0.67 MB

The first route draws flat rectangles, then subtracts the die-wide circle
keepout and lets ``Cell.fill_region`` walk the result -- 3.6 s of fill on top
of 4.1 s spent building a 45,000-polygon keepout region.  The second exploits
the fact that every link is *congruent*: same length, same width, same two
circles at the same relative offsets.  So the fill runs once, on a prototype
cell holding one bar with its two end circles carved out, and the die gets one
instance of that cell per link.  Slot geometry is identical -- verified
XOR = 0 -- because a lattice fill of congruent regions is translation
invariant.

Use ``place_connectors`` unless one of its preconditions fails:

* **Congruence.** Links of differing length (from ``extension``, or a ``step``
  other than 2) need one prototype each.
* **Lattice coherence.** The prototype carries its own slot lattice, frozen
  relative to its origin.  Global continuity survives translation only when
  every link centre sits on the slot lattice; pass ``lattice=<slot pitch>`` to
  have that asserted rather than assumed.  Note that an off-lattice placement
  yields the *same slot count*, so counting slots will not catch it -- only
  the modulo check or an XOR will.
* **Uniform keepout.** A link that also runs near a border rectangle or the
  die edge is no longer congruent with the rest.  Slot those individually.

Two traps in ``fill_named_rectangles_fast`` when it is pointed at links rather
than at zone rectangles: its default ``margin=1.0`` erases anything narrower
than 2 um outright, so a 1.5 um bar vanishes silently; and
``named_fill_region`` cannot see links drawn by ``connect_circles`` at all,
because those are flat polygons with no cell name to match -- pass the
``kdb.Region`` to ``fill_region_fast`` directly instead.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Literal

__all__ = [
    "Fallback",
    "Link",
    "as_grid",
    "build_links",
    "connect_circles",
    "default_position",
    "group_by_prototype",
    "pair_by_distance",
    "pair_indices",
    "pair_with_fallback",
    "place_connectors",
    "resolve_axis",
]

Matrix = Sequence[Sequence[Any]]
Index = tuple[int, int]
Axis = Literal["row", "column", "auto"]


@dataclass(frozen=True)
class Link:
    """One circle-to-circle connection.

    Immutable, so one link list can be built once and reused across several
    insertion passes -- polygons on one layer, instances on another -- with no
    risk of a pass mutating the geometry for the next.
    """

    a: Index
    """(row, col) of the first circle, in the source matrix's indexing."""
    b: Index
    """(row, col) of the second circle."""
    axis: Literal["row", "column"]
    """Matrix axis the pair runs along. ``"row"`` is horizontal in x."""
    box: tuple[float, float, float, float]
    """(xmin, ymin, xmax, ymax) of the rectangle, in um, die frame."""

    @property
    def length(self) -> float:
        """Rectangle extent along the connection direction, in um.

        This is the *drawn* length, so it includes any ``extension``; with
        ``extension=0`` it equals the centre-to-centre circle spacing.
        """
        xmin, ymin, xmax, ymax = self.box
        return xmax - xmin if self.axis == "row" else ymax - ymin

    @property
    def center(self) -> tuple[float, float]:
        """Rectangle centre ``(x, y)`` in um, die frame.

        Equal to the midpoint of the two circle centres, and the placement
        point used by :func:`place_connectors`.
        """
        xmin, ymin, xmax, ymax = self.box
        return (0.5 * (xmin + xmax), 0.5 * (ymin + ymax))


@dataclass(frozen=True)
class Fallback:
    """How to connect circles the index-step pairing cannot reach.

    A checkerboard zone skips every other cell, so its neighbours are two
    indices apart. A single-file row or column does not skip anything, so its
    neighbours are one index apart -- and in a die-wide matrix both patterns
    coexist, because a strip's circles land in consecutive global columns
    while the mesh's land in alternating ones. No single ``step`` covers both.

    The fallback therefore pairs by physical distance instead of index gap,
    which is both pattern-agnostic and the thing you actually care about: how
    long a connector you are willing to draw. Keepout holes still break the
    chain, since a missing circle doubles the gap past ``max_distance``.
    """

    max_distance: float
    """Longest centre-to-centre spacing that may be paired, in um. Set it
    between one and two lattice pitches to bridge neighbours but not holes."""
    mode: Literal["isolated", "unpaired"] = "isolated"
    """``"isolated"`` only takes circles the index pass could not have paired
    under either stagger phase -- genuine single-file lines, and circles whose
    only index-neighbour is beyond ``max_length``. ``"unpaired"`` also sweeps
    up the odd cells the stagger left over inside 2D zones, connecting run ends
    that were skipped on purpose."""
    axes: tuple[str, ...] = ("row", "column")
    """Axes to try, in order. Both, by default: a horizontal strip is caught by
    the row pass and a vertical one by the column pass."""
    stagger: bool = False
    """Off by default, unlike the primary pass. On a lone line the stagger
    offset would be decided by that line's global index parity, which is
    arbitrary -- the strip would start pairing at its first or second circle
    depending on where it happens to sit on the die."""
    phase: int = 0
    """Constant offset applied to the pairing within each line."""


# --------------------------------------------------------------------------
# input normalisation
# --------------------------------------------------------------------------


def as_grid(matrix: Any) -> Matrix:
    """Return a plain list-of-lists view of ``matrix``.

    ``circle_matrix.CircleMatrix`` holds its cells in a ``.grid`` attribute and
    offers no ``__len__``, so it is not itself a sequence. Unwrapping it here
    means every public function in this module accepts either the dataclass or
    a bare list of lists, and nothing downstream has to care.

    Args:
        matrix: a ``CircleMatrix``, anything else exposing ``.grid``, or a list
            of lists.

    Returns:
        The underlying grid if there is one, otherwise ``matrix`` unchanged.
    """
    grid = getattr(matrix, "grid", None)
    return matrix if grid is None else grid


def default_position(entry: Any) -> tuple[float, float]:
    """Best-effort centre of a matrix entry, in um.

    Attributes are tried in order of decreasing unit safety, which is the whole
    point of the ordering: kfactory exposes both ``dcenter`` (um) and ``x``
    (dbu integers), so reading ``dcenter`` first keeps a kfactory instance from
    being silently interpreted as microns-worth-of-dbu. The bare ``.x`` / ``.y``
    fallback is what ``circle_matrix.Circle`` needs, and there the values
    genuinely are um.

    Args:
        entry: one occupied matrix cell -- a ``circle_matrix.Circle``, a
            kfactory/gdsfactory instance, a KLayout box or point, or a plain
            ``(x, y)`` tuple.

    Returns:
        ``(x, y)`` in um, in whatever frame the entry's own coordinates are
        expressed in. For ``circle_matrix`` output that is the die frame.

    Raises:
        TypeError: if no centre can be read. Pass ``position=<callable>`` to
            :func:`build_links` for anything more exotic.
    """
    for attr in ("dcenter", "center"):
        value = getattr(entry, attr, None)
        if value is None:
            continue
        if callable(value):
            value = value()
        return _as_xy(value)

    for attr in ("dbbox", "bbox"):
        value = getattr(entry, attr, None)
        if value is None:
            continue
        box = value() if callable(value) else value
        return _as_xy(box.center())

    x = getattr(entry, "x", None)
    y = getattr(entry, "y", None)
    if x is not None and y is not None:
        # circle_matrix.Circle and friends: plain um attributes.
        return (float(x), float(y))

    if isinstance(entry, tuple | list) and len(entry) >= 2:
        return (float(entry[0]), float(entry[1]))

    raise TypeError(
        f"cannot read a centre from {type(entry).__name__}; "
        "pass position=<callable> to build_links()"
    )


def _as_xy(value: Any) -> tuple[float, float]:
    """Coerce a KLayout point / box centre or a 2-sequence to ``(x, y)`` floats.

    Args:
        value: an object with ``.x`` / ``.y``, or an indexable of length 2.

    Returns:
        ``(x, y)`` as floats, units unchanged.
    """
    x = getattr(value, "x", None)
    if x is not None:
        return (float(x), float(value.y))
    return (float(value[0]), float(value[1]))


# --------------------------------------------------------------------------
# index pairing
# --------------------------------------------------------------------------


def _occupied(matrix: Matrix, axis: str) -> list[tuple[int, list[int]]]:
    """Occupied cell indices, grouped into lines along ``axis``.

    Reduces the 2D pairing problem to a series of independent 1D ones: each
    line is handled on its own, which is what makes the stagger a function of
    the line index alone and keeps holes local to the line they are in.

    Args:
        matrix: sparse 2D matrix, ``None`` where there is no circle.
        axis: ``"row"`` to walk rows, ``"column"`` to walk columns.

    Returns:
        ``[(line index, ascending transverse indices of occupied cells)]``, one
        entry per line, including lines that are entirely empty. For ``"row"``
        the line index is the row and the transverse indices are columns; for
        ``"column"`` it is the other way round. Ragged rows are tolerated --
        short rows are treated as empty past their end.
    """
    if axis == "row":
        return [
            (r, [c for c, cell in enumerate(row) if cell is not None])
            for r, row in enumerate(matrix)
        ]
    n_cols = max((len(row) for row in matrix), default=0)
    return [
        (
            c,
            [r for r, row in enumerate(matrix) if c < len(row) and row[c] is not None],
        )
        for c in range(n_cols)
    ]


def _runs(indices: Sequence[int], step: int) -> list[list[int]]:
    """Split ascending ``indices`` into maximal runs with a uniform gap.

    This is the mechanism that keeps a keepout hole from being bridged: a
    missing circle shows up as a gap of ``2 * step`` between its neighbours,
    which ends the run, and pairing never spans two runs.

    Args:
        indices: ascending cell indices along one line.
        step: the exact difference required between consecutive members of a
            run. Anything else starts a new run.

    Returns:
        Runs in ascending order; every input index appears in exactly one. A
        lone index yields a run of length 1, which pairs with nothing.

    Example:
        >>> _runs([0, 2, 6, 8], 2)
        [[0, 2], [6, 8]]
    """
    runs: list[list[int]] = []
    current: list[int] = []
    for idx in indices:
        if current and idx - current[-1] != step:
            runs.append(current)
            current = []
        current.append(idx)
    if current:
        runs.append(current)
    return runs


def resolve_axis(matrix: Matrix, axis: Axis) -> Literal["row", "column"]:
    """Resolve ``"auto"`` to the long axis of the occupied region.

    Lets one call handle every zone on a die: a wide zone gets horizontal
    connections and a tall one gets vertical, with no per-zone configuration.
    Only the *occupied* extent counts, so trailing empty rows or columns in the
    matrix do not skew the choice.

    Args:
        matrix: sparse 2D matrix, or a ``CircleMatrix``.
        axis: ``"row"``, ``"column"`` or ``"auto"``.

    Returns:
        ``"row"`` or ``"column"``. Ties go to ``"row"``, as does an empty
        matrix.

    Raises:
        ValueError: if ``axis`` is not one of the three accepted values.
    """
    matrix = as_grid(matrix)
    if axis in ("row", "column"):
        return axis  # type: ignore[return-value]
    if axis != "auto":
        raise ValueError(f"axis must be 'row', 'column' or 'auto', got {axis!r}")

    rows = [r for r, row in enumerate(matrix) if any(c is not None for c in row)]
    cols = [
        c
        for c in range(max((len(row) for row in matrix), default=0))
        if any(c < len(row) and row[c] is not None for row in matrix)
    ]
    if not rows or not cols:
        return "row"
    row_span = rows[-1] - rows[0] + 1
    col_span = cols[-1] - cols[0] + 1
    return "row" if col_span >= row_span else "column"


def pair_indices(
    matrix: Matrix,
    *,
    axis: Axis = "row",
    step: int = 2,
    stagger: bool = True,
    phase: int = 0,
    pair_short_runs: bool = False,
) -> list[tuple[Index, Index]]:
    """Pair occupied cells ``step`` indices apart along ``axis``.

    Pure index arithmetic -- no coordinates are read -- so this is the function
    to test the pattern against, and the one to call if you want the pairing
    without any geometry.

    Args:
        matrix: sparse 2D matrix, ``None`` where there is no circle. A
            ``CircleMatrix`` is accepted directly.
        axis: ``"row"`` pairs horizontally, ``"column"`` vertically,
            ``"auto"`` picks the long axis of the occupied region.
        step: index distance between paired cells. On a checkerboard lattice,
            same-row neighbours are 2 columns apart.
        stagger: offset the pairing by one cell on alternating lines (the brick
            pattern). Set False to pair every line identically.
        phase: seed for the stagger; flips which cells pair on which line. With
            ``stagger=False`` it becomes a constant offset.
        pair_short_runs: a run of exactly two cells on an offset line yields no
            pair at all, because the offset consumes the first cell -- so a row
            split into short runs by keepout holes can come back empty. Set
            True to drop the offset for those runs, at the cost of a local
            break in the brick rhythm.

    Returns:
        ``[((row, col), (row, col)), ...]`` in matrix order, the first cell of
        each pair always the lower index. Every cell appears in at most one
        pair, so the connections form disjoint dimers rather than chains.

    Raises:
        ValueError: if ``step < 1``, or ``axis`` is invalid.
    """
    if step < 1:
        raise ValueError(f"step must be >= 1, got {step}")

    matrix = as_grid(matrix)
    resolved = resolve_axis(matrix, axis)
    pairs: list[tuple[Index, Index]] = []

    for line, occupied in _occupied(matrix, resolved):
        offset = (line + phase) % 2 if stagger else phase % 2
        for run in _runs(occupied, step):
            start = offset
            if pair_short_runs and start >= len(run) - 1:
                start = 0
            for i in range(start, len(run) - 1, 2):
                first, second = run[i], run[i + 1]
                if resolved == "row":
                    pairs.append(((line, first), (line, second)))
                else:
                    pairs.append(((first, line), (second, line)))
    return pairs


def _occupied_cells(matrix: Matrix) -> list[Index]:
    """Every occupied cell as ``(row, col)``, in row-major order.

    Args:
        matrix: sparse 2D matrix, ``None`` where there is no circle.

    Returns:
        Indices of all non-``None`` cells.
    """
    return [
        (r, c)
        for r, row in enumerate(matrix)
        for c, cell in enumerate(row)
        if cell is not None
    ]


def _pair_span(
    matrix: Matrix,
    a: Index,
    b: Index,
    position: Callable[[Any], tuple[float, float]],
) -> float:
    """Centre-to-centre distance between two paired cells, in um.

    Args:
        matrix: sparse 2D matrix.
        a: first cell.
        b: second cell, sharing a row or a column with ``a``.
        position: callable returning the ``(x, y)`` centre of a matrix entry.

    Returns:
        The separation along whichever axis the pair runs on.
    """
    xa, ya = position(matrix[a[0]][a[1]])
    xb, yb = position(matrix[b[0]][b[1]])
    return abs(xb - xa) if a[0] == b[0] else abs(yb - ya)


def _reachable(
    matrix: Matrix,
    *,
    axis: Literal["row", "column"],
    step: int,
    stagger: bool,
    phase: int,
    pair_short_runs: bool,
    position: Callable[[Any], tuple[float, float]],
    max_length: float | None,
) -> set[Index]:
    """Cells the index pass could pair, under either stagger phase.

    The distinction the fallback needs is not "did this cell get paired" but
    "could it have been". A stagger leftover at the end of a mesh run was
    skipped deliberately and should stay skipped; a circle in a single-file
    strip was never pairable at all and is what the fallback exists for.
    Running both phases separates the two -- a cell unpaired under both is
    genuinely out of the index pass's reach.

    Pairs longer than ``max_length`` do not count as reach, which is what lets
    a circle whose only index-neighbour is a zone away fall through to the
    fallback rather than being written off as already served.

    Args:
        matrix: sparse 2D matrix.
        axis: primary pairing axis, already resolved.
        step: index distance for the primary pass.
        stagger: brick offset setting of the primary pass.
        phase: stagger seed of the primary pass; the opposite phase is tried
            alongside it.
        pair_short_runs: see :func:`pair_indices`.
        position: callable returning the ``(x, y)`` centre of a matrix entry.
        max_length: pairs wider than this are not counted. ``None`` counts all.

    Returns:
        Every cell appearing in a viable pair under either phase.
    """
    reachable: set[Index] = set()
    for trial in (phase, phase + 1):
        for a, b in pair_indices(
            matrix,
            axis=axis,
            step=step,
            stagger=stagger,
            phase=trial,
            pair_short_runs=pair_short_runs,
        ):
            if max_length is None or _pair_span(matrix, a, b, position) <= max_length:
                reachable.update((a, b))
    return reachable


def _distance_runs(
    members: Sequence[tuple[float, Index]], max_distance: float
) -> list[list[tuple[float, Index]]]:
    """Split coordinate-sorted cells into runs with no oversized gap.

    The distance-based twin of :func:`_runs`, and it serves the same purpose:
    a keepout hole shows up as a double-pitch gap, which ends the run, so
    pairing never spans one.

    Args:
        members: ``(coordinate along the line, index)`` pairs, ascending by
            coordinate.
        max_distance: largest gap that may stay inside a run, in um.

    Returns:
        Runs in ascending coordinate order; every member appears in exactly
        one.
    """
    runs: list[list[tuple[float, Index]]] = []
    current: list[tuple[float, Index]] = []
    for member in members:
        if current and member[0] - current[-1][0] > max_distance:
            runs.append(current)
            current = []
        current.append(member)
    if current:
        runs.append(current)
    return runs


def pair_by_distance(
    matrix: Matrix,
    *,
    max_distance: float,
    axis: Literal["row", "column"],
    position: Callable[[Any], tuple[float, float]] = default_position,
    stagger: bool = False,
    phase: int = 0,
    only: Iterable[Index] | None = None,
) -> list[tuple[Index, Index]]:
    """Pair cells along ``axis`` by physical spacing rather than index gap.

    Use this wherever the index step is not uniform -- most often a single-file
    row or column, whose circles sit one global index apart while a
    checkerboard zone's sit two apart.

    Args:
        matrix: sparse 2D matrix, or a ``CircleMatrix``.
        max_distance: longest centre-to-centre spacing that may be paired, in
            um. Anything wider ends the run.
        axis: ``"row"`` pairs horizontally, ``"column"`` vertically. No
            ``"auto"`` here -- the caller has already decided.
        position: callable returning the ``(x, y)`` centre of a matrix entry.
        stagger: offset the pairing on alternating lines. Off by default; see
            :attr:`Fallback.stagger` for why.
        phase: constant offset applied within each line.
        only: restrict pairing to these cells. Everything else is invisible,
            including as a run member, so a restricted pass will happily pair
            two cells that have an unlisted circle between them -- pass a set
            that is contiguous along the line, or accept the bridging.

    Returns:
        ``[((row, col), (row, col)), ...]``, lower index first in each pair.
        Every cell appears in at most one pair.

    Raises:
        ValueError: if ``max_distance <= 0``.
    """
    if max_distance <= 0:
        raise ValueError(f"max_distance must be > 0, got {max_distance}")

    matrix = as_grid(matrix)
    allowed = None if only is None else set(only)
    groups: dict[int, list[tuple[float, Index]]] = {}

    for cell in _occupied_cells(matrix):
        if allowed is not None and cell not in allowed:
            continue
        x, y = position(matrix[cell[0]][cell[1]])
        line = cell[0] if axis == "row" else cell[1]
        coord = x if axis == "row" else y
        groups.setdefault(line, []).append((coord, cell))

    pairs: list[tuple[Index, Index]] = []
    for line in sorted(groups):
        offset = (line + phase) % 2 if stagger else phase % 2
        for run in _distance_runs(sorted(groups[line]), max_distance):
            for i in range(offset, len(run) - 1, 2):
                a, b = run[i][1], run[i + 1][1]
                pairs.append((a, b) if a <= b else (b, a))
    return pairs


def pair_with_fallback(
    matrix: Matrix,
    *,
    fallback: Fallback | None,
    axis: Axis = "row",
    step: int = 2,
    stagger: bool = True,
    phase: int = 0,
    pair_short_runs: bool = False,
    max_length: float | None = None,
    on_too_long: Literal["raise", "skip"] = "raise",
    position: Callable[[Any], tuple[float, float]] = default_position,
) -> list[tuple[Index, Index]]:
    """Index-step pairing, then a distance pass over whatever it cannot reach.

    Two passes rather than one distance pass over everything, because the index
    pass is what enforces the brick stagger across a 2D mesh, and that pattern
    is the point. The fallback only gets the leftovers.

    ``max_length`` is applied here rather than downstream in
    :func:`build_links` so that a rejected pair frees its circles for the
    fallback instead of stranding them.

    Args:
        matrix: sparse 2D matrix, or a ``CircleMatrix``.
        fallback: see :class:`Fallback`. ``None`` skips the second pass, giving
            :func:`pair_indices` plus the ``max_length`` filter.
        axis: primary axis; ``"auto"`` picks the long axis of the matrix.
        step: index distance for the primary pass.
        stagger: brick offset on the primary pass.
        phase: stagger seed for the primary pass.
        pair_short_runs: see :func:`pair_indices`.
        max_length: reject pairs whose centre-to-centre spacing exceeds this,
            in um. See :func:`build_links`.
        on_too_long: ``"raise"`` or ``"skip"`` for pairs over ``max_length``.
        position: callable returning the ``(x, y)`` centre of a matrix entry.

    Returns:
        Primary pairs first, then fallback pairs. A pair may run along either
        axis, so read the orientation off the indices rather than assuming.

    Raises:
        ValueError: if a pair exceeds ``max_length`` while
            ``on_too_long="raise"``.
    """
    matrix = as_grid(matrix)
    resolved = resolve_axis(matrix, axis)
    pairs = pair_indices(
        matrix,
        axis=resolved,
        step=step,
        stagger=stagger,
        phase=phase,
        pair_short_runs=pair_short_runs,
    )

    if max_length is not None:
        kept = []
        for a, b in pairs:
            span = _pair_span(matrix, a, b, position)
            if span <= max_length:
                kept.append((a, b))
            elif on_too_long == "raise":
                raise ValueError(
                    f"circles {a} and {b} are {span:.4f} um apart, over "
                    f"max_length {max_length} um; index steps are only "
                    "uniform in distance within a single zone"
                )
        pairs = kept

    if fallback is None:
        return pairs

    if fallback.mode == "isolated":
        served = _reachable(
            matrix,
            axis=resolved,
            step=step,
            stagger=stagger,
            phase=phase,
            pair_short_runs=pair_short_runs,
            position=position,
            max_length=max_length,
        )
    else:
        served = {cell for pair in pairs for cell in pair}

    remaining = {cell for cell in _occupied_cells(matrix) if cell not in served}

    for fallback_axis in fallback.axes:
        if not remaining:
            break
        found = pair_by_distance(
            matrix,
            max_distance=fallback.max_distance,
            axis=fallback_axis,  # type: ignore[arg-type]
            position=position,
            stagger=fallback.stagger,
            phase=fallback.phase,
            only=remaining,
        )
        pairs.extend(found)
        remaining -= {cell for pair in found for cell in pair}

    return pairs


# --------------------------------------------------------------------------
# geometry
# --------------------------------------------------------------------------


def build_links(
    matrix: Matrix,
    *,
    width: float,
    axis: Axis = "row",
    step: int = 2,
    stagger: bool = True,
    phase: int = 0,
    pair_short_runs: bool = False,
    fallback: Fallback | None = None,
    max_length: float | None = None,
    on_too_long: Literal["raise", "skip"] = "raise",
    extension: float = 0.0,
    position: Callable[[Any], tuple[float, float]] = default_position,
    tolerance: float = 1e-6,
    on_misaligned: Literal["raise", "skip", "allow"] = "raise",
) -> list[Link]:
    """Build the connection rectangles without touching any layout.

    Split out from :func:`connect_circles` so the geometry can be inspected,
    counted or asserted on before anything is committed to a cell, and so one
    link list can feed both insertion routes.

    Args:
        matrix: sparse 2D matrix, or a ``CircleMatrix``.
        width: rectangle width transverse to the connection, in um.
        axis: see :func:`pair_indices`.
        step: see :func:`pair_indices`.
        stagger: see :func:`pair_indices`.
        phase: see :func:`pair_indices`.
        pair_short_runs: see :func:`pair_indices`.
        fallback: see :class:`Fallback`. Connects single-file rows and columns
            that the index-step pass cannot reach. Links it produces may run
            along the other axis and be a different length, so check
            :func:`group_by_prototype` before feeding them to
            :func:`place_connectors`.
        max_length: reject pairs whose centre-to-centre spacing exceeds this,
            in um. Worth setting on any die-wide matrix: column indices are
            only uniform in x within a zone, so two indices apart can mean one
            lattice pitch inside a mesh and tens of microns across the gap to
            the next zone. ``None`` disables the check, which is safe when the
            matrix covers a single zone.
        on_too_long: ``"raise"`` or ``"skip"`` for pairs over ``max_length``.
        extension: extra length added at *each* end beyond the circle centres,
            in um. 0.0 gives a pure centre-to-centre rectangle, which already
            overlaps both circles by their radius.
        position: callable returning the ``(x, y)`` centre of a matrix entry,
            in um. See :func:`default_position`.
        tolerance: maximum allowed transverse mismatch between the two centres,
            in um. Note that ``circle_matrix.build_matrix`` clusters rows with
            ``tol=1.0`` um, so extracted circles with placement jitter can
            legitimately sit that far apart -- raise this to ~1e-3 for those,
            and leave it tight for a generated lattice where placement is
            exact.
        on_misaligned: what to do when a pair exceeds ``tolerance`` --
            ``"raise"``, ``"skip"`` the pair, or ``"allow"`` it and centre the
            rectangle on the mean.

    Returns:
        One :class:`Link` per connection, primary pairs first. Each link's
        ``axis`` is read off its own indices, so a mixed list is fine.

    Raises:
        ValueError: if ``width <= 0``; if a pair is misaligned beyond
            ``tolerance`` while ``on_misaligned="raise"``; or if a pair is
            longer than ``max_length`` while ``on_too_long="raise"``.
    """
    if width <= 0:
        raise ValueError(f"width must be > 0, got {width}")
    if max_length is not None and max_length <= 0:
        raise ValueError(f"max_length must be > 0, got {max_length}")

    matrix = as_grid(matrix)
    half = 0.5 * width
    links: list[Link] = []

    for a, b in pair_with_fallback(
        matrix,
        fallback=fallback,
        axis=axis,
        step=step,
        stagger=stagger,
        phase=phase,
        pair_short_runs=pair_short_runs,
        max_length=max_length,
        on_too_long=on_too_long,
        position=position,
    ):
        xa, ya = position(matrix[a[0]][a[1]])
        xb, yb = position(matrix[b[0]][b[1]])

        # a pair always shares a row or a column; the fallback can hand back
        # either orientation, so take it from the indices rather than the
        # requested axis
        resolved = "row" if a[0] == b[0] else "column"

        if resolved == "row":
            along, transverse = (xa, xb), (ya, yb)
        else:
            along, transverse = (ya, yb), (xa, xb)

        if abs(transverse[0] - transverse[1]) > tolerance:
            if on_misaligned == "raise":
                raise ValueError(
                    f"circles {a} and {b} are not aligned along {resolved}: "
                    f"transverse offset "
                    f"{abs(transverse[0] - transverse[1]):.6f} um "
                    f"exceeds tolerance {tolerance} um"
                )
            if on_misaligned == "skip":
                continue

        lo = min(along) - extension
        hi = max(along) + extension
        mid = 0.5 * (transverse[0] + transverse[1])

        box = (
            (lo, mid - half, hi, mid + half)
            if resolved == "row"
            else (mid - half, lo, mid + half, hi)
        )
        links.append(Link(a=a, b=b, axis=resolved, box=box))

    return links


# --------------------------------------------------------------------------
# layer / cell resolution
# --------------------------------------------------------------------------


def _layer_index(component: Any, layer: Any) -> int:
    """Resolve a layer spec to a KLayout layer index in ``component``'s layout.

    Args:
        component: target cell, used for its ``kcl``.
        layer: an existing layer index (a gdsfactory ``LayerEnum`` is an ``int``
            subclass and counts as one), a ``(layer, datatype)`` pair, or a PDK
            layer name.

    Returns:
        The layer index.

    Raises:
        ValueError: from ``gdsfactory.get_layer`` for an unknown name, or when
            a name is passed with no PDK active.
    """
    if isinstance(layer, int):
        return layer
    if isinstance(layer, tuple | list) and len(layer) == 2:
        return component.kcl.layer(int(layer[0]), int(layer[1]))
    import gdsfactory as gf

    return gf.get_layer(layer)


def _cell_index(connector: Any) -> int:
    """Resolve a connector spec to a KLayout cell index.

    Args:
        connector: a gdsfactory ``Component``, a kfactory ``KCell``, a
            ``klayout.db.Cell``, or an already-resolved cell index.

    Returns:
        The cell index.

    Raises:
        TypeError: if no cell index can be found.
    """
    if isinstance(connector, int):
        return connector
    for attr in ("kdb_cell", "_kdb_cell"):
        cell = getattr(connector, attr, None)
        if cell is not None:
            return cell.cell_index()
    index = getattr(connector, "cell_index", None)
    if callable(index):
        return index()
    raise TypeError(
        f"cannot get a cell index from {type(connector).__name__}; pass a "
        "gdsfactory Component, kfactory KCell, klayout.db.Cell or an index"
    )


# --------------------------------------------------------------------------
# layout insertion
# --------------------------------------------------------------------------


def connect_circles(
    component: Any,
    matrix: Matrix,
    *,
    layer: Any,
    width: float,
    axis: Axis = "row",
    step: int = 2,
    stagger: bool = True,
    phase: int = 0,
    pair_short_runs: bool = False,
    fallback: Fallback | None = None,
    max_length: float | None = None,
    on_too_long: Literal["raise", "skip"] = "raise",
    extension: float = 0.0,
    position: Callable[[Any], tuple[float, float]] = default_position,
    tolerance: float = 1e-6,
    on_misaligned: Literal["raise", "skip", "allow"] = "raise",
    merge: bool = False,
) -> list[Link]:
    """Draw one flat rectangle per connection into ``component``.

    All rectangles are collected into a single ``kdb.Region`` and inserted in
    one call, so the cost is one C++ pass rather than a Python loop over
    shapes. For a link set that then needs slotting, prefer
    :func:`place_connectors` -- see the module docstring for the measured
    difference.

    Args:
        component: target gdsfactory ``Component`` / kfactory ``KCell``,
            modified in place.
        matrix: sparse 2D matrix, or a ``CircleMatrix``.
        layer: ``(layer, datatype)``, a layer index, or a PDK layer name.
        width: rectangle width transverse to the connection, in um.
        axis: see :func:`pair_indices`.
        step: see :func:`pair_indices`.
        stagger: see :func:`pair_indices`.
        phase: see :func:`pair_indices`.
        pair_short_runs: see :func:`pair_indices`.
        fallback: see :class:`Fallback` and :func:`build_links`.
        max_length: see :func:`build_links`.
        on_too_long: see :func:`build_links`.
        extension: see :func:`build_links`.
        position: see :func:`build_links`.
        tolerance: see :func:`build_links`.
        on_misaligned: see :func:`build_links`.
        merge: union the rectangles before insertion. Only matters when
            ``extension`` is large enough to make neighbours touch; otherwise
            the dimers are disjoint and merging is wasted work.

    Returns:
        The links that were drawn, for verification and downstream use.

    Raises:
        ValueError: as :func:`build_links`.
    """
    import klayout.db as kdb

    links = build_links(
        matrix,
        width=width,
        axis=axis,
        step=step,
        stagger=stagger,
        phase=phase,
        pair_short_runs=pair_short_runs,
        fallback=fallback,
        max_length=max_length,
        on_too_long=on_too_long,
        extension=extension,
        position=position,
        tolerance=tolerance,
        on_misaligned=on_misaligned,
    )

    dbu = component.kcl.dbu
    region = kdb.Region()
    for link in links:
        region.insert(kdb.DBox(*link.box).to_itype(dbu))
    if merge:
        region.merge()

    component.shapes(_layer_index(component, layer)).insert(region)
    return links


def place_connectors(
    component: Any,
    links: Iterable[Link],
    connector: Any,
    *,
    rotate_columns: bool = True,
    lattice: float | tuple[float, float] | None = None,
    on_off_lattice: Literal["raise", "skip", "allow"] = "raise",
) -> list[Link]:
    """Place one instance of ``connector`` per link, centred on the link.

    The alternative to drawing flat polygons: ``connector`` is a cell you have
    already built and, if the rules require it, already slotted -- a bar of the
    right length and width, drawn centred on its own origin, with the two end
    circles carved out of its fill. Because every link is congruent to every
    other, that one cell serves the whole die, so the expensive work (a region
    boolean and a lattice fill) happens once instead of per link. Measured at
    roughly 85x faster and 4x smaller than slotting the links as one die-wide
    region; see the module docstring.

    The prototype must be drawn centred on the origin, since
    :attr:`Link.center` is the placement point.

    Args:
        component: target gdsfactory ``Component`` / kfactory ``KCell``,
            modified in place.
        links: links from :func:`build_links`. Mixed row and column links are
            fine as long as ``rotate_columns`` is set appropriately.
        connector: the prototype cell -- gdsfactory ``Component``, kfactory
            ``KCell``, ``klayout.db.Cell`` or a cell index. It must live in the
            same layout as ``component``.
        rotate_columns: place column links with a 90 degree rotation, so a
            single horizontal prototype covers both orientations. Set False if
            ``connector`` is already vertical, or is isotropic.
        lattice: slot pitch in um, as a scalar or ``(px, py)``. When given,
            every link centre is checked to be an integer number of pitches
            from the origin, which is the condition for the prototype's frozen
            slot lattice to stay globally continuous once placed. An
            off-lattice placement produces the correct slot *count*, so nothing
            downstream will notice -- hence the check.
        on_off_lattice: what to do with a link that fails the ``lattice``
            check -- ``"raise"``, ``"skip"`` it, or ``"allow"`` it through.

    Returns:
        The links that were actually placed, so ``len(placed) != len(links)``
        reveals anything skipped.

    Raises:
        ValueError: if a link centre is off the lattice while
            ``on_off_lattice="raise"``.
        TypeError: if ``connector`` yields no cell index.
    """
    import klayout.db as kdb

    dbu = component.kcl.dbu
    cell_index = _cell_index(connector)
    insert = component.kdb_cell.insert

    if lattice is None:
        px = py = 0.0
    elif isinstance(lattice, tuple | list):
        px, py = float(lattice[0]), float(lattice[1])
    else:
        px = py = float(lattice)

    placed: list[Link] = []
    for link in links:
        cx, cy = link.center
        if px and py:
            off_x = abs((cx / px + 0.5) % 1.0 - 0.5) * px
            off_y = abs((cy / py + 0.5) % 1.0 - 0.5) * py
            if max(off_x, off_y) > 0.5 * dbu:
                if on_off_lattice == "raise":
                    raise ValueError(
                        f"link {link.a}-{link.b} centres on "
                        f"({cx:.4f}, {cy:.4f}) um, which is "
                        f"({off_x:.4f}, {off_y:.4f}) um off a {px} x {py} um "
                        "lattice; the prototype's slot fill would not stay "
                        "continuous with the rest of the die"
                    )
                if on_off_lattice == "skip":
                    continue

        rotation = 1 if (rotate_columns and link.axis == "column") else 0
        insert(
            kdb.CellInstArray(
                cell_index,
                kdb.Trans(rotation, False, round(cx / dbu), round(cy / dbu)),
            )
        )
        placed.append(link)

    return placed


def group_by_prototype(
    links: Iterable[Link], *, decimals: int = 3
) -> dict[tuple[str, float], list[Link]]:
    """Bucket links by the prototype cell they would need.

    :func:`place_connectors` is only valid over congruent links, and a
    :class:`Fallback` pass breaks that: a single-file strip at one lattice
    pitch produces bars half the length of a checkerboard zone's. Grouping
    first turns one invalid placement into several valid ones -- build a
    prototype per bucket and place each bucket separately.

    Args:
        links: links from :func:`build_links`.
        decimals: rounding applied to the length before grouping, to absorb
            floating-point noise. Three decimals is one dbu at the usual
            0.001 um database unit.

    Returns:
        ``{(axis, length): links}``. With ``rotate_columns=True`` a row and a
        column bucket of equal length share one prototype, so a single-length
        die yields at most two entries.
    """
    groups: dict[tuple[str, float], list[Link]] = {}
    for link in links:
        groups.setdefault((link.axis, round(link.length, decimals)), []).append(link)
    return groups
