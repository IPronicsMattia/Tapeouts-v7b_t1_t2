from pathlib import Path

import gdsfactory as gf
import iprlayout_tower as ipr  # type: ignore
import numpy as np
from gdsfactory.typings import ComponentSpec, CrossSectionSpec, LayerSpec, Port
from iprlayout_tower.tower_tech import LAYER  # type: ignore
from scipy.integrate import cumulative_trapezoid
from scipy.interpolate import CubicSpline


class json_settings:
    def __init__(self, dict):
        self.data = dict

    def model_dump(self):
        return self.data

    def model_copy(self):
        return self


def take_gds(kind, name):
    path = (
        Path(__file__).resolve().parent.parent / kind / "Additional_gds" / f"{name}.oas"
    )
    c = gf.Component()
    gds_component = gf.import_gds(gdspath=path)
    gds_component.function_name = "take_gds"
    c << gds_component
    for port in gds_component.ports:
        c.add_port(port.name, port=port)
    return c


#############################
#### Visualization blocks ###
#############################
def square_visual(
    square_roundness: float,
    square_size: float,
    square_layer: LayerSpec,
    slot_layer: LayerSpec,
) -> gf.Component:
    """
    Create a series of rounded squares to form a triangle used for visual purposes.

    Args:
        square_roundness (float):
            The roundness of the squares. 1 is circle, 0 is square.
        square_size (float):
            The size of the squares.
        square_layer (LayerSpec):
            The layer on which the squares will be drawn.
        slot_layer (LayerSpec):
            The layer on which the slots will be drawn.
    """
    c = gf.Component()

    # Create the polygon of the square
    n = 2 + (10) * (1 - square_roundness)

    theta = np.linspace(0, 2 * np.pi, 100)

    cos_t = np.cos(theta)
    sin_t = np.sin(theta)

    x = (square_size / 2) * np.sign(cos_t) * np.abs(cos_t) ** (2 / n)
    y = (square_size / 2) * np.sign(sin_t) * np.abs(sin_t) ** (2 / n)
    points = np.column_stack((x, y))

    c.add_polygon(points, layer=square_layer)

    # Find the center of the square
    x_center = np.sum(x) / len(x)
    y_center = np.sum(y) / len(y)

    # Create the slots
    slot_size = 2.4
    row = int((square_size - 4 * slot_size) / (slot_size * 2))
    rec_to_place = gf.c.rectangle(size=(slot_size, slot_size), layer=slot_layer)

    slots = c << gf.components.array(
        component=rec_to_place,
        rows=row,
        columns=row,
        row_pitch=slot_size * 2,
        column_pitch=slot_size * 2,
    )
    slots.x = x_center
    slots.y = y_center

    return c


@gf.cell
def triangle_visual(
    square_roundness: float,
    square_size: float,
    square_distance: float,
    triangle_size: float,
    triangle_layer: LayerSpec,
    slot_layer: LayerSpec,
) -> gf.Component:
    """
    Create a series of rounded squares to form a triangle used for visual purposes.

    Args:
        square_roundness (float):
            The roundness of the squares. 1 is circle, 0 is square.
        square_size (float):
            The size of the squares.
        square_distance (float):
            The distance between the squares.
        triangle_size (float):
            The size of the triangle formed by the squares.
        triangle_layer (LayerSpec):
            The layer on which the triangle will be drawn.
        slot_layer (LayerSpec):
            The layer on which the slots will be drawn.
    """

    # Checks
    assert square_roundness >= 0 and square_roundness <= 1, (
        "square_roundness must be between 0 and 1"
    )
    assert triangle_size > square_size, "triangle_size must be greater than square_size"

    # Create the component
    c = gf.Component()

    square = square_visual(
        square_roundness=square_roundness,
        square_size=square_size,
        square_layer=triangle_layer,
        slot_layer=slot_layer,
    )

    # Create a sequence of square to form the triangle
    n_squares = int(triangle_size / (square_size + square_distance)) + 1
    for edge in range(1, n_squares + 1):
        if edge == n_squares:
            range_x = edge - 2
        else:
            range_x = edge - 1
        for idx in range(range_x):
            square_ref = c << square
            square_ref.x = edge * (square_size + square_distance)
            square_ref.y = idx * (square_size + square_distance)

    c.flatten()

    return c


@gf.cell
def bump(layer, width, height):
    """
    Create a small rounded elliptical bump on the given layer.
    """

    # Create a component
    c = gf.Component()

    # Left fillet: vertical wall -> flat top
    radius = height
    n_pts = 10
    center_l = (-width / 2 + radius, height - radius)
    theta_l = np.linspace(np.pi, np.pi / 2, n_pts)
    arc_l = [
        (center_l[0] + radius * np.cos(t), center_l[1] + radius * np.sin(t))
        for t in theta_l
    ]

    # Right fillet: flat top -> vertical wall
    center_r = (width / 2 - radius, height - radius)
    theta_r = np.linspace(np.pi / 2, 0, n_pts)
    arc_r = [
        (center_r[0] + radius * np.cos(t), center_r[1] + radius * np.sin(t))
        for t in theta_r
    ]

    points = [(-width / 2, 0)] + arc_l + arc_r + [(width / 2, 0)]

    c.add_polygon(points, layer=layer)

    # Add ports
    c.add_port(
        name="o1",
        center=(0, 0),
        width=width,
        orientation=270,
        layer=layer,
    )
    return c


##############################
### Phase shifter and PUCS ###
##############################


@gf.cell
def v7a_PUC_from_gds(name) -> gf.Component:
    path = (
        Path(__file__).resolve().parent.parent
        / "ComplementaryFile"
        / "PUCs"
        / f"{name}.gds"
    )
    return gf.import_gds(gdspath=path, cellname=f"TOP_{name}")


@gf.cell
def puc_with_diode(puc, diode, **kwargs):
    """
    Create a PUC where the left part is connected to a diode.
    """

    # Cross section needed
    xs_metal1 = gf.get_cross_section("metal1", width=11)
    xs_metal2 = gf.get_cross_section("metal2", width=11)
    xs_metal3 = gf.get_cross_section("metal3", width=11)

    # Place the component
    c = gf.Component()

    # Place the puc
    puc_ref = c << puc
    puc_ref.rotate(90)

    via_htr_2 = via_to_metal2(
        size=(xs_metal2.width, xs_metal2.width), pitch_via=0.28, bottom_layer=LAYER.tnr
    )
    via_1_2 = via_to_metal2(
        size=(xs_metal2.width, xs_metal2.width),
        pitch_via=0.28,
        bottom_layer=LAYER.metal1,
    )
    via_2_3 = via_metal2_metal3(size=(xs_metal2.width, xs_metal2.width), pitch_via=0.54)

    # Add diode to the puc
    vias = []
    for idx in range(2):
        # Decide the port
        puc_port = puc_ref[f"e{1 + idx}"]

        via_ref = c << via_htr_2
        via_ref.connect("e1", puc_port, allow_layer_mismatch=True)

        # Rotate the port in correct position
        puc_rout_dist = (diode["N"].width - xs_metal1.width) / np.sqrt(2)

        strt = c << straight_with_slots(length=puc_rout_dist, cross_section=xs_metal2)
        strt.connect("e1", via_ref["e3"])

        # Create a via from metal 2 to metal 1
        via_ref = c << via_1_2
        via_ref.connect("e1", strt["e2"])

        # Create a taper metal 1 to diode
        tp = gf.c.taper(
            length=puc_rout_dist,
            width1=via_ref["e3"].width,
            width2=diode["N"].width,
            layer=LAYER.metal1,
            port_names=("e1", "e2"),
            port_types=("electrical", "electrical"),
        )
        tp_ref = c << tp
        tp_ref.connect("e1", via_ref["e3"], allow_layer_mismatch=True)

        # Position the diode
        diode_ref = c << diode
        diode_ref.connect("N", tp_ref["e2"])

        # Create a taper diode to metal 1
        tp_ref = c << tp
        tp_ref.connect("e2", diode_ref["P"])

        # Create a via from metal 1 to metal 2
        via_ref = c << via_1_2
        via_ref.connect("e1", tp_ref["e1"], allow_layer_mismatch=True)

        via_ref2 = c << via_2_3
        via_ref2.center = via_ref.center

        # Add the port
        c.add_port(f"e{1 + idx}", port=via_ref2["e1"])
        vias.append(via_ref2)

        # Create a via also in the other part
        puc_port = puc_ref[f"e{3 + idx}"]

        via_ref = c << via_htr_2
        via_ref.connect("e1", puc_port, allow_layer_mismatch=True)

        if idx == 0:
            via_ref2 = c << via_2_3
            via_ref2.center = via_ref.center
            c.add_port(f"e{3 + idx}", port=via_ref2["e3"])
        else:
            c.add_port(f"e{3 + idx}", port=via_ref["e3"])

    # Create a straight between the final via
    dy = vias[1]["e4"].y - vias[0]["e2"].y
    strt = c << straight_with_slots(length=dy, cross_section=xs_metal3)
    strt.connect("e1", vias[1]["e4"], allow_layer_mismatch=True)

    # Add the port
    port_idx = 0
    for port in puc_ref.ports:
        if port.name in ["o1", "o2", "o3", "o4"]:
            port_name = ["o1", "o2", "o3", "o4"][port_idx]
            port_idx += 1
            c.add_port(port_name, port=port)

    return c


