"""Run the MT3 acute-notch fix over a die: preview, patch, verify.

Three phases, each printing a count rather than a dump:

1.  **Preview.**  ``find_sites`` reports how many notches exist and how they
    break down by orientation.  Nothing is modified, so this is safe to run
    against a die you have not decided to patch yet.  Skip it with
    ``--no-preview`` once the number is familiar -- it costs a full region
    extract and spacing check that :func:`patch_die` will repeat.
2.  **Patch.**  Geometry is added and the layout is written to a new file; the
    input is never modified in place.
3.  **Verify.**  The same check is re-run and must report nothing.  The merged
    polygon count must also be unchanged, since a drop would mean a patch had
    bridged two previously separate nets.

The process exit code is 0 only if every invariant held, so this can gate a
tape-out script directly.

Usage::

    python run_mt3_acute_patch.py v7b.oas --out v7b_patched.oas
    python run_mt3_acute_patch.py v7b.oas --dry-run
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import klayout.db as kdb
from v7b.tools.drc.mt3_acute_patch import (
    DEFAULT_DEPTH,
    DEFAULT_DISTANCE,
    PatchReport,
    find_sites,
    min_depth_for,
    patch_die,
)

LAYER = (28, 0)


def preview(cell: Any, layer: Any = LAYER, distance: float = DEFAULT_DISTANCE) -> int:
    """Count the acute notches without modifying anything.

    Args:
        cell: Top cell.
        layer: Layer spec.
        distance: The spacing rule in um.

    Returns:
        The number of sites found.
    """
    start = time.perf_counter()
    sites, unhandled = find_sites(cell, layer, distance)
    elapsed = time.perf_counter() - start

    print(f"[find]  {len(sites)} acute notches on {layer}  ({elapsed:.1f}s)")

    buckets = Counter((s.trans.angle * 90, s.trans.is_mirror()) for s in sites)
    for angle, mirror in sorted(buckets):
        tag = f"r{angle}" + ("m" if mirror else "")
        print(f"          {tag:>5}  {buckets[(angle, mirror)]}")

    if unhandled:
        print(f"[find]  WARNING {len(unhandled)} pairs are not axis/45 wedges")
        for pair in unhandled[:5]:
            print(f"          {pair.first} | {pair.second}")
        if len(unhandled) > 5:
            print(f"          ... and {len(unhandled) - 5} more")
    return len(sites)


def summarise(report: PatchReport, dbu: float) -> None:
    """Print the patch outcome and the invariants that must hold.

    Args:
        report: The result of :func:`patch_die`.
        dbu: Database unit in um, used to label the patch depth.
    """
    print(
        f"[patch] {len(report.sites)} patched"
        f"  ({report.rectangles} rect, {report.triangles} tri)"
    )
    print(f"[check] remaining violations : {len(report.remaining)}")
    print(
        f"[check] merged polygons      : "
        f"{report.polygons_before} -> {report.polygons_after}"
    )
    if report.unhandled:
        print(f"[check] unhandled pairs      : {len(report.unhandled)}")
    print(f"[check] {'PASS' if report.clean else 'FAIL'}")


def run(
    cell: Any,
    layer: Any = LAYER,
    distance: float = DEFAULT_DISTANCE,
    depth: float = DEFAULT_DEPTH,
    do_preview: bool = True,
) -> PatchReport:
    """Preview, patch and verify a cell that is already in memory.

    Call this directly from an existing build script when the die has not been
    written to disk yet.

    Args:
        cell: Top cell, modified in place.
        layer: Layer spec.
        distance: The spacing rule in um.
        depth: Fill depth back from the apex, in um.
        do_preview: Whether to run the counting pass first.

    Returns:
        The :class:`PatchReport`.
    """
    print(
        f"[rule]  {distance} um spacing, "
        f"fill {depth} um (minimum {min_depth_for(distance):.3f})"
    )
    if do_preview:
        preview(cell, layer, distance)

    start = time.perf_counter()
    report = patch_die(cell, layer, distance=distance, depth=depth)
    print(f"[patch] {time.perf_counter() - start:.1f}s")
    return report


def main(argv: list[str] | None = None) -> int:
    """Entry point.

    Args:
        argv: Command line arguments, defaulting to ``sys.argv``.

    Returns:
        0 if every invariant held, 1 otherwise.
    """
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("layout", type=Path, help="input GDS or OASIS")
    parser.add_argument("--out", type=Path, help="output path (default: *_patched)")
    parser.add_argument("--top", help="top cell name (default: the only top cell)")
    parser.add_argument("--layer", default="28/0", help="layer/datatype, default 28/0")
    parser.add_argument("--distance", type=float, default=DEFAULT_DISTANCE)
    parser.add_argument("--depth", type=float, default=DEFAULT_DEPTH)
    parser.add_argument(
        "--no-preview",
        action="store_true",
        help="skip the counting pass (saves a full scan)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="count only; write nothing"
    )
    args = parser.parse_args(argv)

    layer = tuple(int(v) for v in args.layer.split("/"))

    layout = kdb.Layout()
    layout.read(str(args.layout))
    tops = layout.top_cells()
    if args.top:
        cell = layout.cell(args.top)
        if cell is None:
            print(f"no cell named {args.top!r}", file=sys.stderr)
            return 1
    elif len(tops) == 1:
        cell = tops[0]
    else:
        names = ", ".join(c.name for c in tops)
        print(f"{len(tops)} top cells ({names}); pass --top", file=sys.stderr)
        return 1
    print(f"[read]  {args.layout}  top={cell.name}  dbu={layout.dbu}")

    if args.dry_run:
        preview(cell, layer, args.distance)
        return 0

    report = run(cell, layer, args.distance, args.depth, not args.no_preview)
    summarise(report, layout.dbu)

    if not report.clean:
        print("[write] skipped: verification failed", file=sys.stderr)
        return 1

    out = args.out or args.layout.with_name(
        f"{args.layout.stem}_patched{args.layout.suffix}"
    )
    layout.write(str(out))
    print(f"[write] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
