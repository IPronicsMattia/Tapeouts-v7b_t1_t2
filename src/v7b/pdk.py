import math
import re
import sys
from pathlib import Path

import gdsfactory as gf
import iprlayout_tower as ipr
import kfactory as kf
import numpy as np
from gdsfactory.get_factories import get_cells
from gdsfactory.typings import ComponentSpec, CrossSectionSpec, LayerSpec
from iprlayout_tower.tech import LAYER


@gf.cell
def ipronics_logo() -> gf.Component:
    path = Path(__file__).resolve().parents[1] / "v7b" / "logo" / "ipronics_logo.gds"

    c = gf.import_gds(
        gdspath=path,
        cellname="Logo_ipronics",
    )

    return c


@gf.cell
def v7b_logo() -> gf.Component:
    path = Path(__file__).resolve().parents[1] / "v7b" / "logo" / "v7b_logo.gds"

    c = gf.import_gds(
        gdspath=path,
        cellname="v7b_logo",
    )

    return c


@gf.cell
def phase_shifter_cassette(
    loops: int = 7,
    wv_length: float = 50,
    width_center: float = 0.41,
    width_var: float = 0.1,
    width_all: float = 0.41,
    spacing: float = 0.75,
    bend_extra_spacing: float = 0.75,
    bend: gf.Component = "bend_euler_custom_width",
    taper1: gf.Component = "rib_taper",
    taper2: gf.Component = "rib_taper",
    taper: gf.Component = "rib_taper",
    htr_y_displacement: float = 0,
    htr_x_displacement: float = 0,
    htr_width: float = 3,
    right_out_leng: float = 0,
    inverted_ports: bool = False,
) -> gf.Component:
    c = gf.Component()

    width2 = width_center + width_var

    wv_length_center = wv_length - 17  # To match Juan's heater
    xs1 = gf.get_cross_section("strip", width=width_center)
    xs2 = gf.get_cross_section("strip", width=width2)
    xs_all = gf.get_cross_section("strip", width=width_all)

    bend = gf.get_component(bend)
    taper1 = gf.get_component(taper1)
    taper2 = gf.get_component(taper2)

    left_in = []
    right_out = []

    loop_aux = int((loops - 3) / 2)

    for i in range(loops):
        xs = xs1 if i % 2 == 0 else xs2
        st = c << gf.c.straight(
            length=wv_length_center + (spacing + xs1.width) * 2 * i, cross_section=xs
        )
        st.move((st.x, st.y), (0, st.y - (spacing + xs1.width / 2 + xs2.width / 2) * i))

        for j in range(2):
            if j % 2 == 0:
                leng = (
                    bend.info["radius"] * 2
                    - spacing
                    - xs_all.width
                    + (bend_extra_spacing * (i - 1))
                    if i > loop_aux
                    else bend_extra_spacing * i
                )
                aux = c << gf.c.straight(
                    length=leng,
                    cross_section=xs,
                )
                aux.connect("o2", st["o1"])
            else:
                leng = (
                    bend.info["radius"] * 2
                    - spacing
                    - xs_all.width
                    + bend_extra_spacing * (i - 1)
                    if i > loop_aux + 1
                    else bend_extra_spacing * i
                )
                aux = c << gf.c.straight(
                    length=leng,
                    cross_section=xs,
                )
                aux.connect("o1", st["o2"])

            tap = c << taper1 if i % 2 == 0 else c << taper2
            tap.connect("o2", aux[f"o{1 + j}"])
            left_in.append(tap["o1"]) if j % 2 == 0 else right_out.append(tap["o1"])

    for i in range(int((loops - 1) / 2)):
        ben = c << bend
        ben.connect("o1", left_in[loop_aux - i], mirror=True)
        gf.routing.route_single(
            c,
            ben["o2"],
            left_in[loop_aux + 1 + i],
            auto_taper=False,
            bend=bend,
            cross_section=xs_all,
        )
        ben = c << bend
        ben.connect("o1", right_out[loop_aux + 1 - i])
        gf.routing.route_single(
            c,
            ben["o2"],
            right_out[loop_aux + 2 + i],
            auto_taper=False,
            bend=bend,
            cross_section=xs_all,
        )

    aux = c << bend
    aux.connect("o1", right_out[0])
    ben = c << bend
    ben.connect("o1", aux["o2"], mirror=True)

    st2 = c << gf.c.straight(length=right_out_leng, cross_section=xs_all)
    st2.connect("o1", ben["o2"])

    st1 = c << gf.c.straight(length=left_in[loops - 1].x - c.xmin, cross_section=xs_all)
    st1.connect("o2", left_in[loops - 1])

    c.add_port("o2", port=st1["o1"])
    c.add_port("o1", port=st2["o2"])

    # METAL
    xs_htr = gf.get_cross_section("heater_metal", width=htr_width)
    htr = c << gf.c.straight(wv_length, cross_section=xs_htr)
    center = (
        right_out[0].x - taper.dxsize + 1,
        (right_out[0].y + right_out[loops - 1].y) / 2,
    )
    htr.move(
        (htr.xmax, htr.y),
        (center[0] + htr_x_displacement, center[1] + htr_y_displacement),
    )

    tap_left = c << gf.c.taper(
        5,
        11,
        4,
        LAYER.tnr,
        port_types=("electrical", "electrical"),
        port_names=("e1", "e2"),
    )
    tap_right = c << gf.c.taper(
        5,
        11,
        4,
        LAYER.tnr,
        port_types=("electrical", "electrical"),
        port_names=("e1", "e2"),
    )

    tap_left.connect("e2", htr["e1"])
    tap_right.connect("e2", htr["e2"])

    via_left = c << ipr.via_tnr_metal3()
    via_left.connect("e3", tap_left["e1"], allow_layer_mismatch=True)
    via_right = c << ipr.via_tnr_metal3()
    via_right.connect("e1", tap_right["e1"], allow_layer_mismatch=True)
    c.add_port("e1", port=via_left["e2"] if not inverted_ports else via_left["e4"])
    c.add_port("e2", port=via_right["e2"] if not inverted_ports else via_right["e4"])

    c.info["length"] = wv_length
    c.info["ps_length"] = wv_length
    c.info["width_center"] = width_center
    c.info["width_var"] = width_var
    c.info["width"] = width_all
    c.info["htr_width"] = htr_width
    c.info["htr_angle"] = 0

    return c