_puc_array_number = 0


def puc_array_test_structure(
    kind: str,
    gc_array: ComponentSpec,
    pucs: list[ComponentSpec],
    pad_ports: list[Port],
    routing_straight: ComponentSpec,
    routing_bend: ComponentSpec,
) -> gf.Component:
    """
    Create a test structure for testing optically a PUC DoE.

    Args:
        kind (string):
            Decide how the pucs are placed.
        gc_array (ComponentSpec):
            The component to be used as grating coupler array.
        pucs (list[ComponentSpec]):
            The list of PUCs to place in the structure.
        pad_ports (list[Port]):
            The list of ports to which the PUCs will be connected.
            The first 4 are for the signal and the last for ground.
        routing_straight (ComponentSpec):
            The component to be used for the straight routing between the PUCs and gc.
        routing_bend (ComponentSpec):
            The component to be used for the bend routing between the PUCs and gc
    """

    # Variable from LAB
    gc_array_dist = 650  # 50 half pad size + 600 minimum distance
    pitch = 127
    structure_height = 900

    # Create the component
    global _puc_array_number
    c = gf.Component(name="puc_array_test_structure_" + str(_puc_array_number))
    _puc_array_number += 1

    # Calculate the maximum height of the pads
    min_height = min(port.y for port in pad_ports)

    # Place the gratings
    gc_array_bot = c << gc_array
    gc_array_bot.rotate(-90)
    gc_array_bot.xmax = pad_ports[0].x - gc_array_dist
    gc_array_bot.ymin = min_height

    if kind == "Left":
        gc_array_bot.xmax -= pitch * 9

    gc_array_top = c << gc_array
    gc_array_top.rotate(90)
    gc_array_top.ymax = min_height + structure_height
    gc_array_top.x = gc_array_bot.x - pitch / 2

    # Place the PUCs
    pucs_top_ports = []
    pucs_bot_ports = []
    pucs_elc_ports = []
    n_pucs = len(pucs)
    idx_puc = 1 if kind == "Right" else 0
    for idx, puc in enumerate(reversed(pucs)):
        puc_ref = c << puc

        puc_ref.x = (
            gc_array_top[f"o{2 * idx + idx_puc}"].x
            + gc_array_top[f"o{2 * idx + 1 + idx_puc}"].x
        ) / 2 + pitch / 4
        puc_ref.y = (
            gc_array_top[f"o{2 * idx + idx_puc}"].y * 0.4
            + gc_array_bot[f"o{2 * idx + 1 + idx_puc}"].y * 0.6
        )

        # Append new port
        pucs_bot_ports.append(puc_ref["o2"])
        pucs_bot_ports.append(puc_ref["o1"])
        pucs_top_ports.append(puc_ref["o4"])
        pucs_top_ports.append(puc_ref["o3"])
        pucs_elc_ports.append(puc_ref["e2"])
        pucs_elc_ports.append(puc_ref["e3"])

    lr = routing_straight(length=0)
    xs = gf.get_cross_section(lr["o1"].cross_section)
    xs_new = gf.cross_section.cross_section(
        sections=xs.sections,
        layer=gf.get_layer_name(xs.layer),
        width=xs.width,
        port_names=("o1", "o2"),
    )
    if kind == "Right":
        gc_in_ports = [
            gc_array_top[f"o{idx + 1}"] for idx in range(len(gc_array_top.ports) - 1)
        ]
        gc_out_ports = [
            gc_array_bot[f"o{idx}"] for idx in range(len(gc_array_bot.ports) - 1)
        ]
    else:
        gc_in_ports = [
            gc_array_top[f"o{idx}"] for idx in range(len(gc_array_top.ports))
        ]
        gc_out_ports = [
            gc_array_bot[f"o{idx}"] for idx in range(len(gc_array_bot.ports))
        ]
    gc_out_ports = reversed(gc_out_ports)

    # Route all the input and output
    gf.routing.route_bundle(
        auto_taper=False,
        bend=routing_bend,
        component=c,
        cross_section=xs_new,
        ports1=pucs_top_ports,
        ports2=gc_in_ports,
        straight=routing_straight,
        start_straight_length=20,
    )

    gf.routing.route_bundle(
        auto_taper=False,
        bend=routing_bend,
        component=c,
        cross_section=xs_new,
        ports1=pucs_bot_ports,
        ports2=gc_out_ports,
        straight=routing_straight,
        start_straight_length=20,
    )

    p_up = gc_array_top["o0"]
    p_down = gc_array_bot[f"o{len(gc_array_top.ports) - 1}"]

    if kind == "Right":
        p_dist = p_up.y * 0.5 - p_down.y * 0.5
        gf.routing.route_single(
            auto_taper=False,
            bend=routing_bend,
            component=c,
            cross_section=xs_new,
            port1=p_up,
            port2=p_down,
            straight=routing_straight,
            start_straight_length=p_dist,
        )

    # Electrical routing
    m3_width = 11
    m3g_width = 33
    m3_xs = gf.get_cross_section("metal_routing", width=m3_width)
    m3g_xs = gf.get_cross_section("metal_routing", width=m3g_width)

    for idx in range(n_pucs):
        # For the signal
        metal_spacing = 25
        if kind == "Right":
            # In the top part we need to start from a different port
            pad_port = pad_ports[4 + idx]

            dy0 = 0
            x = pucs_elc_ports[-1].x + 185 + metal_spacing * (n_pucs + 1 - idx)
        else:
            # Than in the bot part
            pad_port = pad_ports[idx]

            # While for the bot part we need to leave some initial space
            dy0 = metal_spacing * 5 + 20
            x = pucs_elc_ports[-1].x + 200 + metal_spacing * (idx + 3) + pitch * 9

        gf.routing.route_single(
            auto_taper=False,
            bend="wire_corner45",
            allow_width_mismatch=True,
            component=c,
            cross_section=m3_xs,
            port1=pucs_elc_ports[2 * idx],
            port2=pad_port,
            radius=m3_xs.width / 2,
            straight=ipr.straight,
            steps=[
                {"y": pucs_elc_ports[0].y + (n_pucs + 1 - idx) * metal_spacing + dy0},
                {"x": x},
                {"y": pad_port.y + 62.5},
                {"x": pad_port.x},
            ],
        )

        port_puc_bot = pucs_elc_ports[2 * idx + 1]
        length = abs(port_puc_bot.y - pad_ports[-1].y) + 115
        m3_strt = c << gf.components.straight(length=length, cross_section=m3_xs)
        m3_strt.connect("e1", port_puc_bot, allow_width_mismatch=True)

    # Common ground
    m3_ground_length = pad_ports[-1].x - pucs_elc_ports[1].x - 244.5
    if kind == "Left":
        m3_ground = c << straight_with_slots(
            length=m3_ground_length, cross_section=m3g_xs
        )
    else:
        m3_ground = c << ipr.straight(length=m3_ground_length, cross_section=m3g_xs)
    m3_ground.ymin = m3_strt.ymin - 26.5
    m3_ground.xmax = pad_ports[-1].x - 250

    m3_ground_length = 100
    if kind == "Left":
        m3_ground = c << straight_with_slots(
            length=m3_ground_length, cross_section=m3g_xs
        )
    else:
        m3_ground = c << ipr.straight(length=m3_ground_length, cross_section=m3g_xs)
    m3_ground.ymin = m3_strt.ymin - 26.5
    m3_ground.xmin = pad_ports[-1].x - 150

    return c


@gf.cell
def via_to_metal2(
    bottom_layer,
    size=(10, 10),
    pitch_via: float = 0.54,
    enclosure_via: float = 0.46,
) -> gf.Component:
    """
    Returns a rectangular via between bottom layer and metal2.
    """

    via1 = gf.partial(
        gf.c.via,
        layer=LAYER.via1,
        size=(0.2, 0.2),
        pitch=pitch_via + 0.2,
        enclosure=enclosure_via,
    )

    via_mt1_mt2 = gf.get_component(
        gf.partial(
            gf.c.via_stack,
            layers=(bottom_layer, LAYER.metal2),
            vias=(via1, None),
            size=size,
        )
    )

    return via_mt1_mt2


@gf.cell
def via_metal2_metal3(
    size=(10, 10),
    pitch_via: float = 0.54,
    enclosure_via: float = 0.46,
) -> gf.Component:
    """
    Returns a rectangular via between metal2 and metal3.
    """

    via2 = gf.partial(
        gf.c.via,
        layer=LAYER.via2,
        size=(0.36, 0.36),
        pitch=pitch_via + 0.36,
        enclosure=enclosure_via,
    )

    via_mt2_mt3 = gf.get_component(
        gf.partial(
            gf.c.via_stack,
            layers=(LAYER.metal2, LAYER.metal3),
            vias=(via2, None),
            size=size,
        )
    )

    return via_mt2_mt3


@gf.cell
def via_23_with_metal_taper(via_width, metal3_width):
    # Create the component
    c = gf.Component("via_with_taper")

    # Add the via
    via23 = c << via_metal2_metal3(size=(via_width, via_width), pitch_via=0.54)

    # Add the taper
    length = (via_width - metal3_width) / np.sqrt(2)
    metal_taper = c << gf.c.taper(
        width1=via_width,
        width2=metal3_width,
        length=length,
        layer=LAYER.metal3,
        port_names=["e1", "e2"],
        port_types=["electrical", "electrical"],
    )
    metal_taper.connect("e1", via23["e4"])

    # Add the ports
    for idx in range(4):
        if idx != 3:
            c.add_port(f"e{idx + 1}", port=via23[f"e{idx + 1}"])
        else:
            c.add_port(f"e{idx + 1}", port=metal_taper["e2"])

    return c


