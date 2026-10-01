"""Global-lattice checkerboard fill inside arbitrary rectangular regions.

Written for gdsfactory 9.12 (kfactory backend).

Idea
----
One global grid spans the whole die, anchored at `origin` with `pitch`.
At every lattice point (i, j) we consider placing an instance of
`component` centered on that point. It's placed only when:

  1. (i + j) is even            -> checkerboard parity
  2. the component's full bbox
     fits inside at least one
     of the red fill regions    -> containment (with optional margin)
  3. its placed bbox does not
     intersect the union of
     `keepout_layers` grown by
     `keepout_clearance`         -> keepout clearance

Because the lattice is global (not per-region), the pitch is preserved
across regions: a component in region A and one in region B are always
on the same underlying grid.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Sequence

import gdsfactory as gf
import iprlayout_tower as ipr
import klayout.db as kdb
from gdsfactory.typings import ComponentSpec, LayerSpec

# (xmin, ymin, xmax, ymax) in microns
Region = tuple[float, float, float, float]

fill_regions: list[Region] = [
    # MESH AREA
    (-11203.084, 3275.59, -5865.09, 9770.70),
    (-9663.693, -9698.45, -5865.09, 3270.03),
    (-5558.19, -9698.45, -4912.60, 9748.59),
    (-4613.22, 3272.41, -1572.82, 9749.53),
    (-4613.22, -3213.02, -706.10, 3270.03),
    (-4613.22, -9698.30, -1559.62, -3215.25),
    (-606.08, -9698.30, 389.45, -3215.25),
    (-43.084, 3275.59, 5294.91, 9770.70),
    (1496.307, -9698.45, 5294.91, 3270.03),
    (5601.81, -9698.45, 6247.40, 9748.59),
    (6546.78, 3272.41, 9587.18, 9749.53),
    (6546.78, -3213.02, 10453.90, 3270.03),
    (6546.78, -9698.30, 9600.38, -3215.25),
    (10553.92, -9698.30, 11548.88, -3215.25),
    # MUA AREA
    (-11223.34, 10378.09, -4729.967, 11096.04),
    (-11223.34, 9754.53, -4729.967, 10024.26),
    (-56.393, 10378.09, 6436.98, 11096.04),
    (-56.393, 9754.53, 6436.98, 10024.26),
    # MUA LOOP
    (-11560.465, 9754.530, -11216.639, 11097.430),
    (6426.614, 9741.670, 6770.440, 11084.570),
    # THERMISTORS
    (-11488.83, 11253.60, -11399.39, 11553.23),
    (-10772.23, -273.58, -10682.79, 26.05),
    (-11311.45, -10900.25, -11222.01, -10600.62),
    (-1230.56, 10352.50, -1141.12, 10652.13),
    (209.84, -273.58, 299.28, 26.05),
    (746.86, -10354.75, 836.30, -10055.12),
    (10834.86, 11253.60, 10924.30, 11553.23),
    (11363.84, -92.15, 11453.28, 207.48),
    (11371.82, -10900.96, 11461.26, -10601.33),
    # DAISY CHAIN
    (-11929.967, 11986.22, -8249.71, 12266.95),
    (-12116.34, -12123.62, -11855.86, 12088.27),
    (-11855.86, -12214.79, -7800.28, -11944.37),
    (8311.83, -12214.22, 11996.66, -11944.37),
    (11823.56, -11944.37, 12088.64, 12074.153),
    (7829.47, 11991.69, 11903.89, 12262.22),
    # INNER DAISY CHAIN
    (-529.96, 5831.29, -408.52, 7611.49),
    (190.72, 1357.46, 319.17, 2767.43),
    (-342.15, -618.43, -225.25, 498.26),
    (550.55, -805.97, 659.91, 603.35),
    (190.05, -2975.91, 316.76, -1562.67),
    (542.38, -7280.82, 668.53, -5514.17),
]


def checkerboard_fill(
    die: ComponentSpec,
    component: ComponentSpec = ipr.flipchip_pad(port_orientation=90),
    fill_regions: Sequence[Region] = fill_regions,
    pitch: tuple[float, float] = (90.0, 90.0),
    origin: tuple[float, float] = (0.0, 0.0),
    offset: tuple[float, float] = (0.0, 0.0),
    checkerboard: bool = True,
    margin: float = 0.0,
    layer_fill_region: LayerSpec = (999, 1),
    keepout_layers: Sequence[LayerSpec] | None = None,
    keepout_clearance: float = 0.0,
    draw_regions: bool = True,
):
    """Fill rectangles with `component` on a shared global grid.

    Args:
        component: cell (or ComponentSpec) placed at each valid grid point.
        die: die cell (or ComponentSpec). Its bbox defines the die extent;
            fill regions must lie inside that bbox. The die itself is added
            as a reference to the output when `include_die=True`.
        fill_regions: iterable of (xmin, ymin, xmax, ymax) rectangles in the
            same coordinate frame as the die's bbox.
        pitch: (px, py) global grid pitch in um. Default (90, 90).
        origin: (x0, y0) anchor of the global grid in um. All lattice points
            are at (x0 + i*px, y0 + j*py) for integer i, j.
        checkerboard: if True, keep only lattice points where (i+j) is even.
        offset: (dx, dy) additional shift in um applied to every placed
            component. Containment is tested at the shifted position, so
            no pad can be pushed outside its fill region.
        margin: extra clearance required between the component bbox and the
            region edge. Component is placed iff bbox+margin fits inside.
        layer_fill_region: layer to draw each red rectangle outline on.
        keepout_layers: layers whose existing geometry blocks placement. Each
            item is a (layer, datatype) tuple. Shapes are collected recursively
            through the die's references, so anything already added to the die
            is picked up. Pass an empty list or None to disable.
        keepout_clearance: minimum distance in um between any placed component's
            bbox and any shape on `keepout_layers`. Implemented by growing the
            union of keepout shapes outward by this amount before the
            intersection test. Ignored when `keepout_layers` is empty.
        draw_regions: if True, draw the fill region outlines for reference.

    Returns:

    """
    comp = gf.get_component(component)
    die_c = gf.get_component(die)

    # Die extent from its bbox.
    dbb = die_c.dbbox()

    # Union of all shapes on `keepout_layers` in the die (recursive through
    # references), grown outward by `keepout_clearance`. A candidate placement
    # is rejected if its bbox intersects this region.
    dbu = die_c.kcl.dbu
    keepout_region = kdb.Region()
    if keepout_layers:
        for lyr in keepout_layers:
            if not (isinstance(lyr, tuple) and len(lyr) == 2):
                raise TypeError(
                    f"keepout_layers items must be (layer, datatype) tuples, "
                    f"got {lyr!r}"
                )
            layer_index = die_c.kcl.layer(kdb.LayerInfo(*lyr))
            keepout_region += kdb.Region(die_c.begin_shapes_rec(layer_index))
        keepout_region.merge()
        if keepout_clearance > 0:
            keepout_region.size(int(round(keepout_clearance / dbu)))

    dx0, dy0, dx1, dy1 = dbb.left, dbb.bottom, dbb.right, dbb.top

    # Component footprint in um.
    bbox = comp.dbbox()
    w, h = bbox.width(), bbox.height()
    bcx, bcy = bbox.center().x, bbox.center().y

    px, py = pitch
    ox, oy = origin
    sx, sy = offset
    ox += sx
    oy += sy

    if px <= 0 or py <= 0:
        raise ValueError(f"Pitch must be positive, got {pitch}.")

    # Fill regions must lie inside the die's bbox.
    for k, (rx0, ry0, rx1, ry1) in enumerate(fill_regions):
        if not (dx0 <= rx0 < rx1 <= dx1 and dy0 <= ry0 < ry1 <= dy1):
            raise ValueError(
                f"Fill region {k} = ({rx0}, {ry0}, {rx1}, {ry1}) is not "
                f"a valid rectangle inside the die bbox "
                f"({dx0}, {dy0}, {dx1}, {dy1})."
            )

    # Global lattice indices covering the die bbox.
    i_min = math.ceil((dx0 - ox) / px)
    i_max = math.floor((dx1 - ox) / px)
    j_min = math.ceil((dy0 - oy) / py)
    j_max = math.floor((dy1 - oy) / py)

    placed = 0
    for i, j in itertools.product(range(i_min, i_max + 1), range(j_min, j_max + 1)):
        if checkerboard and (i + j) % 2:
            continue

        cx = ox + i * px
        cy = oy + j * py

        # Placed bbox if the component's own bbox-center sits at (cx, cy).
        xmin, xmax = cx - w / 2, cx + w / 2
        ymin, ymax = cy - h / 2, cy + h / 2

        # 1. Must fit inside at least one fill region.
        for rx0, ry0, rx1, ry1 in fill_regions:
            if (
                xmin >= rx0 + margin
                and xmax <= rx1 - margin
                and ymin >= ry0 + margin
                and ymax <= ry1 - margin
            ):
                break
        else:
            continue  # no region contains this bbox

        # 2. Must not hit any keepout geometry (including clearance halo).
        if not keepout_region.is_empty():
            placed_box_dbu = kdb.Box(
                round(xmin / dbu),
                round(ymin / dbu),
                round(xmax / dbu),
                round(ymax / dbu),
            )
            if not (keepout_region & kdb.Region(placed_box_dbu)).is_empty():
                continue

        ref = die << comp
        ref.dmove((cx - bcx, cy - bcy))
        placed += 1

    if draw_regions:
        for rx0, ry0, rx1, ry1 in fill_regions:
            die.add_polygon(
                [(rx0, ry0), (rx1, ry0), (rx1, ry1), (rx0, ry1)],
                layer=layer_fill_region,
            )

    print(f"Placed {placed} pads.")

    return


if __name__ == "__main__":
    die = gf.Component("test")

    die_border = die << gf.components.die(
        size=(
            25000.0,
            25000.0,
        ),
        die_name=None,
        bbox_layer=(118, 134),
        draw_corners=False,
        layer=None,
    )
    die_border2 = die << gf.components.die(
        size=(25000, 25150),
        die_name=None,
        bbox_layer=(166, 0),
        draw_corners=False,
        layer=None,
    )

    # Fill regions in the die's coordinate frame (its bbox is (0, 0, 1600, 1900)).
    # (xmin,ymin,xmax,ymax)
    fill_regions: list[Region] = [
        (-11426.79, 3155.88, -10659.62, 9777.93),
        (-10357.87, 3155.880, -10210.70, 9777.93),
        (-9994.23, 3155.88, -9477.28, 9777.93),
        (-9251.68, -9742.24, -8734.73, 9777.93),
    ]

    tile = ipr.flipchip_pad()

    checkerboard_fill(
        die=die,
        component=tile,
        fill_regions=fill_regions,
        pitch=(90.0, 90.0),
        origin=(0.0, 0.0),
        checkerboard=True,
        draw_regions=True,
        margin=0.0,
    )

    die.show()