@gf.cell(set_name=False)
def v7b_puc(
    arm_separation: float = 37,
    PUC_type: str = "Cassette",
    phase_shifter: gf.Component = None,
    splitter: gf.Component = "rib_mmi",
    bend: gf.Component = "bend_euler_custom_width",
    ac: gf.Component = "bend_bezier_s_custom_width",
    cross_section: gf.CrossSection = "strip",
    ac_side: tuple = (1, 1),
    puc_number: int = 0,
) -> gf.Component:
    c = gf.Component(f"puc{puc_number}")

    xs = gf.get_cross_section(cross_section)
    splitter = gf.get_component(splitter)
    phase_shifter = gf.get_component(phase_shifter)
    bend_r3 = gf.get_component(bend)
    ac = gf.get_component(ac)

    arm_separation = arm_separation - 12
    upper_phase_shifter = c << phase_shifter
    upper_phase_shifter.mirror_y()
    lower_phase_shifter = c << phase_shifter
    lower_phase_shifter.movey(
        lower_phase_shifter["o1"].y,
        upper_phase_shifter["o1"].y - arm_separation - xs.width,
    )
    center = (c.x, c.y)

    if PUC_type == "Cassette":
        splitter_x_shift = 0
    elif PUC_type == "Mushroom":
        splitter_x_shift = -26.598
    else:
        raise ValueError("PUC_type must be: 'Cassette' or 'Mushroom'.")

    splitter_right = c << splitter
    splitter_right.move(
        (splitter_right["o1"].x, splitter_right.y),
        (
            upper_phase_shifter["o1"].x + bend.info["radius"] * 2 + splitter_x_shift,
            center[1],
        ),
    )

    if ac_side[1]:
        ac1 = c << ac
        ac1.connect("o1", splitter_right["o3"])
        c.add_port("o3", port=ac1["o2"])
        ac2 = c << ac
        ac2.connect("o1", splitter_right["o4"], mirror=True)
        c.add_port("o4", port=ac2["o2"])
    else:
        c.add_port("o3", port=splitter_right["o3"])
        c.add_port("o4", port=splitter_right["o4"])

    gf.routing.route_single(
        c,
        splitter_right["o2"],
        upper_phase_shifter["o1"],
        bend=bend_r3,
        cross_section=xs,
        auto_taper=False,
    )
    gf.routing.route_single(
        c,
        splitter_right["o1"],
        lower_phase_shifter["o1"],
        bend=bend_r3,
        cross_section=xs,
        auto_taper=False,
    )

    splitter_left = c << splitter
    splitter_left.move(
        (splitter_left["o3"].x, splitter_left.y),
        (
            upper_phase_shifter["o2"].x - bend.info["radius"] * 2 - splitter_x_shift,
            center[1],
        ),
    )

    gf.routing.route_single(
        c,
        splitter_left["o3"],
        upper_phase_shifter["o2"],
        bend=bend_r3,
        cross_section=xs,
        auto_taper=False,
    )
    gf.routing.route_single(
        c,
        splitter_left["o4"],
        lower_phase_shifter["o2"],
        bend=bend_r3,
        cross_section=xs,
        auto_taper=False,
    )

    if ac_side[0]:
        ac1 = c << ac
        ac1.connect("o1", splitter_left["o2"], mirror=True)
        c.add_port("o2", port=ac1["o2"])
        ac2 = c << ac
        ac2.connect("o1", splitter_left["o1"])
        c.add_port("o1", port=ac2["o2"])
    else:
        c.add_port("o2", port=splitter_left["o2"])
        c.add_port("o1", port=splitter_left["o1"])

    c.add_port("e1", port=lower_phase_shifter["e1"])
    c.add_port("e2", port=upper_phase_shifter["e1"])
    c.add_port("e3", port=upper_phase_shifter["e2"])
    c.add_port("e4", port=lower_phase_shifter["e2"])

    c.flatten()

    c.remove_layers([(118, 120)], recursive=True)

    return c