#################
### Straights ###
#################
change_port_cache = {}


def change_port(component, ports_i, ports_o, flatten=True):
    """
    Take a component and change the input ports with the output ports.
    """
    # Place component
    c = gf.Component()
    comp_ref = c << component

    # Add name
    c.name = component.name + "_pinv"
    c.function_name = component.function_name
    c.settings = component.settings

    # Invert port
    for port in component.ports:
        if port.name in ports_i:
            port_o = ports_o[ports_i.index(port.name)]
            c.add_port(port_o, port=comp_ref.ports[port.name])

            # Update name to avoid duplicate
            c.name += port.name + port_o

    # Add info
    c.info = comp_ref.cell.info

    # Flatten
    if flatten:
        c.flatten()

    # Manage cache
    if c.name in change_port_cache:
        return change_port_cache[c.name]
    else:
        change_port_cache[c.name] = c

    return c


def straight_410_swg(length: float, **kwargs):  # Level 0
    kwargs["cross_section"] = gf.get_cross_section("strip", layer=LAYER.swg, width=0.41)
    return gf.partial(ipr.fast_straight, length=length, **kwargs)()


def straight_930_swg(length: float, **kwargs):  # Level 0
    kwargs["cross_section"] = gf.get_cross_section("strip", layer=LAYER.swg, width=0.93)
    return gf.partial(ipr.fast_straight, length=length, **kwargs)()


def straight_700_anwg(length: float, **kwargs):  # Level 0
    kwargs["cross_section"] = gf.get_cross_section("nitride2", width=0.70)
    return gf.partial(ipr.fast_straight, length=length, **kwargs)()


def straight_2000_anwg(length: float, **kwargs):  # Level 0
    kwargs["cross_section"] = gf.get_cross_section("nitride2", width=2.00)
    return gf.partial(ipr.fast_straight, length=length, **kwargs)()


@gf.cell
def straight_with_slots(length: float, cross_section: CrossSectionSpec) -> gf.Component:
    c = gf.Component()
    width = gf.get_cross_section(cross_section).width
    layer = gf.get_cross_section(cross_section).layer
    if gf.get_layer_name(layer) == "metal3":
        layer_slit = LAYER.metal3_slot
        rec = c << gf.c.rectangle_with_slits(
            size=(length, width),
            layer=layer,
            port_type="electrical",
            slit_column_pitch=4.8,
            slit_row_pitch=4.8,
            slit_enclosure=2.4,
            slit_size=(2.4, 2.4),
            layer_slit=layer_slit,
        )
    elif gf.get_layer_name(layer) == "metal2":
        layer_slit = LAYER.metal2_slot
        rec = c << gf.c.rectangle_with_slits(
            size=(length, width),
            layer=layer,
            port_type="electrical",
            slit_column_pitch=5.0,
            slit_row_pitch=5.0,
            slit_enclosure=2.5,
            slit_size=(2.5, 2.5),
            layer_slit=layer_slit,
        )
    else:
        layer_slit = LAYER.metal1_slot
        rec = c << gf.c.rectangle_with_slits(
            size=(length, width),
            layer=layer,
            port_type="electrical",
            slit_column_pitch=4.8,
            slit_row_pitch=4.8,
            slit_enclosure=2.4,
            slit_size=(2.4, 2.4),
            layer_slit=layer_slit,
        )

    c.add_port(
        name="e1",
        center=(rec.xmin, rec.ymin + width / 2),
        orientation=180,
        port_type="electrical",
        width=width,
        layer=layer,
    )
    c.add_port(
        name="e2",
        center=(rec.xmax, rec.ymin + width / 2),
        orientation=0,
        port_type="electrical",
        width=width,
        layer=layer,
    )

    return c


def from_clothoid_to_straights(component: ComponentSpec) -> gf.Component:
    """
    Create a n_bb_straights of clothoid
    """
    xs = gf.get_cross_section("strip", width=component["o2"].width)
    # Create two clothoid connected
    clothoid_kwargs = {"bbmul": component, "bbadd": component, "bbmul_list": ["o1"]}
    bb2_clothoid = ipr.bb_mul_bb(length=0, **clothoid_kwargs)

    tp_length = 5
    bb_distance = 11
    if abs(component["o2"].width - 0.41) > 2e-3:
        taper = ipr.rib_taper(
            width_RIB_in=0.41, width_RIB_out=component["o2"].width, length=tp_length
        )
    else:
        taper = straight_410_swg(length=tp_length)

    # Create a series of n clothoid
    clothoid_n_kwargs = {
        "straight": ipr.nbb_straight,
        "bb1": taper,
        "bb2": taper,
        "bb2_rev": True,
        "1_straight": gf.partial(ipr.fast_straight, cross_section=xs),
        "1_straight_limited": gf.partial(ipr.fast_straight, cross_section=xs),
        "1_bb": bb2_clothoid,
        "1_sep_distance": bb_distance,
        "1_sep_variation": 0.141,
        # For calculation
        "2_bb": bb2_clothoid,
        "2_io_length": tp_length,
        "2_bb_extra_length": bb_distance,
        "2_sep_distance": bb_distance,
    }

    return gf.partial(
        ipr.bb_straight_bb_limited, **clothoid_n_kwargs
    ), clothoid_n_kwargs


def tps_410_swg_930_swg_lim(length: float, **kwargs):  # Level 1
    rb_taper = kwargs["bb1"]

    # Add a IO of 1 um
    kwargs["straight"] = straight_410_swg
    kwargs["bb1"] = None
    kwargs["bb2"] = rb_taper
    rb_taper_in = ipr.bb_straight_bb(length=1.0, **kwargs)

    # Add the correct kwargs
    kwargs["straight"] = straight_930_swg
    kwargs["straight_limited"] = straight_410_swg
    kwargs["bb1"] = rb_taper_in
    kwargs["bb2"] = rb_taper_in
    kwargs["bb2_rev"] = "True"
    return gf.partial(ipr.bb_straight_bb_limited, length, **kwargs)()


######################
### Building Block ###
######################


@gf.cell
def clothoid(
    variant: str = "bloss",  # "na" | "bloss" | "partial_euler"
    H: float = 4.0,  # maximum height (um)
    angle: float = 105.0,  # angles of the first bend (degrees)
    na_n: float = None,  # exponent for "na"  (n=1 is Euler)
    pe_p: float = None,  # ramp fraction for "partial_euler" (0-1)
    bloss_rho: float = None,  # rho for "bloss"
    g: float = None,  # gap between both wgs (um)
    wg_a: float = None,  # width of wg A (um)
    wg_b: float = None,  # width of wg B (um)
    Lt: float = None,  # taper length A<->B (um)
    w_center: float = None,  # maximum width of the first bend
    m: float = None,  # width varying rate (1 = lineal)
    length_access: float = 0,
    cross_section: CrossSectionSpec = "strip",
    npoints: int = 200,
    **kwargs,
) -> gf.Component:
    """U-turn structure built with six segments (2 bends + 2 tranposed + taper + straight) generalized
    to any type of bend by the curvature profile kappa(s).

    variant:
        "partial_euler" -> lineal ramp + central arch     (fraction pe_p)
        "na"            -> kappa proportional to s**na_n   (na_n=1 => Exact Euler)
        "bloss"         -> 3t^2-2t^3 ramps + central arch (bloss_rho parameter)
    """

    # --------------------------------------------------------------- #
    # Angles required
    # --------------------------------------------------------------- #
    theta_a = np.radians(angle)
    delta_a = 2 * theta_a - 3 * np.pi / 2
    cos_da, sin_da = np.cos(delta_a), np.sin(delta_a)

    theta_b = theta_a - np.pi / 2
    delta_b = 2 * theta_b + np.pi / 2
    cos_db, sin_db = np.cos(delta_b), np.sin(delta_b)

    g = g + (wg_a + wg_b) / 2  # Correcting the gap
    xs = gf.get_cross_section(cross_section, **kwargs)

    # =============================================================== #
    # Curvature profile kappa(s): defines the shape of each variant.
    # Its re-normalized so that the turn is exactly 'angle'.
    # =============================================================== #
    def _kappa_profile(variant, r_min, npoints, angle):
        if variant == "na":
            n = max(float(na_n), 0.0)
            L_t = (n + 1) * angle * r_min
            s = np.linspace(0.0, L_t, npoints)
            kappa = (s**n) / r_min
            theta_raw = cumulative_trapezoid(kappa, s, initial=0.0)
            kappa = kappa * angle / theta_raw[-1]
            return s, kappa
        if variant == "bloss":
            rho = max(float(bloss_rho), 0.0)
            u_hat = rho * angle / (2.0 * (2.0 + rho))
            L_ramp = 2.0 * u_hat * r_min
            L_arc = (angle - 2.0 * u_hat) * r_min

            def ramp(t):
                return 3.0 * t**2 - 2.0 * t**3
        else:  # partial_euler
            p = float(np.clip(pe_p, 0.0, 1.0))
            L_ramp = p * angle * r_min
            L_arc = (1.0 - p) * angle * r_min

            def ramp(t):
                return t

        L_t = L_ramp + L_arc
        s = np.linspace(0.0, L_t, npoints)
        kappa = np.full(npoints, 1.0 / r_min)
        if L_ramp > 0:
            up = s <= L_ramp
            dn = s > L_ramp + L_arc
            kappa[up] = ramp(s[up] / L_ramp) / r_min
            kappa[dn] = ramp(np.maximum(L_t - s[dn], 0.0) / L_ramp) / r_min
            theta_raw = cumulative_trapezoid(kappa, s, initial=0.0)
            kappa = kappa * angle / theta_raw[-1]
        return s, kappa

    def _curve(angle_turn, npoints):
        """Unity bend (r_min=1) for the variation: returbs s, theta(s), x(s) and y(s).
        Integrates in arch length.
        """
        s, kappa = _kappa_profile(variant, 1.0, npoints, angle_turn)
        theta = cumulative_trapezoid(kappa, s, initial=0.0)
        x = cumulative_trapezoid(np.cos(theta), s, initial=0.0)
        y = cumulative_trapezoid(np.sin(theta), s, initial=0.0)
        return s, theta, x, y

    ND = 4001  # dense mesh for good precision
    # --- bend 1 (turns theta_a) ---
    _, thu1, Xu1, Yu1 = _curve(theta_a, ND)

    def _pt1(alpha):  # point of bend 1 where the tangent is equal to alpha
        return np.interp(alpha, thu1, Xu1), np.interp(alpha, thu1, Yu1)

    X1a, Y1a = Xu1[-1], Yu1[-1]  # end (tangent = theta_a)
    X1p, Y1p = _pt1(2 * theta_a - np.pi)
    A = H / (((X1p - X1a) * cos_da + (Y1p - Y1a) * sin_da) + Y1a)

    h2 = A * (-X1a * cos_da + Y1a * (1 - sin_da)) - g + Lt * np.sin(2 * theta_a)

    # --- bend 2 (turns theta_b): ---
    _, _, Xu2, Yu2 = _curve(theta_b, ND)
    X3, Y3 = Xu2[-1], Yu2[-1]  # end (tangent = theta_b)
    A2 = h2 / ((-X3 * cos_db) + (Y3 * (1 - sin_db)))

    # =============================================================== #
    #  Segment 1 (first bend)
    # =============================================================== #
    s1, theta1, Xd1, Yd1 = _curve(theta_a, npoints)
    x1 = A * Xd1
    y1 = A * Yd1

    # Variable width
    var = np.linspace(0, 1, npoints)
    w = w_center + (wg_a - w_center) * var**m
    w = w[::-1]

    sin_a, cos_a = np.sin(theta1), np.cos(theta1)
    inner1 = np.column_stack((x1 - w / 2 * sin_a, y1 + w / 2 * cos_a))
    outer1 = np.column_stack((x1 + w / 2 * sin_a, y1 - w / 2 * cos_a))

    # =============================================================== #
    #  Segment 2 (bend 1 transposed)
    # =============================================================== #
    x2 = -x1 * sin_da + y1 * cos_da + x1[-1] * (1 + sin_da) - y1[-1] * cos_da
    y2 = x1 * cos_da + y1 * sin_da - x1[-1] * cos_da + y1[-1] * (1 - sin_da)

    theta2 = 2 * theta_a - theta1  # (+ np.pi if the normal is inverted)
    sin_a, cos_a = np.sin(theta2), np.cos(theta2)
    inner2 = np.column_stack((x2 - w / 2 * sin_a, y2 + w / 2 * cos_a))
    outer2 = np.column_stack((x2 + w / 2 * sin_a, y2 - w / 2 * cos_a))

    # =============================================================== #
    #  Segment 3 (second bend)
    # =============================================================== #
    s2, theta3, Xd2, Yd2 = _curve(theta_b, npoints)
    x3_p = A2 * Xd2
    y3_p = A2 * Yd2

    # =============================================================== #
    #  Segmento 4 (bend 2 transposed)
    # =============================================================== #
    x4_p = -x3_p * sin_db + y3_p * cos_db + x3_p[-1] * (1 + sin_db) - y3_p[-1] * cos_db
    y4_p = x3_p * cos_db + y3_p * sin_db - x3_p[-1] * cos_db + y3_p[-1] * (1 - sin_db)

    # Offset to connect with segment 2 and the taper
    Obx = -x4_p[0] + x2[0] - Lt * np.cos(2 * theta_b)

    # Segment 3 with offset (wg B and pitch g)
    x3 = x3_p + Obx
    y3 = y3_p + g
    sin_b, cos_b = np.sin(theta3), np.cos(theta3)
    inner3 = np.column_stack((x3 - wg_b / 2 * sin_b, y3 + wg_b / 2 * cos_b))
    outer3 = np.column_stack((x3 + wg_b / 2 * sin_b, y3 - wg_b / 2 * cos_b))

    # Segmento 4 with offset
    x4 = x4_p + Obx
    y4 = y4_p + g
    theta4 = 2 * theta_b - theta3
    sin_b, cos_b = np.sin(theta4), np.cos(theta4)
    inner4 = np.column_stack((x4 - wg_b / 2 * sin_b, y4 + wg_b / 2 * cos_b))
    outer4 = np.column_stack((x4 + wg_b / 2 * sin_b, y4 - wg_b / 2 * cos_b))

    # =============================================================== #
    #  Segmento 5 (taper wg_b -> wg_a)
    # =============================================================== #
    var = np.linspace(0, Lt, npoints)
    x5 = x4[0] + var * np.cos(theta_b * 2)
    y5 = y4[0] + var * np.sin(theta_b * 2)
    t = var / Lt
    x_we_offset = ((wg_b + (wg_a - wg_b) * t) / 2) * np.sin(theta_b * 2)
    y_we_offset = -((wg_b + (wg_a - wg_b) * t) / 2) * np.cos(theta_b * 2)
    inner5 = np.column_stack((x5 - x_we_offset, y5 - y_we_offset))
    outer5 = np.column_stack((x5 + x_we_offset, y5 + y_we_offset))

    # =============================================================== #
    #  Segmento 6 (access wg, wg A)
    # =============================================================== #
    x6 = np.linspace(Obx, 0, npoints)
    y6 = np.zeros(len(x6))
    inner6 = np.column_stack((x6, y6 + wg_a / 2))
    outer6 = np.column_stack((x6, y6 - wg_a / 2))

    # =============================================================== #
    #  Building the polygon
    # =============================================================== #
    inner = np.vstack(
        [inner6, inner1, inner2[::-1], inner5[::-1], inner4, inner3[::-1]]
    )
    outer = np.vstack(
        [outer6, outer1, outer2[::-1], outer5[::-1], outer4, outer3[::-1]]
    )

    # Add a straight if necessary
    if length_access != 0:
        inner = np.vstack(
            [
                [Obx - length_access, inner[0, 1]],
                inner,
                [Obx - length_access, inner[-1, 1]],
            ]
        )
        outer = np.vstack(
            [
                [Obx - length_access, outer[0, 1]],
                outer,
                [Obx - length_access, outer[-1, 1]],
            ]
        )

    polygon = np.vstack([outer, inner[::-1]])

    def _snap(v: float) -> float:
        i = round(v * 1000)
        return (i + 1 if i % 2 else i) / 1000.0

    c = gf.Component()
    c.add_polygon(polygon, layer=xs.layer)
    if length_access != 0:
        c.add_port(
            name="o1",
            center=(0.0, 0.0),
            width=_snap(wg_a),
            orientation=180,
            layer=xs.layer,
        )
        c.add_port(
            name="o2",
            center=(Obx, g),
            width=_snap(wg_b),
            orientation=180,
            layer=xs.layer,
        )
    else:
        c.add_port(
            name="o1",
            center=(Obx, 0.0),
            width=_snap(wg_a),
            orientation=180,
            layer=xs.layer,
        )
        c.add_port(
            name="o2",
            center=(inner[-1, 0], g),
            width=_snap(wg_b),
            orientation=180,
            layer=xs.layer,
        )
    # arc length of the UNIT curves (s already goes 0 .. L)
    su1 = s1[-1]  # from  s1, theta1, Xd1, Yd1 = _curve(theta_a, npoints)
    su2 = s2[-1]  # from  s2, theta3, Xd2, Yd2 = _curve(theta_b, npoints)

    total_length = (
        2 * (A * su1 + A2 * su2) + Lt - Obx
    )  # Twice the bends with transposed + taper + straight
    c.info["length"] = round(float(total_length.squeeze()), 3)
    c.flatten()
    return c