@gf.cell
def bend_modified_hermite(
    radius: float = 5.0,
    angle: float = 45.0,
    a1: float = 5.213,
    a2: float = 5.601,
    width: float = 0.41,
    npoints: int = 100,
    direction: str = "ccw",
    cross_section: CrossSectionSpec = "strip",
    loss: float = 0.0001,
    length_access: float = 3,
    access: bool = True,
    sim: bool = True,
    show: bool = False,
    **kwargs,
) -> gf.Component:
    """
    Modified Hermite bend using inner and outer boundary curves.
    Developed following the article: http://doi.org/10.3390photonics13020175.
    Generalized for any angle.
    Constraint:
        - a1 <= a2
    """

    if direction not in {"ccw", "cw"}:
        raise ValueError('direction must be either "ccw" or "cw".')
    if a1 > a2:
        raise ValueError("Require a1 <= a2 for modified Hermite bends.")

    x = gf.get_cross_section(cross_section, **kwargs)
    radius = radius or x.radius
    layer_bend = x.layer
    angle_rad = angle * np.pi / 180

    c = gf.Component()

    t = np.linspace(0.0, 1.0, npoints)

    c1 = 1 - 3 * t**2 + 2 * t**3
    c2 = t - 2 * t**2 + t**3
    c3 = -(t**2) + t**3
    c4 = 3 * t**2 - 2 * t**3

    R_in = radius - width / 2  # radius of the inner boundary
    R_out = radius + width / 2  # radius of the outer boundary

    # Input tangent: +x, so width offset is ±y
    # Output tangent: +y, so width offset is ±x
    p1 = np.array([0.0, width / 2])  # inner boundary start
    p2 = np.array([0.0, -width / 2])  # outer boundary start
    p3 = np.array(
        [R_in * np.sin(angle_rad) + p1[0], R_in * (1 - np.cos(angle_rad)) + p1[1]]
    )  # inner boundary end
    p4 = np.array(
        [R_out * np.sin(angle_rad) + p2[0], R_out * (1 - np.cos(angle_rad)) + p2[1]]
    )  # outer boundary end

    # Inner boundary tangent vectors
    m1 = np.array([a1, 0.0])
    m3 = np.array([a1 * np.cos(angle_rad), a1 * np.sin(angle_rad)])
    # Outer boundary tangent vectors
    m2 = np.array([a2, 0.0])
    m4 = np.array([a2 * np.cos(angle_rad), a2 * np.sin(angle_rad)])

    inner = c1[:, None] * p1 + c2[:, None] * m1 + c3[:, None] * m3 + c4[:, None] * p3

    outer = c1[:, None] * p2 + c2[:, None] * m2 + c3[:, None] * m4 + c4[:, None] * p4

    if access:
        n_acc = max(3, int(npoints * length_access / max(radius, 1e-6) / 2))

        s_in = np.linspace(0.0, length_access, n_acc)
        s_out = np.linspace(0.0, length_access, n_acc)

        inner_in = np.column_stack(
            (-length_access + s_in, np.full_like(s_in, width / 2))
        )
        outer_in = np.column_stack(
            (-length_access + s_in, np.full_like(s_in, -width / 2))
        )

        inner_out = np.column_stack(
            (
                R_in * np.sin(angle_rad) + s_out * np.cos(angle_rad),
                R_in * (1 - np.cos(angle_rad)) + width / 2 + s_out * np.sin(angle_rad),
            )
        )

        outer_out = np.column_stack(
            (
                R_out * np.sin(angle_rad) + s_out * np.cos(angle_rad),
                R_out * (1 - np.cos(angle_rad)) - width / 2 + s_out * np.sin(angle_rad),
            )
        )

        inner = np.vstack([inner_in[:-1], inner, inner_out[1:]])
        outer = np.vstack([outer_in[:-1], outer, outer_out[1:]])

    polygon = np.vstack([outer, inner[::-1]])

    if direction == "cw":
        polygon[:, 1] *= -1

    c.add_polygon(polygon, layer=layer_bend)

    if sim and cross_section == "nitride2":
        c.add_polygon(polygon, layer=LAYER.HAT_AN)

    def enforce_even_third_decimal(value: float) -> float:
        v = round(value * 1000)
        if v % 2 != 0:
            v += 1
        return v / 1000

    o1_center = (0.0, 0.0)
    o2_center = (
        radius * np.sin(angle_rad),
        (
            radius * (1 - np.cos(angle_rad))
            if direction == "ccw"
            else -(radius * (1 - np.cos(angle_rad)))
        ),
    )

    c.add_port(
        name="o1",
        center=o1_center,
        width=enforce_even_third_decimal(width),
        orientation=180,
        layer=layer_bend,
    )

    c.add_port(
        name="o2",
        center=o2_center,
        width=enforce_even_third_decimal(width),
        orientation=angle if direction == "ccw" else 360 - angle,
        layer=layer_bend,
    )

    centerline = 0.5 * (inner + outer)
    seg = np.diff(centerline, axis=0)

    c.info["length"] = float(np.round(np.sum(np.sqrt(np.sum(seg**2, axis=1))), 3))
    c.info["dy"] = float(np.round(abs(centerline[-1, 1] - centerline[0, 1]), 3))
    c.info["radius"] = radius
    c.info["width"] = width
    c.info["angle"] = angle
    c.info["a1"] = float(a1)
    c.info["a2"] = float(a2)
    c.info["loss"] = loss

    c.add_route_info(
        cross_section=x,
        length=c.info["length"],
        n_bend_90=abs(angle / 90.0),
    )

    c.flatten()

    if show:
        c.show()

    return c