@gf.cell
def diode_linear(
    length_contact: float = 5,
    length_dop1: float = 0.5,
    length_dop1_overlap: float = 0.0,
    length_dop2: float = 1.00,
    length_dop2_overlap: float = 0.0,
    margin_swg: float = 0.18,
    margin_silicide: float = 0.50,
    margin_silicide_doped: float = 0.15,
    width_contact: float = 20,
):
    """
    Create a diode as a sequence of layers from maximum P doping to maximum N doping,
    changing gradually the doping.
    P+ can overlap with PI by length_dop1_overlap. Same for N+ with NI.
    P can overlap with P+ by length_dop_2_overlap. Same for N with N+.

    Args:
        length_contact: length of P++ and N++ layers.
            Defaults to 5.
        length_dop1: length of P+ and N+ layers.
            Defaults to 0.5.
        length_dop1_overlap: overlap amount between P+ and PI (same for N+ and NI)
            Defaults to 0.0.
        length_dop2: length of P and N layers.
            Defaults to 1.25
        length_dop2_overlap: overlap amount between P and P+ (same for N and N+)
            Defaults to 0.0.
        margin_swg: distance between swg and doped region. Positive means
            inside (extended).
            Defaults to 0.18.
        margin_silicide: distance between swg and silicide region. Positive means
            outside (contained).
            Defaults to 0.50.
        margin_silicide_doped: distance between silicide and P+ (N+) considered when
            swg-silicide distance is satisfied.
            Defaults to 0.15
        width_contact: width of all the layers.
            Defaults to 20.

    """
    # Calculate parameters for the swg
    width_swg = width_contact + margin_swg * 2
    length_swg = (
        length_contact
        + length_dop1
        - length_dop1_overlap
        + length_dop2
        - length_dop2_overlap
        + margin_swg
    ) * 2
    overlap_swg = length_swg - margin_swg

    # Increase 100 nm for the bumping of the swg edges
    bump_margin = 0.1
    margin_silicide += bump_margin

    # Calculate parameters for the silicide
    width_silicide = width_swg - margin_silicide * 2
    length_silicide = (
        length_contact
        - margin_silicide
        - margin_silicide_doped
        + margin_swg
        + bump_margin
    )
    width_metal = width_silicide
    length_metal = length_silicide

    # Create the rectangle
    rectangles = []
    if length_contact > 0:
        rectangles.append(
            {
                "width": width_contact,
                "length": length_contact,
                "layer": LAYER.cpi,
                "overlap": 0,
                "closing": False,
            }
        )  # P++ Implant

    if length_dop1 > 0:
        rectangles.append(
            {
                "width": width_contact,
                "length": length_dop1,
                "layer": LAYER.modano2,
                "overlap": length_dop1_overlap,
                "closing": False,
            }
        )  # P+ Doped

    if length_dop2 > 0:
        rectangles.append(
            {
                "width": width_contact,
                "length": length_dop2,
                "layer": LAYER.modano,
                "overlap": length_dop2_overlap,
                "closing": False,
            }
        )  # P Doped

    if length_dop2 > 0:
        rectangles.append(
            {
                "width": width_contact,
                "length": length_dop2,
                "layer": LAYER.modca,
                "overlap": 0,
                "closing": False,
            }
        )  # N Doped

    if length_dop1 > 0:
        rectangles.append(
            {
                "width": width_contact,
                "length": length_dop1,
                "layer": LAYER.modca2,
                "overlap": length_dop2_overlap,
                "closing": False,
            }
        )  # N+ Doped

    if length_contact > 0:
        overlap = length_dop1_overlap if length_dop1 > 0 else length_dop2_overlap
        rectangles.append(
            {
                "width": width_contact,
                "length": length_contact,
                "layer": LAYER.cni,
                "overlap": overlap,
                "closing": False,
            }
        )  # N++ Implant

    if length_swg > 0:
        rectangles.append(
            {
                "width": width_swg,
                "length": length_swg,
                "layer": LAYER.swg,
                "overlap": overlap_swg,
                "closing": True,
            }
        )  # swg Waveguide

    # Component where to insert the diode
    c = gf.Component()

    # Add rectangle chain of doping
    rc = c << rectangles_chain(rectangles=rectangles)

    # Add silicide
    rectangles = [
        {"width": width_silicide, "length": length_silicide, "layer": LAYER.sblk}
    ]
    silicide_i = c << rectangles_chain(rectangles=rectangles)
    silicide_o = c << rectangles_chain(rectangles=rectangles)
    silicide_i.xmin = rc.xmin + margin_silicide
    silicide_o.xmax = rc.xmax - margin_silicide

    # We need to guarantee 2.5 um distance between metal to be DRC compatible
    rule_distance = silicide_o.xmin - silicide_i.xmax
    safe_rule_distance = 2.6
    remove_distance = max(safe_rule_distance - rule_distance, 0) / 2
    length_metal -= remove_distance

    # Add metal
    rectangles = [{"width": width_metal, "length": length_metal, "layer": LAYER.metal1}]

    for idx in range(2):
        metal = c << rectangles_chain(rectangles=rectangles)
        if idx == 0:
            metal.xmin = rc.xmin + margin_silicide
        else:
            metal.xmax = rc.xmax - margin_silicide

        # General contact information
        square_size = 0.48
        square_to_square_distance = 0.72
        square_to_edge_distance = 0.2

        # x direction
        width = metal.xmax - metal.xmin
        n = np.floor(
            (width + square_to_square_distance - 2 * square_to_edge_distance)
            / (square_size + square_to_square_distance)
        )
        dx = width - n * square_size - (n - 1) * square_to_square_distance

        if idx == 0:
            dx1 = square_to_edge_distance
            dx2 = dx - square_to_edge_distance
        else:
            dx1 = dx - square_to_edge_distance
            dx2 = square_to_edge_distance

        # y direction
        height = metal.ymax - metal.ymin
        n = np.floor(
            (height + square_to_square_distance - 2 * square_to_edge_distance)
            / (square_size + square_to_square_distance)
        )
        dy = (height - n * square_size - (n - 1) * square_to_square_distance) / 2

        # Add contact
        c << square_filling(
            filling_structure=metal,
            layer=LAYER.contact,
            square_size=square_size,
            square_to_edge_distances=[dx1, dx2, dy, dy],
            square_to_square_distance=square_to_square_distance,
        )

    # Add electrical ports
    c.add_port(
        name="P",
        center=(silicide_i.xmin, 0),
        width=silicide_i.size_info.height,
        orientation=180,
        layer=LAYER.metal1,
        port_type="electrical",
    )

    c.add_port(
        name="N",
        center=(silicide_o.xmax, 0),
        width=silicide_o.size_info.height,
        orientation=0,
        layer=LAYER.metal1,
        port_type="electrical",
    )

    return c


@gf.cell
def tlm_linear(lengths_array, layer, contact_width=7):
    """
    Create a TLM linear structure, for each of the lengths_array defined in input.
    The structure will measure electrical property of the layer specified.

    Args:
        lengths_array: list of all the spacing between two contacts.
        layer: layer of the material to be used for the TLM.
        contact_width: space left for each contact.
    """
    assert len(lengths_array) > 2, (
        "Specify at least 3 lengths for the TLM method to work"
    )
    assert layer is not None, "Specify a layer to be used for the TLM structure"

    # Component where to place the TLM
    c = gf.Component()

    # Geometrical info of the TLM
    width_contact = 20
    length_contact = contact_width
    ext_si_imp = 0.18
    ext_imp_sil = 0.5
    margin_silicide = 0.50

    # Length of the TLM
    lengths = [10, 20, 40, 80]
    total_length = (
        np.sum(lengths) + (len(lengths) + 1) * length_contact + ext_imp_sil + ext_si_imp
    )

    # Initialize the rectangle with the geometrical info
    rectangles = [
        {
            "width": width_contact + ext_si_imp * 2,
            "length": total_length + ext_si_imp * 2,
            "layer": LAYER.swg,
            "overlap": 0,
            "closing": True,
        },  # Si base
        {
            "width": width_contact,
            "length": total_length,
            "layer": layer,
            "overlap": total_length + ext_si_imp,
            "closing": False,
        },  # Layer
    ]

    # Add remainng part: silicide
    for idx in range(len(lengths) + 1):
        overlap = (
            total_length - ext_imp_sil + ext_si_imp if idx == 0 else -lengths[idx - 1]
        )
        rectangles.append(
            {
                "width": width_contact - ext_imp_sil * 2 + ext_si_imp * 2,
                "length": length_contact,
                "layer": LAYER.sblk,
                "overlap": overlap,
                "closing": False,
            }
        )

    # Create the structure
    chain = c << rectangles_chain(rectangles)

    # Change rectangles info for metal
    rectangles = [
        {
            "width": width_contact - ext_imp_sil * 2 + ext_si_imp * 2,
            "length": length_contact,
            "layer": LAYER.metal1,
        }
    ]
    for idx in range(len(lengths) + 1):
        metal = c << rectangles_chain(rectangles=rectangles)
        metal.xmin = (
            chain.xmin
            + margin_silicide
            + 0.1
            + np.sum(lengths[:idx])
            + length_contact * idx
        )

        # General contact information
        square_size = 0.48
        square_to_square_distance = 0.72
        square_to_edge_distance = 0.2

        # x direction
        width_ = metal.xmax - metal.xmin
        n = np.floor(
            (width_ + square_to_square_distance - 2 * square_to_edge_distance)
            / (square_size + square_to_square_distance)
        )
        dx = width_ - n * square_size - (n - 1) * square_to_square_distance

        dx1 = square_to_edge_distance
        dx2 = dx - square_to_edge_distance
        dx = (dx1 + dx2) / 2

        # y direction
        height_ = metal.ymax - metal.ymin
        n = np.floor(
            (height_ + square_to_square_distance - 2 * square_to_edge_distance)
            / (square_size + square_to_square_distance)
        )
        dy = (height_ - n * square_size - (n - 1) * square_to_square_distance) / 2

        # Add contact
        c << square_filling(
            filling_structure=metal,
            layer=LAYER.contact,
            square_size=square_size,
            square_to_edge_distances=[dx, dx, dy, dy],
            square_to_square_distance=square_to_square_distance,
        )

        c.add_port(
            name=f"e{idx + 1}",
            center=(metal.x, metal.ymax),
            width=length_contact,
            orientation=90,
            layer=LAYER.metal1,
            port_type="electrical",
        )

    return c


@gf.cell
def ec_with_vt(
    ec,
):
    # Component for the edge coupler
    c = gf.Component()

    # Define the edge coupler
    ec_ref = c << ec

    # Add vertical transition
    vt = c << ipr.si_anwg_transition(
        name_si_nwg_transition="VT1_D0_100_PI",
        name_nwg_anwg_transition="VT2_D2_PI",
        width_out=ec["o1"].width,
    )
    vt.connect("o2", ec_ref["o1"])

    # Add port
    c.add_port("o1", port=vt["o1"])

    # Add port
    if "oaux1" in ec_ref.ports:
        c.add_port("oaux1", port=ec_ref["oaux1"])
    else:
        c.add_port("oaux1", port=ec_ref["o1"])

    # Return block
    return c


@gf.cell
def diode_guard_ring(
    component: ComponentSpec = gf.Component,
    layers: list[dict] = None,
) -> gf.Component:
    """
    Create multiple rectangular guard rings around a component.

    Args:
        component: The core component to wrap.
        layers: List of dicts, each of which must contain:
            - layer: LayerSpec
            - thickness_x: float
            - thickness_y: float
            - distance_x: float
            - distance_y: float

    Returns:
        gf.Component with all guard rings added.
    """

    # Create parent component
    if layers is None:
        layers = []
    c = gf.Component()
    c << component

    # Component bbox
    xmin, xmax = component.xmin, component.xmax
    ymin, ymax = component.ymin, component.ymax

    # Process each ring layer
    for ring in layers:
        layer = ring["layer"]
        tx = ring["thickness_x"]
        ty = ring["thickness_y"]
        dx = ring["distance_x"]
        dy = ring["distance_y"]

        # Validate parameters
        assert tx > 0 and ty > 0
        assert dx >= 0 and dy >= 0

        # Compute geometry

        # Left rectangle
        rect = gf.components.rectangle(
            size=(tx, ymax - ymin + 2 * dy + ty),
            layer=layer,
        )
        left = c << rect
        left.xmax = xmin - dx
        left.ymin = ymin - dy

        # Right rectangle
        right = c << rect
        right.xmin = xmax + dx
        right.ymax = ymax + dy

        # Bottom rectangle
        rect = gf.components.rectangle(
            size=(xmax - xmin + 2 * dx + tx, ty),
            layer=layer,
        )
        bottom = c << rect
        bottom.xmin = xmin - dx - tx
        bottom.ymax = ymin - dy

        # Top rectangle
        top = c << rect
        top.xmin = xmin - dx
        top.ymin = ymax + dy

    # Propagate ports
    for port in component.ports:
        c.add_port(name=port.name, port=port)

    return c


@gf.cell
def pbs_with_taper(
    L_sym_coupler,
    L_phase_control,
    width,
    gap1,
    Gap,
    L_bend,
    width2,
    width3,
    L_taper,
    connection_width,
    cross_section="strip",
):
    def unilateral_taper(width1, width2, L_taper, cross_section="strip"):
        xs = gf.get_cross_section(cross_section)
        layer = xs.layer

        c = gf.Component()

        points = [
            (0, 0),
            (0, width1),
            (L_taper, width2),
            (L_taper, 0),
        ]

        c.add_polygon(points, layer=layer)

        c.add_port(
            name="o1",
            center=(0, width1 / 2),
            width=width1,
            orientation=180,
            layer=layer,
            cross_section=xs,
        )

        c.add_port(
            name="o2",
            center=(L_taper, width2 / 2),
            width=width2,
            orientation=0,
            layer=layer,
            cross_section=xs,
        )

        return c

    c = gf.Component()
    wg2 = (
        c.add_ref(
            gf.components.straight(
                length=L_sym_coupler,
                npoints=2,
                cross_section=cross_section,
                width=width,
            )
        )
        .movey(-gap1 / 2 - width / 2)
        .movex(-L_phase_control / 2 - L_taper - L_sym_coupler)
    )
    wg1 = (
        c.add_ref(
            gf.components.straight(
                length=L_sym_coupler,
                npoints=2,
                cross_section=cross_section,
                width=width,
            )
        )
        .movey(gap1 / 2 + width / 2)
        .movex(-L_phase_control / 2 - L_taper - L_sym_coupler)
    )
    bend1 = c.add_ref(
        gf.components.bend_s(
            size=(L_bend, Gap / 2 - gap1 / 2),
            npoints=99,
            cross_section=cross_section,
            allow_min_radius_violation=True,
            width=width,
        )
    )
    bend1.connect("o2", wg2.ports["o1"])
    bend2 = c.add_ref(
        gf.components.bend_s(
            size=(L_bend, Gap / 2 - gap1 / 2),
            npoints=99,
            cross_section=cross_section,
            allow_min_radius_violation=True,
            width=width,
        )
    )
    bend2.connect("o2", wg1.ports["o1"], mirror=True)

    wg3 = (
        c.add_ref(
            gf.components.straight(
                length=L_phase_control,
                npoints=2,
                cross_section=cross_section,
                width=width2,
            )
        )
        .movey(gap1 / 2 + width2 / 2)
        .movex(-L_phase_control / 2)
    )
    wg4 = (
        c.add_ref(
            gf.components.straight(
                length=L_phase_control,
                npoints=2,
                cross_section=cross_section,
                width=width3,
            )
        )
        .movey(-gap1 / 2 - (width - width3) - width3 / 2)
        .movex(-L_phase_control / 2)
    )

    taper1 = c.add_ref(
        unilateral_taper(width, width2, L_taper, cross_section=cross_section)
    )
    taper1.connect("o1", wg1.ports["o2"])
    wg3.connect("o1", taper1.ports["o2"])

    taper2 = c.add_ref(
        unilateral_taper(width, width3, L_taper, cross_section=cross_section)
    )
    taper2.connect("o1", wg2.ports["o2"])
    wg4.connect("o1", taper2.ports["o2"])

    wg5 = (
        c.add_ref(
            gf.components.straight(
                length=L_sym_coupler,
                npoints=2,
                cross_section=cross_section,
                width=width,
            )
        )
        .movey(gap1 / 2 + width / 2)
        .movex(L_phase_control / 2 + L_taper)
    )
    wg6 = (
        c.add_ref(
            gf.components.straight(
                length=L_sym_coupler,
                npoints=2,
                cross_section=cross_section,
                width=width,
            )
        )
        .movey(-gap1 / 2 - width / 2)
        .movex(L_phase_control / 2 + L_taper)
    )

    taper3 = c.add_ref(
        unilateral_taper(width2, width, L_taper, cross_section=cross_section)
    )
    taper3.connect("o1", wg3.ports["o2"])
    wg5.connect("o1", taper3.ports["o2"])

    taper4 = c.add_ref(
        unilateral_taper(width3, width, L_taper, cross_section=cross_section)
    )
    taper4.connect("o1", wg4.ports["o2"])
    wg6.connect("o1", taper4.ports["o2"])

    bend3 = c.add_ref(
        gf.components.bend_s(
            size=(L_bend, Gap / 2 - gap1 / 2),
            npoints=99,
            cross_section=cross_section,
            allow_min_radius_violation=True,
            width=width,
        )
    )
    bend3.connect("o1", wg5.ports["o2"])
    bend4 = c.add_ref(
        gf.components.bend_s(
            size=(L_bend, Gap / 2 - gap1 / 2),
            npoints=99,
            cross_section=cross_section,
            allow_min_radius_violation=True,
            width=width,
        )
    )
    bend4.connect("o1", wg6.ports["o2"], mirror=True)

    # --- rib tapers de entrada/salida ---
    tap1 = ipr.rib_taper(
        length=2,
        width1=connection_width,
        width2=bend1["o1"].width,
    )
    tap1_in = c << tap1
    tap1_in.connect("o2", bend1["o1"])
    c.add_port("o1", port=tap1_in["o1"])

    tap2 = ipr.rib_taper(
        length=2,
        width1=connection_width,
        width2=bend2["o1"].width,
    )
    tap2_in = c << tap2
    tap2_in.connect("o2", bend2["o1"])
    c.add_port("o2", port=tap2_in["o1"])

    tap3 = ipr.rib_taper(
        length=2,
        width1=bend3["o2"].width,
        width2=connection_width,
    )
    tap3_in = c << tap3
    tap3_in.connect("o1", bend3["o2"])
    c.add_port("o3", port=tap3_in["o2"])

    tap4 = ipr.rib_taper(
        length=2,
        width1=bend4["o2"].width,
        width2=connection_width,
    )
    tap4_in = c << tap4
    tap4_in.connect("o1", bend4["o2"])
    c.add_port("o4", port=tap4_in["o2"])

    c.flatten()
    return c