@gf.cell
def spaced_bend(angle: int = 90, width: float = 0.41) -> gf.Component:
    c = gf.Component()
    xs = gf.get_cross_section("strip", width=0.41, radius_min=3.0)
    bend = c << ipr.bend_euler_custom_width(angle=angle, cross_section=xs)
    st = c << gf.c.straight(0.5, cross_section=xs)
    st.connect("o1", bend["o1"])
    c.add_port("o1", port=st["o2"])
    st = c << gf.c.straight(0.5, cross_section=xs)
    st.connect("o1", bend["o2"])
    c.add_port("o2", port=st["o2"])

    c.info["length"] = bend.cell.info["length"] + 1
    return c

@gf.cell
def spaced_taper(taper, straight) -> gf.Component:
    c = gf.Component()
    kwargs = {'bb2': taper,
              'straight': straight}
    tp = c << ipr.bb_straight_bb(length=1, **kwargs)
    for port in tp:
        c.add_port(name=port.name, port=port)
    return c


@gf.cell(set_name=False)
def custom_shallow_transition() -> gf.Component:
    c = gf.Component("si_gwg_transition_1000_410")

    ref = c << ipr.layer_transition_single_taper(
        m_RIB=0.642,
        m_SLAB=0.561,
        width_RIB_in=1,
        width_RIB_out=0.41,
        width_SLAB_in=1,
        width_SLAB_out=3.074,
        length_SLAB=10,
        length_total=10,
        layers=[[171, 0], [172, 0], [223, 0]],
        width_GRAT_SLAB=5.0,
        GRAT=False,
        SLAB=True,
        access=False,
        length_access=1.0,
        npoints=1000,
    )

    c.add_port("o1", port=ref["o1"])
    c.add_port("o2", port=ref["o2"])

    c.flatten()

    c.copy_layers({LAYER.rwg: LAYER.gwg}, recursive=True)

    layer_idx = gf.kcl.layer(*LAYER.gwg)

    region = gf.kdb.Region(c.begin_shapes_rec(layer_idx))
    region.merge()
    region.size(int(1.0 / gf.kcl.dbu))

    c.shapes(layer_idx).insert(region)

    return c