@gf.cell
def psr_adiabatic_taper(
    wg_width=0.41,
    wup_rib=0.362,
    wdown_rib_in=0.204,
    wdown_rib_out=0.204,
    wdown_slab_in=0.3,
    wdown_slab_out=0.41,
    gap=0.2,
    coupling_length=200,
    lt_length=10.0,
    sbend_height=2.0,
    taper_length=1.0,
    cross_section="strip",
    layers=[LAYER.swg, LAYER.rwg],  # noqa: B006
):
    c = gf.Component()
    up_arm = c << gf.components.straight(
        cross_section=gf.get_cross_section(cross_section=cross_section, width=wup_rib),
        length=coupling_length,
    )
    up_arm.movey(wup_rib / 2 + gap / 2)
    sbend = c << gf.components.bend_s(
        size=(lt_length - taper_length, sbend_height),
        cross_section=gf.get_cross_section(cross_section=cross_section, width=wup_rib),
    )
    sbend.connect("o1", up_arm.ports["o2"])
    taper = c << gf.components.taper(
        width1=wup_rib, width2=wg_width, length=taper_length, layer=layers[0]
    )
    taper.connect("o1", sbend.ports["o2"])

    c.add_polygon(
        np.array(
            [
                [0, -gap / 2],
                [0, -gap / 2 - wdown_rib_in],
                [coupling_length, -gap / 2 - wdown_rib_out],
                [coupling_length, -gap / 2],
            ]
        ),
        layer=layers[0],
    )

    c.add_polygon(
        np.array(
            [
                [coupling_length, -gap / 2],
                [coupling_length, -gap / 2 - wdown_rib_out],
                [coupling_length + lt_length, -gap / 2 - wg_width],
                [coupling_length + lt_length, -gap / 2],
            ]
        ),
        layer=layers[0],
    )

    c.add_polygon(
        np.array(
            [
                [0, -gap / 2],
                [0, -gap / 2 - wdown_slab_in],
                [coupling_length, -gap / 2 - wdown_slab_out],
                [coupling_length, -gap / 2],
            ]
        ),
        layer=layers[1],
    )

    taper_slab = c << gf.components.taper(
        width1=wdown_slab_out, width2=wdown_slab_in, length=lt_length, layer=layers[1]
    )

    taper_slab.move(
        [
            up_arm.ports["o2"].x,
            up_arm.ports["o2"].y - wup_rib / 2 - gap - wdown_slab_out / 2,
        ]
    )

    in0 = c << gf.components.taper(
        width1=wg_width, width2=wup_rib, length=3 * taper_length, layer=layers[0]
    )
    in0.connect("o2", up_arm.ports["o1"])

    c.add_port("o1", port=in0.ports["o1"])
    c.add_port(
        name="o2",
        orientation=0,
        center=(coupling_length + lt_length, -gap / 2 - wg_width / 2),
        width=wg_width,
        layer=layers[0],
    )
    c.add_port("o3", port=taper.ports["o2"])

    c.flatten()
    return c


@gf.cell
def psr_adiabatic_taper_wabsorber(
    wup_rib=0.404,
    wdown_rib_in=0.204,
    wdown_rib_out=0.204,
    wdown_slab_in=0.3,
    wdown_slab_out=0.41,
    gap=0.2,
    coupling_length=100,
    lt_length=30.0,
    wg_width=0.41,
    wg_slab_tip=0.15,
):
    @gf.cell
    def rib_spiral(
        win: float = 0.402,
        wtip=0.12,
        a: float = 2.05,
        b: float = 0.12,
        layer=LAYER.swg,
    ) -> gf.Component:
        """Returns a spiral.

        Args:
            win: width at the input.
            wtip: final width of the spiral.
            a: parameter to define the radius function.  radius= a * exp( b * angle )
            b: parameter to define the radius function.  radius= a * exp( b * angle )
            layer: layer to use. Defaults to cross_section.layer.

        """
        c = gf.Component()
        layer = gf.get_layer(layer)

        res_bent = 500
        arr_angle = np.linspace(np.pi / 2, np.pi / 2 - 3 * np.pi, res_bent)
        arr_width = np.logspace(np.log10(win), np.log10(wtip), res_bent)

        r_inner = a * np.exp(b * arr_angle) - arr_width / 2
        r_outer = a * np.exp(b * arr_angle) + arr_width / 2

        spiral_pts_x_outer = r_outer * np.cos(arr_angle)
        spiral_pts_x_inner = r_inner * np.cos(arr_angle)
        spiral_pts_y_outer = r_outer * np.sin(arr_angle)
        spiral_pts_y_inner = r_inner * np.sin(arr_angle)

        pts_x = np.concatenate([spiral_pts_x_outer, np.flip(spiral_pts_x_inner)])
        pts_y = np.concatenate([spiral_pts_y_outer, np.flip(spiral_pts_y_inner)])

        polygon_points = [(x, y) for x, y in zip(pts_x, pts_y)]

        c.add_polygon(polygon_points, layer=layer)

        c.add_port(
            name="o1",
            center=(
                (a * np.exp(b * arr_angle[0])) * np.cos(arr_angle[0]),
                (a * np.exp(b * arr_angle[0])) * np.sin(arr_angle[0]),
            ),
            width=win,
            orientation=180.0,
            layer=layer,
        )
        c.add_port(
            name="o2",
            center=(
                (a * np.exp(b * arr_angle[-1])) * np.cos(arr_angle[-1]),
                (a * np.exp(b * arr_angle[-1])) * np.sin(arr_angle[-1]),
            ),
            width=wtip,
            orientation=180.0,
            layer=layer,
        )

        f_out = CubicSpline(np.flip(arr_angle), np.flip(r_outer))
        f_in = CubicSpline(np.flip(arr_angle), np.flip(r_inner))

        arr_angle_in = np.linspace(np.pi / 2, np.pi / 2 - 1 * np.pi, res_bent)
        arr_angle_out = np.linspace(
            np.pi / 2 - 2 * np.pi, np.pi / 2 - 3 * np.pi, res_bent
        )

        spacing = f_in(arr_angle_in) - f_out(arr_angle_out)

        c.info["min_spacing"] = np.round(spacing.min(), 3)
        c.flatten()

        return c

    @gf.cell
    def slab_spiral(
        win: float = 0.30,
        wtip: float = 0.16,
        a: float = 2.05,
        b: float = 0.12,
        layer=LAYER.rwg,
    ) -> gf.Component:
        """Returns a spiral.

        Args:
            win: width at the input.
            wtip: final width of the spiral.
            a: parameter to define the radius function.  radius= a * exp( b * angle )
            b: parameter to define the radius function.  radius= a * exp( b * angle )
            layer: layer to use. Defaults to cross_section.layer.

        """
        c = gf.Component()
        layer = gf.get_layer(layer)

        res_bent = 100
        arr_angle = np.linspace(np.pi / 2, 0, res_bent)
        arr_width = np.logspace(np.log10(win), np.log10(wtip), res_bent)

        r_inner = a * np.exp(b * arr_angle) - arr_width / 2
        r_outer = a * np.exp(b * arr_angle) + arr_width / 2

        spiral_pts_x_outer = r_outer * np.cos(arr_angle)
        spiral_pts_x_inner = r_inner * np.cos(arr_angle)
        spiral_pts_y_outer = r_outer * np.sin(arr_angle)
        spiral_pts_y_inner = r_inner * np.sin(arr_angle)

        pts_x = np.concatenate([spiral_pts_x_outer, np.flip(spiral_pts_x_inner)])
        pts_y = np.concatenate([spiral_pts_y_outer, np.flip(spiral_pts_y_inner)])

        polygon_points = [(x, y) for x, y in zip(pts_x, pts_y)]

        c.add_polygon(polygon_points, layer=layer)

        c.add_port(
            name="o1",
            center=(
                (a * np.exp(b * arr_angle[0])) * np.cos(arr_angle[0]),
                (a * np.exp(b * arr_angle[0])) * np.sin(arr_angle[0]),
            ),
            width=win,
            orientation=180.0,
            layer=layer,
        )
        c.add_port(
            name="o2",
            center=(
                (a * np.exp(b * arr_angle[-1])) * np.cos(arr_angle[-1]),
                (a * np.exp(b * arr_angle[-1])) * np.sin(arr_angle[-1]),
            ),
            width=wtip,
            orientation=180.0,
            layer=layer,
        )

        c.flatten()

        return c

    c = gf.Component()

    psr = c << psr_adiabatic_taper(
        wup_rib=wup_rib,
        wdown_rib_in=wdown_rib_in,
        wdown_rib_out=wdown_rib_out,
        wdown_slab_in=wdown_slab_in,
        wdown_slab_out=wdown_slab_out,
        gap=gap,
        coupling_length=coupling_length,
        lt_length=lt_length,
        wg_width=wg_width,
    )

    spiral = c << rib_spiral(win=wdown_rib_in, wtip=0.1)

    spiral.mirror_x()
    aux_y = psr.ports["o1"].y - spiral.ports["o1"].y - wup_rib / 2 - gap
    spiral.move(
        [psr.ports["o1"].x - spiral.ports["o1"].x + 3.0, aux_y - wdown_rib_in / 2]
    )

    spiral_slab = c << slab_spiral(
        win=wdown_slab_in,
        wtip=wg_slab_tip,
    )
    spiral_slab.mirror_x()
    spiral_slab.move([0, aux_y - wdown_slab_in / 2])

    c.add_port("o1", port=psr.ports["o1"])
    c.add_port("o2", port=psr.ports["o2"])
    c.add_port("o3", port=psr.ports["o3"])

    c.flatten()
    return c