@gf.cell
def custom_sin_cross_compensation(ncross: int, randoms: list) -> gf.Component:
    c = gf.Component()

    xs = gf.get_cross_section("strip", width=0.93)
    xs_n = gf.get_cross_section("nitride2", width=2)

    cross3D = ipr.crossing_3D(
        cross_section1=xs,
        cross_section2=xs_n,
        length1=10,
        length2=0.93,
        angle=90,
    )

    if ncross == 0 or ncross == 71:
        st_ref = c << gf.c.straight(1, cross_section=xs_n)
    else:
        st_ref = c << gf.c.straight(3.2 + randoms[70 - ncross], cross_section=xs_n)
    c.add_port("o1", port=st_ref["o1"])

    for i in range(ncross):
        cross_ref = c << cross3D
        cross_ref.connect("o2", st_ref["o2"])

        sin_ext = c << gf.c.rectangle(
            (1, 0.93), (171, 0), port_type="optical", port_orientations=[0]
        )
        sin_ext.connect("o1", cross_ref["o3"])
        sin_ext = c << gf.c.rectangle(
            (1, 0.93), (171, 0), port_type="optical", port_orientations=[0]
        )
        sin_ext.connect("o1", cross_ref["o1"])

        if i != ncross - 1:
            st_ref = c << gf.c.straight(
                3.2 + randoms[71 - ncross + i], cross_section=xs_n
            )
        else:
            st_ref = c << gf.c.straight(1, cross_section=xs_n)
        st_ref.connect("o1", cross_ref["o4"])

    c.add_port("o2", port=st_ref["o2"])

    return c


def named_fill_region(
    die: ComponentSpec,
    name_regex: str = r"slot_rect.*",
    rect_layer: LayerSpec | None = (28, 0),
    use_bbox: bool = False,
) -> kf.kdb.Region:
    """Region covering every instance of the components matching `name_regex`.

    Args:
        die: the die component to search.
        name_regex: full-match regex for the rectangle component cell names.
            gdsfactory appends parameters, so use a trailing `.*`.
        rect_layer: collect shapes on this layer from inside the matched cells.
            Set None (or use_bbox=True) to use each instance's bounding box.
        use_bbox: use the instance bbox instead of its shapes. Cheaper, but for
            a ROTATED instance the bbox is larger than the shape itself.

    Returns:
        Merged Region in die coordinates. Anything outside the matched cells
        (e.g. connecting paths on the same layer) is not included.
    """

    comp = gf.get_component(die)
    layout = comp.kcl.layout
    rx = re.compile(name_regex)
    targets = [c.cell_index() for c in layout.each_cell() if rx.fullmatch(c.name)]
    if not targets:
        names = sorted({c.name for c in layout.each_cell()})
        raise ValueError(f"no cells matched {name_regex!r}. Available: {names}")

    li = comp.kcl.layer(rect_layer[0], rect_layer[1]) if rect_layer else None

    region = kf.kdb.Region()
    it = comp.kdb_cell.begin_instances_rec()
    it.targets = targets
    while not it.at_end():
        total = it.trans() * it.inst_trans()
        cell = layout.cell(it.inst_cell().cell_index())
        if use_bbox or li is None:
            region.insert(cell.bbox().transformed(total))
        else:
            region += kf.kdb.Region(cell.begin_shapes_rec(li)).transformed(total)
        it.next()
    return region.merged()


def fill_region_fast(
    target: gf.Component,
    area: kf.kdb.Region,
    slot_size: float = 1.0,
    pitch: float = 2.0,
    slot_layer: LayerSpec = (28, 20),
    anchor: tuple[float, float] | None = (0.0, 0.0),
    fill_cell_name: str = "slot_fill_cell",
) -> gf.Component:
    """Fill `area` with slot instances inside `target`, using the native engine.

    Args:
        target: component to place the fill instances into (modified in place).
        area: the allowed fill region, already margin-shrunk and keep-out-carved.
        slot_size: side of each square slot (um).
        pitch: center-to-center slot spacing (um).
        slot_layer: layer of the slot square.
        anchor: global lattice origin, so pitch stays continuous die-wide.
            Pass None to let KLayout optimize per polygon: that packs in more
            slots, but the lattice is no longer continuous between rectangles.
        fill_cell_name: name for the 1-slot fill cell.

    Returns:
        `target`, for convenience.
    """
    layout = target.kcl.layout
    dbu = target.kcl.dbu
    s = round(slot_size / dbu)
    p = round(pitch / dbu)

    # the unit cell that gets instanced everywhere
    fc = layout.create_cell(fill_cell_name)
    fc.shapes(layout.layer(slot_layer[0], slot_layer[1])).insert(kf.kdb.Box(0, 0, s, s))
    fc_bbox = kf.kdb.Box(0, 0, s, s)

    # NOTE: row_step needs +X, column_step needs +Y (KLayout requirement).
    row_step = kf.kdb.Vector(p, 0)
    column_step = kf.kdb.Vector(0, p)

    # fill_region aligns the fill box's LOWER-LEFT corner to origin, but we want
    # slot CENTERS on the lattice, so shift by half a slot.
    if anchor is None:
        origin = None
    else:
        origin = kf.kdb.Point(
            round((anchor[0] - slot_size / 2) / dbu),
            round((anchor[1] - slot_size / 2) / dbu),
        )

    target.kdb_cell.fill_region(
        area, fc.cell_index(), fc_bbox, row_step, column_step, origin
    )
    return target


@gf.cell
def fill_named_rectangles_fast(
    die: ComponentSpec,
    name_regex: str = r"slot_rect.*",
    rect_layer: LayerSpec | None = (28, 0),
    no_fill_layers: tuple[LayerSpec, ...] = ((118, 131),),
    slot_size: float = 1.0,
    pitch: float = 2.0,
    margin: float = 1.0,
    keepout_gap: float = 0.5,
    anchor: tuple[float, float] | None = (0.0, 0.0),
    slot_layer: LayerSpec = (28, 20),
    use_bbox: bool = False,
) -> gf.Component:
    """Fill only the rectangle components matched by name, avoiding no-fill layers.

    Args:
        die: die component
        name_regex: full-match regex selecting the rectangle components.
        rect_layer: layer of the rectangle shapes inside those components.
        no_fill_layers: layers that must stay slot-free.
        slot_size: side of each square slot (um).
        pitch: center-to-center slot spacing (um).
        margin: clear border inside each rectangle (um).
        keepout_gap: clearance around no-fill shapes (um).
        anchor: global lattice origin, keeping pitch continuous die-wide.
        slot_layer: layer to draw slots on.
        use_bbox: use instance bboxes instead of shapes (see named_fill_region).

    Returns:
        A Component holding only the slots.
    """

    comp = gf.get_component(die)
    c = gf.Component()
    dbu = c.kcl.dbu

    area = named_fill_region(comp, name_regex, rect_layer, use_bbox)
    if margin:
        area = area.sized(-round(margin / dbu))

    for layer in no_fill_layers:
        li = comp.kcl.layer(layer[0], layer[1])
        ko = kf.kdb.Region(comp.kdb_cell.begin_shapes_rec(li))
        if not ko.is_empty():
            if keepout_gap:
                ko = ko.sized(round(keepout_gap / dbu))
            area = area - ko

    fill_region_fast(
        c, area, slot_size=slot_size, pitch=pitch, slot_layer=slot_layer, anchor=anchor
    )

    c.info["instances"] = c.kdb_cell.child_instances()
    return c


def _grid(size_x, size_y, slot_size, pitch, margin, slot_layer):
    """A centered 2D array of squares that fills a size_x by size_y area."""
    slot = gf.components.rectangle(
        size=(slot_size, slot_size), layer=slot_layer, centered=True
    )
    usable_x = size_x - 2 * margin
    usable_y = size_y - 2 * margin
    ncols = max(1, int(math.floor((usable_x - slot_size) / pitch)) + 1)
    nrows = max(1, int(math.floor((usable_y - slot_size) / pitch)) + 1)
    return gf.components.array(
        slot,
        columns=ncols,
        rows=nrows,
        column_pitch=pitch,
        row_pitch=pitch,
        centered=True,
        add_ports=False,
    )


@gf.cell
def add_slot_fill(
    component: ComponentSpec,
    slot_size: float = 1.0,
    pitch: float = 2.0,
    margin: float = 1.0,
    outer_layer: LayerSpec = (1, 0),
    slot_layer: LayerSpec = (2, 0),
    draw_outer: bool = True,
    keepout_layer: LayerSpec | None = None,
    keepout_gap: float = 1.0,
) -> gf.Component:
    """Fill the bounding box of an existing component with the slot grid.

    Useful to fill the whole square around a waveguide (e.g. your spiral).
    The waveguide stays on its own layer; if you want the slots cleared away
    from it, pass `keepout_layer` (the waveguide layer) and a `keepout_gap`.

    Args:
        component: the component to fill around (its bbox defines the square).
        keepout_layer: if given, slots overlapping this layer (grown by
            keepout_gap) are removed so the waveguide stays slot-free.
        keepout_gap: how far the keep-out extends beyond the waveguide (um).
        (other args as in slot_fill)
    """
    comp = gf.get_component(component)
    bbox = comp.bbox()
    xmin, ymin, xmax, ymax = bbox.left, bbox.bottom, bbox.right, bbox.top
    size_x, size_y = xmax - xmin, ymax - ymin
    cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2

    c = gf.Component()
    c << comp  # keep the original (waveguide) content

    if draw_outer:
        outer = c << gf.components.rectangle(
            size=(size_x, size_y), layer=outer_layer, centered=True
        )
        outer.move((cx, cy))

    grid = _grid(size_x, size_y, slot_size, pitch, margin, slot_layer)

    if keepout_layer is None:
        g = c << grid
        g.move((cx, cy))
        return c

    # keep-out: subtract the waveguide region (grown by keepout_gap) from the grid.
    import kfactory as kf

    grid_c = gf.Component()
    gref = grid_c << grid
    gref.move((cx, cy))
    grid_c.flatten()

    dbu = c.kcl.dbu
    slot_li = grid_c.kcl.layer(*slot_layer)
    ko_li = comp.kcl.layer(*keepout_layer)

    grid_region = kf.kdb.Region(grid_c.begin_shapes_rec(slot_li))
    ko_region = kf.kdb.Region(comp.begin_shapes_rec(ko_li)).sized(
        int(keepout_gap / dbu)
    )
    result = grid_region - ko_region  # drop/clip slots that touch the waveguide

    filled = gf.Component()
    filled.shapes(filled.kcl.layer(*slot_layer)).insert(result)
    c << filled
    return c