@gf.cell
def square_filling(
    filling_structure: ComponentSpec = gf.Component(),
    layer: LayerSpec = LAYER.contact,
    square_size: float = 0.48,
    square_to_edge_distances: float = [0.5, 0.5, 0.5, 0.5],
    square_to_square_distance: float = 0.72,
) -> gf.Component:
    """
    Same behavior as before for computing nx, ny.
    After that, recompute pitch so the squares evenly fill the region
    between the left and right boundaries (with edge offsets respected).

    Args:
        filling_structure: The component defining the area to fill with squares.
            Defaults to gf.Component().
        layer: The layer on which to place the squares.
            Defaults to LAYER.contact.
        square_size: The size of each square.
            Defaults to 0.48.
        square_to_edge_distances: A list of 4 values defining the distance from the
            squares to the left [0], right [1], bottom [2] and top [3] edges of
            the filling structure, respectively.
            Defaults to [0.5, 0.5, 0.5, 0.5].
        square_to_square_distance: The distance between adjacent squares´
            (both horizontally and vertically).
            Defaults to 0.72.
    """

    # Validate parameters
    assert square_size > 0, "square_size must be positive."
    assert square_to_square_distance > 0, (
        "square_to_square_distance must be non-negative."
    )
    for square_to_edge_distance in square_to_edge_distances:
        assert square_to_edge_distance > 0, (
            "square_to_edge_distance must be non-negative."
        )
    assert len(square_to_edge_distances) == 4, (
        "square_to_edge_distances must have 4 values for left,"
    )
    "right, bottom and top edges."

    # Get bounding box
    xmin = filling_structure.xmin
    xmax = filling_structure.xmax
    ymin = filling_structure.ymin
    ymax = filling_structure.ymax

    length_x = xmax - xmin
    length_y = ymax - ymin

    # -------- Compute nx, ny EXACTLY as before --------
    nominal_pitch = square_size + square_to_square_distance
    nx = int(
        np.round(
            (
                length_x
                - square_to_edge_distances[0]
                - square_to_edge_distances[1]
                + square_to_square_distance
            )
            / nominal_pitch,
            3,
        )
    )
    ny = int(
        np.round(
            (
                length_y
                - square_to_edge_distances[2]
                - square_to_edge_distances[3]
                + square_to_square_distance
            )
            / nominal_pitch,
            3,
        )
    )

    # Component to return
    c = gf.Component()

    if nx <= 0 or ny <= 0:
        return c

    # -------- Recompute pitch to fill entire span uniformly --------
    # Available region inside edges:
    avail_x = length_x - square_to_edge_distances[0] - square_to_edge_distances[1]
    avail_y = length_y - square_to_edge_distances[2] - square_to_edge_distances[3]

    if nx > 1:
        pitch_x = (avail_x - square_size) / (nx - 1)
    else:
        pitch_x = 0  # single square centered at the available start

    if ny > 1:
        pitch_y = (avail_y - square_size) / (ny - 1)
    else:
        pitch_y = 0

    if pitch_y > 0.72 + square_size:
        pitch_y = 0.72 + square_size
    if pitch_x > 0.72 + square_size:
        pitch_x = 0.72 + square_size

    # -------- Create square primitive --------
    square = gf.components.rectangle(
        size=(square_size, square_size),
        layer=layer,
    )

    # Start position, respecting edge distance
    start_x = xmin + square_to_edge_distances[1]
    start_y = ymin + square_to_edge_distances[3]

    # -------- Place squares with new pitch --------
    for ix in range(nx):
        for iy in range(ny):
            x = start_x + ix * pitch_x
            y = start_y + iy * pitch_y
            ref = c << square
            ref.move((x, y))

    return c


def rectangles_chain(rectangles: list[dict] | None = None) -> gf.Component:
    """
    Generate a sequence of rectangles placed sequentially along the x-axis.

    Each rectangle is defined by a dictionary containing its geometry.
    Rectangles are placed one after the other starting from x = 0.
    If an overlap value is provided, the next rectangle starts at:

        previous_end_x - overlap

    If two consecutive rectangles have the same width, they naturally form
    a continuous larger rectangle.

    Args:
        rectangles (list[dict], optional):
            List of dictionaries describing each rectangle.

            Required dictionary keys:
                width (float): Rectangle width (y dimension).
                length (float): Rectangle length (x dimension).
                layer (tuple[int, int]): GDS layer defined as (layer, datatype).

            Optional dictionary keys:
                overlap (float): Overlap with the previous rectangle.
                    Default = 0.
    """

    rectangles = rectangles or []

    # -------------------------------------
    # Validate input list
    # -------------------------------------
    if len(rectangles) == 0:
        raise ValueError(
            "The rectangles list is empty. At least one rectangle must be provided."
        )

    c = gf.Component()

    current_x = 0

    for i, rect in enumerate(rectangles):
        # -------------------------------------
        # Check required parameters
        # -------------------------------------
        required = ["width", "length", "layer"]
        missing = [p for p in required if p not in rect]

        if missing:
            raise ValueError(
                f"Rectangle index {i} is missing required parameters: {missing}. "
                "Each rectangle must contain 'width', 'length', and 'layer'."
            )

        width = rect["width"]
        length = rect["length"]
        layer = rect["layer"]
        closing = rect.get("closing", False)
        overlap = rect.get("overlap", 0)

        # -------------------------------------
        # Create rectangle
        # -------------------------------------
        rect_component = gf.components.rectangle(size=(length, width), layer=layer)
        ref = c << rect_component

        # -------------------------------------
        # Position rectangle
        # -------------------------------------
        if i == 0:
            ref.move((current_x, -width / 2))
        else:
            start_x = current_x - overlap
            ref.move((start_x, -width / 2))

        current_x = ref.xmax

        if closing:
            bump_ref = c << bump(layer=layer, width=width, height=0.1)
            bump_ref.rotate(90)
            bump_ref.xmax = ref.xmin
            bump_ref.y = ref.y

            bump_ref = c << bump(layer=layer, width=width, height=0.1)
            bump_ref.rotate(-90)
            bump_ref.xmin = ref.xmax
            bump_ref.y = ref.y

    return c


@gf.cell
def tower_pd_eo(component_pd: ComponentSpec = "tower_pd", kind=1) -> gf.Component:
    """Place a Pd in the wanted position.

    Args:
        component_pd: Photodiode component to place.
            Defaults to "tower_pd".
        kind: Specify how to add the electrical part.
    """

    # Resolve specs to components
    pd_comp = gf.get_component(component_pd)

    # Create the working component
    c = gf.Component()

    # Place the PD component
    pd_ref = c << pd_comp

    # Add ports: expose the taper input as the component input
    c.add_port("o1", port=pd_ref["o1"])

    if kind == 1:
        # Electrical components
        # ----- Electrical part N ----
        # Place a reactangle for routing
        tap = c << gf.components.taper(
            width1=19.28,
            width2=11,
            length=(19.28 - 11),
            layer=LAYER.metal1,
        )
        tap.move((5.78, -10.34))

        # Place a via to go back to metal 3
        via = c << via_metal2_metal3(size=(11, 11))
        via.xmin = tap.xmax
        via.y = tap.y
        c.add_port("e1", port=via["e4"])

        # ----- Electrical part P ----
        # Place a metal to go down and right of the central part
        strt = c << gf.c.straight(
            length=25, cross_section=gf.get_cross_section("metal1", width=7)
        )
        strt.rotate(90)
        strt.move((0, -0.7))
        strt2 = c << gf.c.straight(
            length=11, cross_section=gf.get_cross_section("metal1", width=11)
        )

        strt2.xmax = strt.xmin
        strt2.ymax = strt.ymax

        # Place a via to go back to metal 3
        via = c << via_metal2_metal3(size=(11, 11))
        via.xmax = strt2.xmin
        via.y = strt2.y

        c.add_port("e2", port=via["e2"])
    else:
        # Electrical components
        # ----- Electrical part N ----
        strt = c << gf.c.straight(
            length=5, cross_section=gf.get_cross_section("metal2", width=10)
        )
        strt.connect("e1", pd_ref["e1"])

        # Place a reactangle for routing
        tap = c << gf.components.taper(
            width1=10,
            width2=11,
            length=1,
            layer=LAYER.metal2,
            port_names=["e1", "e2"],
            port_types=["electrical", "electrical"],
        )
        tap.connect("e1", strt["e2"])

        # Place a via to go back to metal 3
        via = c << via_metal2_metal3(size=(11, 11))
        via.xmax = tap.xmin
        via.y = tap.y

        c.add_port("e2", port=via["e1"])

        # ----- Electrical part P ----
        strt = c << gf.c.straight(
            length=5, cross_section=gf.get_cross_section("metal2", width=10)
        )
        strt.connect("e1", pd_ref["e2"])

        # Place a reactangle for routing
        tap = c << gf.components.taper(
            width1=10,
            width2=11,
            length=1,
            layer=LAYER.metal2,
            port_names=["e1", "e2"],
            port_types=["electrical", "electrical"],
        )
        tap.connect("e1", strt["e2"])

        # Place a via to go back to metal 3
        via = c << via_metal2_metal3(size=(11, 11))
        via.xmin = tap.xmax
        via.y = tap.y

        c.add_port("e1", port=via["e3"])

    return c


###########################
### Measuring Utilities ###
###########################
def measure_structure(component):
    # Create a gds component
    c = gf.Component()

    # Add a info with the component
    c.info["Block 1"] = {component: 1}

    return c