@gf.cell()
def dc_connector() -> gf.Component:
    c = gf.Component()

    rect1 = c << gf.c.rectangle((35, 20), LAYER.metal3)
    rect1.movex(rect1.xmin, 0)

    rect = gf.c.rectangle((110, 20), LAYER.metal3)
    filled = add_slot_fill(
        rect,
        slot_size=2.4,
        pitch=4.8,
        margin=2.4,
        slot_layer=(28, 20),
        keepout_gap=1.0,
        draw_outer=False,
    )
    center = c << filled
    center.movex(center.xmin, rect1.xmax)

    rect2 = c << gf.c.rectangle((35, 20), LAYER.metal3)
    rect2.movex(rect2.xmin, center.xmax)

    c.add_port("e1", port=rect1["e1"])
    c.add_port("e2", port=rect2["e3"])

    c.flatten()

    c.move((c.x, c.y), (c.x - c.xsize / 2, c.y - c.ysize / 2))

    return c


@gf.cell()
def mzi_cell(
    order_mzi_length: float = 9.5054,
    splitter: ComponentSpec = "mmi_luka",
    cross_section: CrossSectionSpec = "strip",
    cross_section2: CrossSectionSpec = "strip",
    extra_component: ComponentSpec | None = None,
) -> gf.Component:
    """This structure allows for the generation of a mzi cell,
    two splitters joined by the respective cross-sections

    """
    c = gf.Component()
    splitter = gf.get_component(splitter)
    cross_section = gf.get_cross_section(cross_section)
    splitter_length = splitter["o3"].x - splitter["o2"].x
    if extra_component:
        tap = gf.get_component(extra_component)

    mzis = [0] * 2
    vectorx = [
        0,
        splitter_length + 60,
    ]
    vectory = [0, 0]

    ports1 = []
    ports2 = []

    lengths = [
        order_mzi_length + 2,
        2,
    ]

    for n in range(2):
        mzis[n] = c << splitter
        mzis[n].move([vectorx[n], vectory[n]])
        if n % 2 == 0:
            sbend_1 = c << ipr.bend_bezier_s_custom_width()
            sbend_2 = c << ipr.bend_bezier_s_custom_width()
            sbend_1.connect("o2", mzis[n].ports["o1"])
            sbend_2.mirror_y()
            sbend_2.connect("o2", mzis[n].ports["o2"])

            c.add_port(f"o{2 * n + 3}", port=sbend_1.ports["o1"])
            c.add_port(f"o{2 * n + 2}", port=sbend_2.ports["o1"])

            ports1.append(mzis[n].ports["o4"])
            line = c << ipr.straight(length=10, cross_section=cross_section)
            line.connect("o1", mzis[n].ports["o3"])
            ports1.append(line["o2"])
        else:
            sbend_1 = c << ipr.bend_bezier_s_custom_width()
            sbend_2 = c << ipr.bend_bezier_s_custom_width()
            sbend_1.mirror_y()
            sbend_1.connect("o1", mzis[n].ports["o4"])
            sbend_2.connect("o1", mzis[n].ports["o3"])

            c.add_port(f"o{2 * n + 2}", port=sbend_1.ports["o2"])
            c.add_port(f"o{2 * n - 1}", port=sbend_2.ports["o2"])

            ports2.append(mzis[n].ports["o1"])
            line = c << ipr.straight(length=10, cross_section=cross_section)
            line.connect("o2", mzis[n].ports["o2"])
            ports2.append(line["o1"])

    for n in range(2):
        if extra_component is None:
            steps = [
                {"dx": 10},
                {"dy": -(lengths[n] / 2 + 10)},
                {"dx": 20 if n % 2 != 0 else 40},
                {"dy": (lengths[n] / 2 + 10)},
            ]
            gf.routing.route_single(
                c,
                ports1[n],
                ports2[n],
                steps=steps,
                bend=ipr.bend_euler_custom_width(
                    cross_section=cross_section,
                    width_in=0.41,
                    width_out=0.41,
                    width_center=0.5,
                    p=0.466,
                    m=1.767,
                    radius=5,
                ),
                cross_section=cross_section,
                auto_taper=False,
                straight=ipr.straight,
            )
        else:
            bend = ipr.bend_euler_custom_width(
                cross_section=cross_section,
                width_in=0.41,
                width_out=0.41,
                width_center=0.5,
                p=0.466,
                m=1.767,
                radius=5,
            )
            bd1 = c << bend
            bd1.mirror_y()
            bd1.connect("o1", ports1[n])
            bd2 = c << bend
            bd2.connect("o1", ports2[n])
            taper1 = c << tap
            taper1.connect("o1", bd1["o2"])
            st = c << gf.c.straight(
                cross_section=cross_section2, length=lengths[n] / 2.0
            )
            st.connect("o1", taper1["o2"])
            taper1 = c << tap
            taper1.connect("o2", st["o2"])
            ports1[n] = taper1["o1"]
            taper2 = c << tap
            taper2.connect("o1", bd2["o2"])
            st = c << gf.c.straight(
                cross_section=cross_section2, length=lengths[n] / 2.0
            )
            st.connect("o1", taper2["o2"])
            taper2 = c << tap
            taper2.connect("o2", st["o2"])
            ports2[n] = taper2["o1"]
            gf.routing.route_single(
                c,
                ports1[n],
                ports2[n],
                # steps=steps,
                bend=ipr.bend_euler_custom_width(
                    cross_section=cross_section,
                    width_in=0.41,
                    width_out=0.41,
                    width_center=0.5,
                    p=0.466,
                    m=1.767,
                    radius=5,
                ),
                cross_section=cross_section,
                auto_taper=False,
                straight=ipr.straight,
            )

    return c


@gf.cell
def mesh_72x72_mockup():
    """
    Create a rectangle with same dimension of the real mesh and just the ports for faster testing.
    """

    # Create the component
    mesh_ = gf.Component()
    mesh_ << gf.components.rectangle(size=(11318.714, 19413.650), layer=(1, 0))

    # Cross section to be used
    xs = gf.get_cross_section("strip", width=0.41, radius_min=3.0)

    # Place the ports
    for idx in range(72):
        # Top left
        mesh_.add_port(
            name=f"o{idx + 1}",
            center=(3.85, 19389.82 - 90 * idx),
            width=0.41,
            orientation=180,
            cross_section=xs,
            port_type="optical",
        )

        # Bot right
        mesh_.add_port(
            name=f"o{idx + 73}",
            center=(11280.714, 46.33 + 90 * idx),
            width=0.41,
            orientation=0,
            cross_section=xs,
            port_type="optical",
        )

    mesh_.flatten()
    return mesh_


v7b_cells = get_cells(sys.modules[__name__])

if __name__ == "__main__":
    ipr.get_pdk().activate()

    # spiral = gf.components.spiral(cross_section=gf.get_cross_section("strip"))
    # c2 = add_slot_fill(
    #     spiral,
    #     slot_size=1.0,
    #     pitch=2.0,
    #     margin=1.0,
    #     keepout_layer=(171, 0),
    #     keepout_gap=1.0,
    #     draw_outer=False,
    # )
    # c2.show()

    # rect = gf.c.rectangle((100, 50), LAYER.metal3)
    # filled = add_slot_fill(
    #     rect,
    #     slot_size=2.4,
    #     pitch=4.8,
    #     margin=2.4,
    #     slot_layer=(28, 20),
    #     keepout_gap=1.0,
    #     draw_outer=False,
    # )
    # filled.show()

    @gf.cell
    def slot_rect(size=(60.0, 30.0)):
        c = gf.Component()
        c << gf.components.rectangle(size=size, layer=(28, 0), centered=False)
        return c

    die = gf.Component("die_named")
    (die << slot_rect(size=(60, 30))).move((0, 0))
    (die << slot_rect(size=(50, 30))).move((90, 0))
    r3 = die << slot_rect(size=(40, 20))
    r3.move((0, 60))
    r3.rotate(30)  # rotated container

    # connecting path on the SAME layer -> must NOT be filled
    (die << gf.components.rectangle(size=(30, 4), layer=(28, 0), centered=False)).move(
        (60, 13)
    )

    circle = gf.components.circle(radius=6.0, layer=(18, 0))
    for cx, cy in [(15, 15), (40, 15), (110, 15)]:
        (die << circle).move((cx, cy))

    fill = fill_named_rectangles_fast(
        die,
        name_regex=r"slot_rect.*",
        rect_layer=(28, 0),
        no_fill_layers=((18, 0),),
        slot_size=1.0,
        pitch=2.0,
        margin=1.0,
        keepout_gap=0.5,
    )

    die << fill
    die.show()
