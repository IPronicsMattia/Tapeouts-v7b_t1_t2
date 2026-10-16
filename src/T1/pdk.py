import gdsfactory as gf
import iprlayout_tower as ipr  # type: ignore
import numpy as np
from gdsfactory.typings import ComponentSpec, CrossSectionSpec, LayerSpec
from iprlayout_tower.tower_tech import LAYER  # type: ignore

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


def T1_dummy_adder(
    component, distance_metal, distane_wvg, delta_hor_ver_metal=0, delta_hor_ver_wvg=0
):
    dummy_dict_list = []

    for idx in range(2):
        # Metal 1
        layer = LAYER.metal1 if idx == 0 else (8, 31)
        dummy_dict_list.append(
            {
                "slot_size": 2,
                "pitch": 2.5,
                "margin_tb": distance_metal,
                "margin_lr": distance_metal + delta_hor_ver_metal,
                "slot_layer": layer,
            }
        )

        # Metal 2
        layer = LAYER.metal2 if idx == 0 else (18, 31)
        dummy_dict_list.append(
            {
                "slot_size": 2,
                "pitch": 2.5,
                "margin_tb": distance_metal,
                "margin_lr": distance_metal + delta_hor_ver_metal,
                "slot_layer": layer,
            }
        )

        # Metal 3
        layer = LAYER.metal3 if idx == 0 else (28, 31)
        dummy_dict_list.append(
            {
                "slot_size": 4,
                "pitch": 6.5,
                "margin_tb": distance_metal,
                "margin_lr": distance_metal + delta_hor_ver_metal,
                "slot_layer": layer,
            }
        )

        # Si
        layer = LAYER.swg if idx == 0 else (171, 31)
        dummy_dict_list.append(
            {
                "slot_size": 3,
                "pitch": 5,
                "margin_tb": distane_wvg,
                "margin_lr": distane_wvg + delta_hor_ver_wvg,
                "slot_layer": layer,
            }
        )

        # SiN
        layer = LAYER.nwg if idx == 0 else (174, 31)
        dummy_dict_list.append(
            {
                "slot_size": 3.0,
                "pitch": 3.5,
                "margin_tb": distane_wvg,
                "margin_lr": distane_wvg + delta_hor_ver_wvg,
                "slot_layer": layer,
            }
        )

    return ipr.dummy_adder(dummy_dict_list, component)


@gf.cell
def component_with_transition(component):
    c = gf.Component()

    # Place the component
    comp_ref = c << component

    # Add transition
    trans = c << gf.c.rectangle(
        size=(component.xsize, component.ysize), layer=(118, 120)
    )
    trans.center = comp_ref.center

    # Add ports
    for port in component.ports:
        c.add_port(port.name, port=port)

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
        center=(0, 0.001),
        width=width,
        orientation=270,
        layer=layer,
    )
    return c


@gf.cell
def mzi_cell(
    order_mzi_length: float = 9.5054,
    splitter: ComponentSpec = "mmi_luka",
    bend: ComponentSpec = "bend_euler_custom_width",
    cross_section: CrossSectionSpec = "strip",
    cross_section2: CrossSectionSpec = "strip",
    extra_component: ComponentSpec | None = None,
) -> gf.Component:
    """This test structure allows to measure the group index of a waveguide.
     There are 2 AMZIs with splitters 2x2.

    Args:
        low_order_mzi_length: imbalance length of the first amzi.
        high_order_mzi_length: imbalance lelngth of the second mzi.
        splitter: splitter2x2 component.
        bend: bend: component for bending 90°.
        grating_coupler: grating coupler compoennt.
        pitch_um: distance between gratings.
        cross_section: spec.
        type: 0 the inputs/outputs of both amzi are placed together,
           1 first input and output of one amzi, an then the input
           and output of the second one.
    """

    # Create a new component
    c = gf.Component()

    # Get splitter component to calculate its length
    splitter = gf.get_component(splitter)
    splitter_length = splitter["o3"].x - splitter["o2"].x

    # Get bend component to calculate its radius
    bend = gf.get_component(bend)
    bend_radius = bend["o2"].x - bend["o1"].x

    # Get the cross section
    cross_section = gf.get_cross_section(cross_section)

    # If present, get also the additional component (taper or vt)
    if extra_component:
        tap = gf.get_component(extra_component)

    # Initialize the arrays needed
    mzis = [0] * 2
    vectorx = [0, splitter_length * 2 + bend_radius * 4 - 11.46]
    vectory = [0, 0]
    lengths = [
        order_mzi_length + 2,
        2,
    ]
    ports1 = []
    ports2 = []

    # Start placing the splitters
    hor = 10
    for n in range(2):
        mzis[n] = c << splitter

        if n % 2 == 0:
            mzis[n].move([vectorx[n], vectory[n]])
            c.add_port(f"o{2 * n + 3}", port=mzis[n].ports["o1"])
            c.add_port(f"o{2 * n + 2}", port=mzis[n].ports["o2"])

            ports1.append(mzis[n].ports["o4"])
            line = c << ipr.straight(length=hor, cross_section=cross_section)
            line.connect("o1", mzis[n].ports["o3"])
            ports1.append(line["o2"])
        else:
            mzis[n].mirror_x()
            mzis[n].move([vectorx[n], vectory[n]])
            c.add_port(f"o{2 * n + 2}", port=mzis[n].ports["o1"])
            c.add_port(f"o{2 * n - 1}", port=mzis[n].ports["o2"])

            ports2.append(mzis[n].ports["o4"])
            line = c << ipr.straight(length=hor, cross_section=cross_section)
            line.connect("o2", mzis[n].ports["o3"])
            ports2.append(line["o1"])

    for n in range(2):
        if extra_component is None:
            steps = [
                {"dx": bend_radius},
                {"dy": -(lengths[n] / 2 + bend_radius * 2)},
                {"dx": bend_radius * 2 + hor + (20 if n % 2 == 0 else 0)},
                {"dy": (lengths[n] / 2 + bend_radius * 2)},
            ]

            gf.routing.route_single(
                c,
                ports1[n],
                ports2[n],
                steps=steps,
                bend=bend,
                cross_section=cross_section,
                auto_taper=False,
                straight=ipr.straight,
            )
        else:
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
                bend=bend,
                cross_section=cross_section,
                auto_taper=False,
                straight=ipr.straight,
            )

    return c


@gf.cell
def mzis_test_group_and_effective_index(
    low_order_mzi_length: float = 9.5054,
    high_order_mzi_length: float = 95.0535,
    splitter: ComponentSpec = "rib_mmi",
    bend: ComponentSpec = "euler_bend",
    grating_coupler: ComponentSpec = "gc",
    pitch_um: float = 127.0,
    cross_section: CrossSectionSpec = "strip",
    cross_section2: CrossSectionSpec = "strip",
    extra_component: ComponentSpec | None = None,
) -> gf.Component:
    """This test structure allows to measure the group index of a waveguide.
     There are 2 AMZIs with splitters 2x2.

    Args:
        low_order_mzi_length: imbalance length of the top mzi.
        high_order_mzi_length: imbalance lelngth of the bottom mzi.
        splitter: 2x2 splitter component at input and output of mzi.
        bend: component for bending 90°.
        grating_coupler: grating coupler compoennt in input of structure.
        pitch_um: distance between gratings.
        cross_section: cross section used for routing
        cross_section2: cross section used inside extra_component
        extra_component: component to be used in the vertical section
    """
    c = gf.Component()
    splitter = gf.get_component(splitter)
    gc = gf.get_component(grating_coupler)
    cross_section = gf.get_cross_section(cross_section)

    fa_in = c << ipr.grating_coupler_array(
        grating_coupler=gc,
        pitch=pitch_um,
        n=10,
        with_loopback=True,
        dx=5,
        cross_section=cross_section,
    )
    fa_in.rotate(90)

    mzi_low_order = c << mzi_cell(
        order_mzi_length=low_order_mzi_length,
        bend=bend,
        cross_section=cross_section,
        cross_section2=cross_section2,
        splitter=splitter,
        extra_component=extra_component,
    )
    mzi_low_order.rotate(90)
    mzi_high_order = c << mzi_cell(
        order_mzi_length=high_order_mzi_length,
        bend=bend,
        cross_section=cross_section,
        cross_section2=cross_section2,
        splitter=splitter,
        extra_component=extra_component,
    )
    mzi_high_order.rotate(-90)

    bend_radius = bend["o2"].x - bend["o1"].x
    mzi_low_order.ymax = fa_in["o5"].y - 3 * bend_radius
    mzi_low_order.xmin = fa_in["o5"].x + 2 * bend_radius
    mzi_high_order.ymax = fa_in["o4"].y - 3 * bend_radius
    mzi_high_order.xmax = fa_in["o4"].x - 2 * bend_radius

    port_pairs = [
        [fa_in["o1"], mzi_high_order["o4"]],
        [fa_in["o2"], mzi_high_order["o3"]],
        [fa_in["o3"], mzi_high_order["o2"]],
        [fa_in["o4"], mzi_high_order["o1"]],
    ]
    for idx, port_pair in enumerate(port_pairs):
        gf.routing.route_single(
            c,
            port_pair[0],
            port_pair[1],
            cross_section=cross_section,
            bend=bend,
            auto_taper=False,
            start_straight_length=bend_radius if idx == 1 else 0,
        )

    port_pairs = [
        [fa_in["o5"], mzi_low_order["o2"]],
        [fa_in["o6"], mzi_low_order["o1"]],
        [fa_in["o7"], mzi_low_order["o4"]],
        [fa_in["o8"], mzi_low_order["o3"]],
    ]
    for idx, port_pair in enumerate(port_pairs):
        gf.routing.route_single(
            c,
            port_pair[0],
            port_pair[1],
            cross_section=cross_section,
            bend=bend,
            auto_taper=False,
            start_straight_length=bend_radius if idx == 2 else 0,
        )

    return c


def straight_410_gwg(length: float, **kwargs):  # Level 0
    straight_sh_xs = gf.get_cross_section(
        "shallow", width=0.41, offset_rwg=0.795, offset_gwg=1.795
    )
    kwargs["cross_section"] = straight_sh_xs
    kwargs["additional_name"] = "gwg"
    return gf.partial(ipr.fast_straight, length=length, **kwargs)()


def straight_100_swg(length: float, **kwargs):  # Level 0
    kwargs["cross_section"] = gf.get_cross_section("strip", layer=LAYER.swg, width=0.1)
    return gf.partial(ipr.fast_straight, length=length, **kwargs)()


def straight_410_swg(length: float, **kwargs):  # Level 0
    kwargs["cross_section"] = gf.get_cross_section("strip", layer=LAYER.swg, width=0.41)
    return gf.partial(ipr.fast_straight, length=length, **kwargs)()


def straight_930_swg(length: float, **kwargs):  # Level 0
    kwargs["cross_section"] = gf.get_cross_section("strip", layer=LAYER.swg, width=0.93)
    return gf.partial(ipr.fast_straight, length=length, **kwargs)()


def straight_1560_swg(length: float, **kwargs):  # Level 0
    kwargs["cross_section"] = gf.get_cross_section("strip", layer=LAYER.swg, width=1.56)
    return gf.partial(ipr.fast_straight, length=length, **kwargs)()


def straight_700_anwg(length: float, **kwargs):  # Level 0
    kwargs["cross_section"] = gf.get_cross_section(
        "nitride2", layer=LAYER.anwg, width=0.70
    )
    return gf.partial(ipr.fast_straight, length=length, **kwargs)()


def straight_100_nwg(length: float, **kwargs):  # Level 0
    kwargs["cross_section"] = gf.get_cross_section(
        "nitride", layer=LAYER.nwg, width=0.10
    )
    return gf.partial(ipr.fast_straight, length=length, **kwargs)()


def straight_1000_nwg(length: float, **kwargs):  # Level 0
    kwargs["cross_section"] = gf.get_cross_section(
        "nitride", layer=LAYER.nwg, width=1.00
    )
    return gf.partial(ipr.fast_straight, length=length, **kwargs)()


def straight_150_anwg(length: float, **kwargs):  # Level 0
    kwargs["cross_section"] = gf.get_cross_section(
        "nitride2", layer=LAYER.anwg, width=0.15
    )
    return gf.partial(ipr.fast_straight, length=length, **kwargs)()


def straight_1500_anwg(length: float, **kwargs):  # Level 0
    kwargs["cross_section"] = gf.get_cross_section(
        "nitride2", layer=LAYER.anwg, width=1.50
    )
    return gf.partial(ipr.fast_straight, length=length, **kwargs)()


def straight_2000_anwg(length: float, **kwargs):  # Level 0
    kwargs["cross_section"] = gf.get_cross_section(
        "nitride2", layer=LAYER.anwg, width=2.00
    )
    return gf.partial(ipr.fast_straight, length=length, **kwargs)()


def straigth_with_3d_cross_strip(angle=90, separation=5, below=True):
    """
    Create a straight formed by a series of strip crossing
    """

    # Define Si cross sections
    xs_si = gf.get_cross_section("strip", width=0.93)

    # Define Si nitride cross section
    xs_awng = gf.get_cross_section("nitride2", width=2.00)

    if below:
        # Define the 3d_crossing
        cross_3d_comp = ipr.crossing_3D(
            cross_section1=xs_si,
            cross_section2=xs_awng,
            angle=angle,
            length1=0,
            length2=5.0 / np.sin(angle / 180 * np.pi),
        )

        # Prepare straight with a bump
        bump_ref = bump(layer=xs_awng.layer, width=2.00, height=0.1)
        kwargs = {"bbmul": cross_3d_comp, "bbadd": bump_ref, "bbmul_list": ["o2", "o4"]}
        cross_3d = ipr.bb_mul_bb(**kwargs)
        cross_3d.function_name = cross_3d_comp.function_name
        cross_3d.settings = cross_3d_comp.settings
        cross_3d = change_port(
            component=cross_3d, ports_i=["o1", "o3"], ports_o=["o1", "o2"]
        )

        # Transition between swg 930 to swg 410
        transition = ipr.rib_taper(cross_section="strip", width_RIB_out=0.93)

        # Define which straight to use
        straight = straight_930_swg

    else:
        # Define the 3d_crossing
        cross_3d_comp = ipr.crossing_3D(
            cross_section1=xs_awng,
            cross_section2=xs_si,
            angle=angle,
            length1=0,
            length2=np.round(10 / np.sin(angle / 180 * np.pi) - 0.2, 3),
        )

        # Prepare straight with a bump
        bump_ref = bump(layer=xs_si.layer, width=0.93, height=0.1)
        kwargs = {"bbmul": cross_3d_comp, "bbadd": bump_ref, "bbmul_list": ["o2", "o4"]}
        cross_3d = ipr.bb_mul_bb(**kwargs)
        cross_3d.function_name = cross_3d_comp.function_name
        cross_3d.settings = cross_3d_comp.settings

        cross_3d = change_port(
            component=cross_3d, ports_i=["o1", "o3"], ports_o=["o1", "o2"]
        )

        # Transition between nitride and swg
        vt_opt_te = ipr.si_anwg_transition(
            width_out=2.0,
        )

        feature_vtstraight = {
            "bbmul": vt_opt_te,
            "bbadd": straight_410_swg(0.5),
            "bbmul_list": ["o1"],
        }
        transition = ipr.bb_mul_bb(**feature_vtstraight)

        # Define which straight to use
        straight = straight_2000_anwg

    io_length = transition["o2"].x - transition["o1"].x

    # Define the kwargs for the straight
    kwargs = {
        # Needed for calculation
        "2_bb_extra_length": separation,
        "2_io_length": io_length,
        "2_sep_distance": separation,
        # Created nbb_straight
        "1_bb": cross_3d,
        "1_straight": straight,
        "1_sep_distance": separation,
        "1_sep_variation": 0.141,
        # Create bb_straight_bb_limited
        "straight": ipr.nbb_straight,
        "straight_limited": straight_410_swg,
        "bb1": transition,
        "bb2": transition,
        "bb2_rev": True,
    }
    straight_out = gf.partial(ipr.bb_straight_bb_limited, **kwargs)

    return straight_out, kwargs, cross_3d_comp


def straigth_with_3d_cross_shallow(angle=90, separation=5, below=True):
    """
    Create a straight formed by a series of shallow crossing
    """

    if below:
        # Define Si cross sections
        xs_gwg = gf.get_cross_section("shallow", width=0.41)

        # Define Si nitride cross section
        xs_anwg = gf.get_cross_section("nitride2", width=1.50)

        # Define the 3d_crossing
        cross_3d_comp = ipr.crossing_3D(
            cross_section1=xs_gwg,
            cross_section2=xs_anwg,
            angle=angle,
            length1=0,
            length2=np.round(5.0 / np.sin(angle / 180 * np.pi), 3),
        )

        # Prepare crossing with a bump
        bump_ref = bump(layer=xs_anwg.layer, width=1.50, height=0.1)
        kwargs = {"bbmul": cross_3d_comp, "bbadd": bump_ref, "bbmul_list": ["o2", "o4"]}
        cross_3d = ipr.bb_mul_bb(**kwargs)
        cross_3d.function_name = cross_3d_comp.function_name
        cross_3d.settings = cross_3d_comp.settings

        cross_3d = change_port(
            component=cross_3d, ports_i=["o1", "o3"], ports_o=["o1", "o2"]
        )

        # Transition between swg 410 to gwg 410
        transition = ipr.layer_transition_single_taper(
            length_total=16,
            length_SLAB=15,
            m_SLAB=2,
            m_RIB=1.5,
            width_SLAB_out=2,
            width_SLAB_in=0.41,
            width_RIB_in=0.41,
            width_RIB_out=0.41,
            layers=[LAYER.swg, LAYER.rwg, LAYER.gwg],
        )

        # Define which straight to use
        straight = straight_410_gwg

    else:
        # Define Si cross sections
        xs_gwg = gf.get_cross_section("strip", width=0.41)

        # Define SiN2 cross section (join with gwg)
        xs_add1 = gf.Section(
            layer=LAYER.rwg, width=10 + 0.6 / np.sin(angle / 180 * np.pi)
        )
        xs_add2 = gf.Section(
            layer=LAYER.gwg, width=12 + 0.6 / np.sin(angle / 180 * np.pi)
        )
        xs_anwg = gf.cross_section.cross_section(
            layer=LAYER.anwg,
            width=1.50,
            sections=[xs_add1, xs_add2],
            main_section_name=f"nitride2_gwg_{angle}",
        )
        xs_anwg_io = gf.cross_section.cross_section(
            layer=LAYER.anwg,
            width=1.50,
            sections=[xs_add2],
            main_section_name=f"nitride2_gwg_{angle}_io",
        )

        # Define the 3d_crossing
        cross_3d_comp = ipr.crossing_3D(
            cross_section1=xs_anwg,
            cross_section2=xs_gwg,
            angle=angle,
            length1=0,
            length2=np.round(10.0 / np.sin(angle / 180 * np.pi) - 0.2, 3),
        )

        # Prepare crossing with a bump
        bump_ref = bump(layer=xs_gwg.layer, width=0.41, height=0.1)
        kwargs = {"bbmul": cross_3d_comp, "bbadd": bump_ref, "bbmul_list": ["o2", "o4"]}

        cross_3d = ipr.bb_mul_bb(**kwargs)
        cross_3d.function_name = cross_3d_comp.function_name
        cross_3d.settings = cross_3d_comp.settings

        cross_3d = change_port(
            component=cross_3d, ports_i=["o1", "o3"], ports_o=["o1", "o2"]
        )

        # Define which straight to use
        kwargs = {"cross_section": xs_anwg}
        straight = gf.partial(ipr.fast_straight, **kwargs)

        kwargs_io = {"cross_section": xs_anwg_io}
        straight_io = gf.partial(ipr.fast_straight, **kwargs_io)

        # Transition between nitride and swg
        # --- add a waveguide lateral
        vt_transition = ipr.si_anwg_transition(
            width_out=1.5,
        )
        kwargs = {
            "bbmul": vt_transition,
            "bbadd": straight_io(length=1),
            "bbmul_list": ["o2"],
        }
        tr_ref = ipr.bb_mul_bb(**kwargs)

        kwargs = {
            "bbmul": tr_ref,
            "bbadd": straight(length=5 / np.sin(angle / 180 * np.pi)),
            "bbmul_list": ["o2"],
        }
        transition = ipr.bb_mul_bb(**kwargs)

    io_length = transition["o2"].x - transition["o1"].x

    # Define the kwargs for the straight
    kwargs = {
        # Needed for calculation
        "2_bb_extra_length": separation,
        "2_io_length": io_length,
        "2_sep_distance": separation,
        # Created nbb_straight
        "1_bb": cross_3d,
        "1_straight": straight,
        "1_sep_distance": separation,
        "1_sep_variation": 0.141,
        # Create bb_straight_bb_limited
        "straight": ipr.nbb_straight,
        "straight_limited": straight_410_gwg,
        "bb1": transition,
        "bb2": transition,
        "bb2_rev": True,
    }
    straight_out = gf.partial(ipr.bb_straight_bb_limited, **kwargs)

    return straight_out, kwargs, cross_3d_comp


def all_metal_text(text, size, justify):
    """
    Create a text in all 3 metal layer to improve density
    """
    text_upper = text.upper()
    c = gf.Component(text)

    c << ipr.text(text_upper, size=size, layer=LAYER.metal1, justify=justify)
    c << ipr.text(text_upper, size=size, layer=LAYER.metal2, justify=justify)
    c << ipr.text(text_upper, size=size, layer=LAYER.metal3, justify=justify)

    return c


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


def tps_410_swg_1560_swg_lim(length: float, **kwargs):  # Level 1
    rb_taper = kwargs["bb1"]

    # Add a IO of 1 um
    kwargs["straight"] = straight_410_swg
    kwargs["bb1"] = None
    kwargs["bb2"] = rb_taper
    rb_taper_in = ipr.bb_straight_bb(length=1.0, **kwargs)

    # Add the correct kwargs
    kwargs["straight"] = straight_1560_swg
    kwargs["straight_limited"] = straight_410_swg
    kwargs["bb1"] = rb_taper_in
    kwargs["bb2"] = rb_taper_in
    kwargs["bb2_rev"] = "True"
    return gf.partial(ipr.bb_straight_bb_limited, length, **kwargs)()


@gf.cell
def triangle_round(
    layer: LayerSpec = LAYER.metal2,
    squareness_length: float = 10,
    size: tuple = (250, 250),
) -> gf.Component:
    c = gf.Component()

    points = [
        (0, 0),
        (0, size[1] - squareness_length),
        (squareness_length, size[1] - squareness_length),
        (size[0] - squareness_length, squareness_length),
        (size[0] - squareness_length, 0),
    ]
    c.add_polygon(points, layer=layer)

    return c


######################
### Test Structure ###
######################
@gf.cell
def grating_array_test_structure(
    components_grating_coupler: list,
    component_bend: ComponentSpec = "bend_euler",
    component_straight_routing: ComponentSpec = straight_410_swg,
    extra_loopback_distance: float = 10,
    xs_routing: CrossSectionSpec = "strip",
) -> gf.Component:
    """
    Place a grating array with custom gratings to be tested.

    Args:
        component_bend (ComponentSpec): Bend used for routing.
            Defaults to "bend_euler".
        components_grating_coupler (List[tuple]): Array of grating coupler to be tested.
            Defaults to [].
        component_straight_routing (ComponentSpec) : Component used for routing.
            Default to gf.c.straight
        extra_loopback_distance (float): additional distance from grating to loopback routing.
            Default to 10.
        xs_routing (CrossSectionSpec): Cross section of waveguide used for routing.
            Defaults to "strip".
    """
    # Component where to place the gratings
    c = gf.Component()

    # Get the grating coupler components
    bend = gf.get_component(component_bend)
    gcs = [gf.get_component(gc) for gc in components_grating_coupler]
    n_gcs = int((len(components_grating_coupler) - 2) / 2)

    # Place the gratings in a line, spaced by 127 in x
    gratings = []
    for idx, gc in enumerate(gcs):
        grating_inst = c << gc
        grating_inst.rotate(180)
        grating_inst.xmin = 0
        grating_inst.y = 127 * idx - grating_inst.ymax
        gratings.append(grating_inst)

    # Routing in pair the central gratings
    routes = []
    for idx in range(n_gcs):
        route = gf.routing.route_single(
            c,
            gratings[2 * idx + 1]["o1"],
            gratings[2 * idx + 2]["o1"],
            port_type="optical",
            auto_taper=False,
            allow_width_mismatch=False,
            cross_section=xs_routing,
            bend=bend,
            straight=component_straight_routing,
        )
        routes.append(route)

    # Routing of the loopback
    radius = abs(bend["o2"].x - bend["o1"].x)
    steps = [
        {"dx": radius},
        {"y": c.ymin - 2 * radius + 3.363},
        {"dx": -2 * radius - extra_loopback_distance - gc.xsize},
        {"y": c.ymax + 2 * radius - 3.363},
        {"dx": 2 * radius + extra_loopback_distance + gc.xsize},
        {"y": gratings[-1]["o1"].y},
    ]
    gf.routing.route_single(
        c,
        gratings[0]["o1"],
        gratings[-1]["o1"],
        port_type="optical",
        auto_taper=False,
        allow_width_mismatch=False,
        cross_section=xs_routing,
        bend=bend,
        steps=steps,
    )

    # Prepare the save dictionary for json
    for idx, route in enumerate(reversed(routes)):
        out_dict = {}
        for inst in route.instances:
            temp_dict = ipr.measure_component(inst.cell, scale=1 / 1000)
            out_dict = ipr.combine_component_dict(out_dict, temp_dict)

        c.info[f"Block {idx + 1}"] = out_dict

    return c


@gf.cell
def xt_sin_function(
    bend_Si: ComponentSpec,
    bend_SiN2: ComponentSpec,
    gc_array: ComponentSpec,
    gc_array_dist: float,
    hv_ratios: list[float],
    n_bends: int,
    total_lengths: list[float],
    separation_structure: float,
    separation_rep: float,
    separation_xs: float,
    routing_straight: ComponentSpec,
    vt: ComponentSpec,
):
    """
    Create a prop loss function with double spiral from calculation
    attached to a vertical transition and than to a regular grating array.

    Args:
        bend_Si (ComponentSpec): Si bend used for Si routing.
        bend_SiN2 (ComponentSpec): SiN2 bend used for the Propagation Loss spiral.
        gc_array (ComponentSpec) : Grating array without loopback.
        gc_array_dist (float): Distance to be mantain from the gc_array in x direction.
        hv_ratios (list[float]): Horizontal vertical ratio to be passed to
            the Propagation Loss spiral.
        n_bends (int): Number of bend to be used for the Propagation Loss spiral.
        total_lengths (list[float]): Total length to be used for
            Propagation Loss spiral.
        separation_structure (float): distance between spirals x direction.
        separation_rep (float): internal distance between safe replica.
        separation_xs (float): interanl distance between adjacent replica.
        routing_straight (ComponentSpec): Si straight used for Si routing.
        vt (ComponentSpec): vertical transition to be used.
    """
    # Pre calculation
    xs_041 = gf.get_cross_section("strip", width=0.41)
    bend_radius = bend_Si["o2"].x - bend_Si["o1"].x
    rout_safe_dist = 5

    # Create a component
    c = gf.Component()

    # Add the first double spiral
    sp1 = c << ipr.double_spiral_from_calculation(
        bend=bend_SiN2,
        centralize=1,
        n_bends=n_bends,
        total_length=total_lengths[0],
        separation_rep=separation_rep,
        separation_xs=separation_xs,
        straight=straight_2000_anwg,
        hv_ratio=hv_ratios[0],
    )

    # Add the second double spiral
    sp2 = c << ipr.double_spiral_from_calculation(
        bend=bend_SiN2,
        n_bends=n_bends,
        centralize=1,
        total_length=total_lengths[1],
        separation_rep=separation_rep,
        separation_xs=separation_xs,
        straight=straight_2000_anwg,
        hv_ratio=hv_ratios[1],
    )

    # Add the third double spiral
    sp3 = c << ipr.double_spiral_from_calculation(
        bend=bend_SiN2,
        n_bends=n_bends,
        centralize=1,
        total_length=total_lengths[2],
        separation_rep=separation_rep,
        separation_xs=separation_xs,
        straight=straight_2000_anwg,
        hv_ratio=hv_ratios[2],
    )

    # Add the last double spiral
    sp4 = c << ipr.double_spiral_from_calculation(
        bend=bend_SiN2,
        n_bends=n_bends,
        centralize=1,
        total_length=total_lengths[3],
        separation_rep=separation_rep,
        separation_xs=separation_xs,
        straight=straight_2000_anwg,
        hv_ratio=hv_ratios[3],
    )

    # Mirror for better routing
    sp2.mirror_y()
    sp4.mirror_y()

    # Collect information
    port_sep = sp1["o2"].y - sp1["o1"].y
    sp1_inner_dict = sp1.cell.info["inner_spiral"]
    sp1_outer_dict = sp1.cell.info["outer_spiral"]
    sp2_inner_dict = sp2.cell.info["inner_spiral"]
    sp2_outer_dict = sp2.cell.info["outer_spiral"]
    sp3_inner_dict = sp3.cell.info["inner_spiral"]
    sp3_outer_dict = sp3.cell.info["outer_spiral"]
    sp4_inner_dict = sp4.cell.info["inner_spiral"]
    sp4_outer_dict = sp4.cell.info["outer_spiral"]
    routes_sp1_inner = []
    routes_sp1_outer = []
    routes_sp2_inner = []
    routes_sp2_outer = []
    routes_sp3_inner = []
    routes_sp3_outer = []
    routes_sp4_inner = []
    routes_sp4_outer = []

    # Place the grating coupler
    gc_array_left = c << gc_array
    gc_array_left.rotate(180)
    sp1.xmin = gc_array_left.xmax + gc_array_dist
    sp1.ymin = gc_array_left.ymin
    sp2.xmin = gc_array_left.xmax + gc_array_dist
    sp2.ymax = gc_array_left.ymax
    sp3.xmin = sp2.xmax + separation_structure
    sp3.y = sp2.y
    sp4.xmin = sp1.xmax + separation_structure
    sp4.y = sp1.y
    gc_array_right = c << gc_array
    gc_array_right.rotate(180)
    gc_array_right.xmin = max(sp4.xmax, sp3.xmax) + gc_array_dist

    # Add loopback to the grating coupler
    gf.routing.route_single(
        c,
        port1=gc_array_left["o0"],
        port2=gc_array_left["o9"],
        steps=[
            {"dx": bend_radius},
            {"dy": -2 * bend_radius - 5},
            {"dx": -2 * bend_radius - 5 - gc_array.xsize},
            {
                "dy": abs(gc_array_left["o9"].y - gc_array_left["o0"].y)
                + +2 * (2 * bend_radius + 5)
            },
            {"dx": 2 * bend_radius + 5 + gc_array.xsize},
            {"dy": -2 * bend_radius - 5},
        ],
        radius=bend_radius,
        layer=xs_041.layer,
        route_width=xs_041.width,
        bend=ipr.bend_euler_custom_width,
        auto_taper=False,
    )

    gf.routing.route_single(
        c,
        port1=gc_array_right["o0"],
        port2=gc_array_right["o9"],
        radius=bend_radius,
        layer=xs_041.layer,
        route_width=xs_041.width,
        bend=ipr.bend_euler_custom_width,
        auto_taper=False,
        start_straight_length=5,
    )

    # Place the gc_array going back
    port_out = []
    for idx in range(len(gc_array_right.ports) - 2):
        port = gc_array_right[f"o{idx + 1}"]
        # Going back is formed by bend straight bend straight
        bend1 = c << bend_Si
        bend1.mirror_y()
        bend1.connect("o1", port)
        strt1 = c << straight_410_swg(length=5)
        strt1.connect("o1", bend1["o2"])
        bend2 = c << bend_Si
        bend2.mirror_y()
        bend2.connect("o1", strt1["o2"])
        strt2 = c << straight_410_swg(length=gc_array.xsize)
        strt2.connect("o1", bend2["o2"])
        port_out.append(strt2["o2"])

    # Information used later for counting building blocks
    right_input_dicts = [
        ipr.measure_component(bend1.cell),
        ipr.measure_component(bend2.cell),
        ipr.measure_component(strt1.cell),
        ipr.measure_component(strt2.cell),
    ]

    # Add the vt to the first double spiral
    lenghts = [port_sep, port_sep * 2, port_sep, port_sep * 2]
    gc_ports = [
        gc_array_left["o1"],
        gc_array_left["o2"],
        gc_array_left["o3"],
        gc_array_left["o4"],
        gc_array_left["o8"],
        gc_array_left["o7"],
        gc_array_left["o6"],
        gc_array_left["o5"],
        port_out[5],
        port_out[4],
        port_out[7],
        port_out[6],
        port_out[2],
        port_out[3],
        port_out[0],
        port_out[1],
    ]

    for jdx, sp in enumerate([sp1, sp2, sp3, sp4]):
        for idx, port in enumerate(sp.ports):
            # total index
            tdx = idx + 4 * jdx

            # Place straight + bend + VT
            strt = c << straight_2000_anwg(length=lenghts[idx])
            strt.connect("o1", port)
            bend_ref = c << bend_SiN2
            if jdx == 1 or jdx == 3:
                bend_ref.mirror_y()
            bend_ref.connect("o1", strt["o2"])
            vt_ref = c << vt
            vt_ref.connect("o2", bend_ref["o2"])

            # Update dict
            temp_dicts = [
                ipr.measure_component(strt.cell),
                ipr.measure_component(bend_ref.cell),
                ipr.measure_component(vt_ref.cell),
            ]

            # Decide the start_straight_length depending on the case
            if jdx == 0 and idx == 2:
                steps = [
                    {"y": sp1.ymax + bend_radius},
                    {"x": gc_ports[tdx].x + bend_radius * 4},
                    {"y": gc_ports[tdx].y},
                ]
            elif jdx == 0 and idx == 3:
                steps = [
                    {"y": sp1.ymax + bend_radius + rout_safe_dist},
                    {"x": gc_ports[tdx].x + bend_radius * 2},
                    {"y": gc_ports[tdx].y},
                ]
            elif jdx == 1 and idx == 2:
                steps = [
                    {"y": sp2.ymin - bend_radius},
                    {"x": gc_ports[tdx].x + bend_radius * 4},
                    {"y": gc_ports[tdx].y},
                ]
            elif jdx == 1 and idx == 3:
                steps = [
                    {"y": sp2.ymin - bend_radius - rout_safe_dist},
                    {"x": gc_ports[tdx].x + bend_radius * 2},
                    {"y": gc_ports[tdx].y},
                ]
            elif jdx == 2 and idx == 0:
                steps = [
                    {"y": sp3.ymin - bend_radius},
                    {"x": gc_ports[tdx].x - bend_radius * 4},
                    {"y": gc_ports[tdx].y},
                ]
            elif jdx == 2 and idx == 1:
                steps = [
                    {"y": sp3.ymin - bend_radius - rout_safe_dist},
                    {"x": gc_ports[tdx].x - bend_radius * 2},
                    {"y": gc_ports[tdx].y},
                ]
            elif jdx == 3 and idx == 0:
                steps = [
                    {"y": sp4.ymax + bend_radius},
                    {"x": gc_ports[tdx].x - bend_radius * 4},
                    {"y": gc_ports[tdx].y},
                ]
            elif jdx == 3 and idx == 1:
                steps = [
                    {"y": sp4.ymax + bend_radius + rout_safe_dist},
                    {"x": gc_ports[tdx].x - bend_radius * 2},
                    {"y": gc_ports[tdx].y},
                ]
            else:
                steps = []

            # Connect to the grating
            route = gf.routing.route_single(
                c,
                port1=vt_ref["o1"],
                port2=gc_ports[tdx],
                cross_section=xs_041,
                straight=routing_straight,
                bend=bend_Si,
                auto_taper=False,
                steps=steps,
            )
            if jdx == 0 and idx < 2:
                for temp_dict in temp_dicts:
                    sp1_outer_dict = ipr.combine_component_dict(
                        sp1_outer_dict, temp_dict
                    )
                routes_sp1_outer.append(route)
            elif jdx == 0 and idx >= 2:
                for temp_dict in temp_dicts:
                    sp1_inner_dict = ipr.combine_component_dict(
                        sp1_inner_dict, temp_dict
                    )
                routes_sp1_inner.append(route)
            elif jdx == 1 and idx < 2:
                for temp_dict in temp_dicts:
                    sp2_outer_dict = ipr.combine_component_dict(
                        sp2_outer_dict, temp_dict
                    )
                routes_sp2_outer.append(route)
            elif jdx == 1 and idx >= 2:
                for temp_dict in temp_dicts:
                    sp2_inner_dict = ipr.combine_component_dict(
                        sp2_inner_dict, temp_dict
                    )
                routes_sp2_inner.append(route)
            elif jdx == 2 and idx < 2:
                for temp_dict in temp_dicts:
                    sp3_inner_dict = ipr.combine_component_dict(
                        sp3_inner_dict, temp_dict
                    )
                routes_sp3_inner.append(route)
            elif jdx == 2 and idx >= 2:
                for temp_dict in temp_dicts:
                    sp3_outer_dict = ipr.combine_component_dict(
                        sp3_outer_dict, temp_dict
                    )
                routes_sp3_outer.append(route)
            elif jdx == 3 and idx < 2:
                for temp_dict in temp_dicts:
                    sp4_inner_dict = ipr.combine_component_dict(
                        sp4_inner_dict, temp_dict
                    )
                routes_sp4_inner.append(route)
            elif jdx == 3 and idx >= 2:
                for temp_dict in temp_dicts:
                    sp4_outer_dict = ipr.combine_component_dict(
                        sp4_outer_dict, temp_dict
                    )
                routes_sp4_outer.append(route)

    # Update route information for left part
    for route in routes_sp1_inner:
        for inst in route.instances:
            temp_dict = ipr.measure_component(inst.cell, scale=1 / 1000)
            sp1_inner_dict = ipr.combine_component_dict(sp1_inner_dict, temp_dict)
    for route in routes_sp1_outer:
        for inst in route.instances:
            temp_dict = ipr.measure_component(inst.cell, scale=1 / 1000)
            sp1_outer_dict = ipr.combine_component_dict(sp1_outer_dict, temp_dict)
    for route in routes_sp2_inner:
        for inst in route.instances:
            temp_dict = ipr.measure_component(inst.cell, scale=1 / 1000)
            sp2_inner_dict = ipr.combine_component_dict(sp2_inner_dict, temp_dict)
    for route in routes_sp2_outer:
        for inst in route.instances:
            temp_dict = ipr.measure_component(inst.cell, scale=1 / 1000)
            sp2_outer_dict = ipr.combine_component_dict(sp2_outer_dict, temp_dict)

    # Update route information for right part
    for route in routes_sp3_inner:
        for inst in route.instances:
            temp_dict = ipr.measure_component(inst.cell, scale=1 / 1000)
            sp3_inner_dict = ipr.combine_component_dict(sp3_inner_dict, temp_dict)
        for right_input_dict in right_input_dicts:
            sp3_inner_dict = ipr.combine_component_dict(
                sp3_inner_dict, right_input_dict
            )
    for route in routes_sp3_outer:
        for inst in route.instances:
            temp_dict = ipr.measure_component(inst.cell, scale=1 / 1000)
            sp3_outer_dict = ipr.combine_component_dict(sp3_outer_dict, temp_dict)
        for right_input_dict in right_input_dicts:
            sp3_outer_dict = ipr.combine_component_dict(
                sp3_outer_dict, right_input_dict
            )
    for route in routes_sp4_inner:
        for inst in route.instances:
            temp_dict = ipr.measure_component(inst.cell, scale=1 / 1000)
            sp4_inner_dict = ipr.combine_component_dict(sp4_inner_dict, temp_dict)
        for right_input_dict in right_input_dicts:
            sp4_inner_dict = ipr.combine_component_dict(
                sp4_inner_dict, right_input_dict
            )
    for route in routes_sp4_outer:
        for inst in route.instances:
            temp_dict = ipr.measure_component(inst.cell, scale=1 / 1000)
            sp4_outer_dict = ipr.combine_component_dict(sp4_outer_dict, temp_dict)
        for right_input_dict in right_input_dicts:
            sp4_outer_dict = ipr.combine_component_dict(
                sp4_outer_dict, right_input_dict
            )

    # Read and save the final result
    c.info["Block 1"] = sp2_outer_dict
    c.info["Block 2"] = sp2_inner_dict
    c.info["Block 3"] = sp1_inner_dict
    c.info["Block 4"] = sp1_outer_dict
    c.info["Block 5"] = sp3_outer_dict
    c.info["Block 6"] = sp3_inner_dict
    c.info["Block 7"] = sp4_inner_dict
    c.info["Block 8"] = sp4_outer_dict

    return c


n_mmi = 0


@gf.cell
def mmi_splitter_il_extractor(
    absorber: ComponentSpec,
    bend: ComponentSpec,
    straight: ComponentSpec,
    gc_array: ComponentSpec,
    mmi_component: ComponentSpec,
):
    """
    Create a sequence of mmi test structure from which both IL
    and bar/cross can be extracted
    """

    # Obtain radius of the bend
    radius = bend["o2"].y - bend["o1"].y

    # Distance between gc array - default is 127 um
    gc_port_distance = gc_array["o1"].y - gc_array["o2"].y

    # Distance between MMI ports
    mmi_port_distance = mmi_component["o2"].y - mmi_component["o1"].y

    # Distance between different MMI
    mmi_to_mmi_length = gc_port_distance / 2 - 2 * radius - mmi_port_distance

    # Additional horizontal length added to the mmi
    random_avg = 1
    random_var = 0.141
    hor_length = absorber.xsize - random_avg
    assert mmi_to_mmi_length >= 0, "Please increase mmi distance."

    def mmi_abs_strt(mmi_idx, ports_abs, ports_strt, ports_void=None):
        c_int = gf.Component(f"mmi_{mmi_idx}")

        # Place the mmi
        mmi_ref = c_int << mmi_component

        # Place the absorber
        for port in ports_abs:
            abs_ref = c_int << absorber
            if port == "o1" or port == "o3":
                abs_ref.mirror_y()
            abs_ref.connect("o1", mmi_ref[port])

        # Place the straight
        for port in ports_strt:
            strt = c_int << straight(length=hor_length)
            strt.connect("o1", mmi_ref[port])
            c_int.add_port(port, port=strt["o2"])

        # Place normal ports
        if ports_void is not None:
            for port in ports_void:
                c_int.add_port(port, port=mmi_ref[port])

        return c_int

    def compensator_odd(port1, port2, nbends, total_length, n_comp):
        c_int = gf.Component(f"compensator_{n_comp}")

        port_prev = port1

        # Distance between port that can be used by the compensator
        dx_distance = abs(port1.x - port2.x) - radius * (nbends)

        # Useful length is total length minus the distance between ports
        length_hor_usef = total_length - dx_distance

        # Calculate length in each section
        length_per_bend = round(
            (length_hor_usef - (nbends - 4) * radius) / (nbends - 2), 3
        )
        ver_var = max(length_per_bend * 2 + radius * 2 - gc_port_distance, 0)

        # Place bend straight bend for compensator
        for jdx in range(nbends // 2):
            # Bend
            bend_ref = c_int << bend
            if jdx % 2 == 1:
                bend_ref.mirror_y()
            bend_ref.connect("o1", port_prev)

            if jdx == 0:
                c_int.add_port("o1", port=bend_ref["o1"])

            # Straight
            if jdx == 0:
                length = length_per_bend + ver_var
            elif jdx == nbends // 2 - 1:
                length = length_per_bend - ver_var
            else:
                length = length_per_bend * 2 + radius * 2
            strt = c_int << straight(length=length)
            strt.connect("o1", bend_ref["o2"])

            # Bend
            bend_ref = c_int << bend
            if jdx % 2 == 0:
                bend_ref.mirror_y()
            bend_ref.connect("o1", strt["o2"])
            port_prev = bend_ref["o2"]

        # Create the final length towards the gc array
        strt = c_int << straight(length=dx_distance)
        strt.connect("o1", bend_ref["o2"])
        strt.connect("o2", port2)

        c_int.add_port("o2", port=strt["o2"])
        return c_int

    def compensator_even(port1, port2, nbends, total_length, n_comp):
        c_int = gf.Component(f"compensator_{n_comp}")

        port_prev = port1
        dx_distance = abs(port1.x - port2.x) - radius * (nbends)
        length_hor_usef = total_length - dx_distance
        length_per_bend = length_hor_usef / nbends * 2

        # Place bend straight bend for compensator
        for jdx in range(nbends // 2):
            # Bend
            bend_ref = c_int << bend
            if jdx % 2 == 0:
                bend_ref.mirror_y()
            bend_ref.connect("o1", port_prev)

            if jdx == 0:
                c_int.add_port("o1", port=bend_ref["o1"])

            # Straight
            strt = c_int << straight(length=length_per_bend)
            strt.connect("o1", bend_ref["o2"])

            # Bend
            bend_ref = c_int << bend
            if jdx % 2 == 1:
                bend_ref.mirror_y()
            bend_ref.connect("o1", strt["o2"])
            port_prev = bend_ref["o2"]

        # Create the final length towards the gc array
        strt = c_int << straight(length=dx_distance)
        strt.connect("o1", bend_ref["o2"])
        strt.connect("o2", port2)

        c_int.add_port("o2", port=strt["o2"])
        return c_int

    # Generate component
    c = gf.Component()

    # Place GC
    gc_ref = c << gc_array
    gc_ref.rotate(180)

    global n_mmi
    mmi_number = 9

    # Place initial mmi
    mmi_start_dy = 105

    mmi_start = c << mmi_abs_strt(
        ports_abs=["o2"], ports_strt=["o1", "o4"], ports_void=["o3"], mmi_idx=n_mmi
    )
    mmi_start.movex(mmi_start["o3"].x, gc_ref["o1"].x + radius * 2)
    mmi_start.movey(mmi_start["o3"].y, gc_ref["o1"].y - mmi_start_dy)

    # Distance between consecutive MMI
    mmi_dy = (gc_ref["o2"].y - gc_ref["o1"].y) / 2

    # Starting position of mmi
    mmi_ystart = (gc_ref["o2"].y + gc_ref["o1"].y) / 2

    # Create the MMI - cross
    mmi_top_input_ports = []
    mmi_top_output_ports = []
    mmi_top_aux_ports = []
    for idx in range(mmi_number - 1):
        # Define the mmi port
        mmi_top_input_port = "o1" if idx % 2 == 0 else "o2"
        mmi_top_output_port = "o3" if idx % 2 == 0 else "o4"
        mmi_top_aux1_port = "o2" if idx % 2 == 0 else "o1"
        mmi_top_aux2_port = "o4" if idx % 2 == 0 else "o3"

        # Create the mmi - rotate depending on the parity
        if idx % 2 == 0:
            mmi_top = c << mmi_abs_strt(
                ports_abs=[mmi_top_aux1_port, mmi_top_aux2_port],
                ports_strt=[mmi_top_input_port, mmi_top_output_port],
                mmi_idx=idx + 1 + n_mmi,
            )
            mmi_top.movex(
                mmi_top[mmi_top_input_port].x,
                gc_ref["o3"].x + radius * (mmi_number - 2) * 2,
            )
        else:
            mmi_top = c << mmi_abs_strt(
                ports_abs=[mmi_top_aux1_port],
                ports_strt=[mmi_top_input_port, mmi_top_output_port, mmi_top_aux2_port],
                mmi_idx=idx + 1 + n_mmi,
            )
            mmi_top.rotate(180)
            mmi_top.movex(
                mmi_top[mmi_top_output_port].x,
                gc_ref["o3"].x + radius * (mmi_number - 2) * 2,
            )

        # Position the MMIs
        if idx != mmi_number - 2:
            mmi_top.movey(mmi_top[mmi_top_input_port].y, mmi_ystart + idx * mmi_dy)
        else:
            mmi_top.movey(
                (mmi_top["o3"].y + mmi_top["o4"].y) / 2, mmi_ystart + (idx + 1) * mmi_dy
            )

        # Collect the MMIs ports
        mmi_top_input_ports.append(mmi_top[mmi_top_output_port])
        mmi_top_output_ports.append(mmi_top[mmi_top_input_port])
        if idx % 2 == 1 and idx != mmi_number - 2:
            mmi_top_aux_ports.append(mmi_top[mmi_top_aux2_port])

    # Create MMI to MMI connection
    random_lengths = ipr.random_number_array(
        mean=random_avg + random_var, n_elements=mmi_number - 2, variation=random_var
    )
    for idx in range(mmi_number - 2):
        # Initial random length
        strt = c << straight(length=random_lengths[idx])
        strt.connect("o1", mmi_top_input_ports[idx])

        # Bend -> strt -> bend
        bend_ref = c << bend
        if idx % 2 == 1:
            bend_ref.mirror_y()
        bend_ref.connect("o1", strt["o2"])

        dy = mmi_top_output_ports[idx + 1].y - mmi_top_input_ports[idx].y - 2 * radius
        strt = c << straight(length=dy)
        strt.connect("o1", bend_ref["o2"])

        bend_ref = c << bend
        if idx % 2 == 1:
            bend_ref.mirror_y()
        bend_ref.connect("o1", strt["o2"])

        # Final random length
        strt = c << straight(length=random_lengths[idx])
        strt.connect("o1", bend_ref["o2"])

        strt.connect("o2", mmi_top_output_ports[idx + 1])
    final_top_length = dy

    # Create connection 1 of the top final MMI
    bend_ref = c << bend
    bend_ref.mirror_y()
    bend_ref.connect("o1", mmi_top["o4"])

    dy_top = gc_ref["o6"].y - mmi_top["o4"].y - 2 * radius
    strt = c << straight(length=dy_top)
    strt.connect("o1", bend_ref["o2"])

    bend_ref = c << bend
    bend_ref.connect("o1", strt["o2"])

    dx_top = mmi_top["o4"].x - gc_ref["o6"].x - 2 * radius
    strt = c << straight(length=dx_top)
    strt.connect("o1", bend_ref["o2"])
    strt.connect("o2", gc_ref["o6"])

    # Create connection 2 of the top final MMI
    bend_ref = c << bend
    bend_ref.connect("o1", mmi_top["o3"])

    dy_top = mmi_top["o3"].y - gc_ref["o5"].y - 2 * radius
    strt = c << straight(length=dy_top)
    strt.connect("o1", bend_ref["o2"])

    bend_ref = c << bend
    bend_ref.mirror_y()
    bend_ref.connect("o1", strt["o2"])

    dx_top = mmi_top["o3"].x - gc_ref["o5"].x - 2 * radius
    strt = c << straight(length=dx_top)
    strt.connect("o1", bend_ref["o2"])
    strt.connect("o2", gc_ref["o5"])

    # Compensation part (mmi stair + hor gc-mmi distance + ver gc-mmi distance)
    comp_length_final = dy_top + dx_top + final_top_length

    for idx, port in enumerate(reversed(mmi_top_aux_ports)):
        total_length = (
            comp_length_final
            + mmi_to_mmi_length * (idx * 2 + 1)
            + hor_length * (idx + 1) * 4
        )

        compensator = c << compensator_odd(
            port,
            gc_ref[f"o{4 - idx}"],
            nbends=idx * 4 + 6,
            total_length=total_length,
            n_comp=idx + n_mmi,
        )
        compensator.connect("o2", port)
    total_length_top = total_length + 3 * hor_length + mmi_to_mmi_length

    # Create the MMI - bar
    mmi_bot_input_ports = []
    mmi_bot_output_ports = []

    for idx in range(mmi_number - 1):
        # Define the mmi port
        mmi_bot_input_port = "o1"
        mmi_bot_output_port = "o4"
        mmi_bot_aux1_port = "o2"
        mmi_bot_aux2_port = "o3"

        # Create the mmi - rotate depending on the parity
        if idx != mmi_number - 2:
            mmi_bot = c << mmi_abs_strt(
                ports_abs=[mmi_bot_aux1_port, mmi_bot_aux2_port],
                ports_strt=[mmi_bot_input_port, mmi_bot_output_port],
                mmi_idx=idx + mmi_number + n_mmi,
            )
        else:
            mmi_bot = c << mmi_abs_strt(
                ports_abs=[mmi_bot_aux1_port],
                ports_strt=[mmi_bot_input_port, mmi_bot_output_port, mmi_bot_aux2_port],
                mmi_idx=idx + mmi_number + n_mmi,
            )

        # Position the MMIs
        if idx % 2 == 0:
            mmi_bot.movex(
                mmi_bot[mmi_bot_input_port].x, mmi_top_input_ports[idx].x + radius * 4
            )
        else:
            mmi_bot.rotate(180)
            mmi_bot.movex(
                mmi_bot[mmi_bot_output_port].x, mmi_top_output_ports[idx].x + radius * 4
            )

        if idx != mmi_number - 2:
            mmi_bot.movey(
                mmi_bot[mmi_bot_input_port].y,
                mmi_top_input_ports[idx].y - mmi_port_distance,
            )
        else:
            mmi_bot.movey(
                (mmi_bot["o3"].y + mmi_bot["o4"].y) / 2, mmi_ystart + (idx + 5) * mmi_dy
            )

        # Collect the MMIs
        mmi_bot_input_ports.append(mmi_bot[mmi_bot_output_port])
        mmi_bot_output_ports.append(mmi_bot[mmi_bot_input_port])

    # Create MMI to MMI connection
    for idx in range(mmi_number - 2):
        # Initial random length
        strt = c << straight(length=random_lengths[idx])
        strt.connect("o1", mmi_bot_input_ports[idx])

        # Bend -> strt -> bend
        bend_ref = c << bend
        if idx % 2 == 1:
            bend_ref.mirror_y()
        bend_ref.connect("o1", strt["o2"])

        dy = mmi_bot_output_ports[idx + 1].y - mmi_bot_input_ports[idx].y - 2 * radius
        strt = c << straight(length=dy)
        strt.connect("o1", bend_ref["o2"])

        bend_ref = c << bend
        if idx % 2 == 1:
            bend_ref.mirror_y()
        bend_ref.connect("o1", strt["o2"])

        # Final random length
        strt = c << straight(length=random_lengths[idx])
        strt.connect("o1", bend_ref["o2"])

        strt.connect("o2", mmi_bot_output_ports[idx + 1])
    final_length = dy

    # Create stairs for the initial mmi
    stairs_port_input = mmi_bot_output_ports[0]
    stairs_sep = 0.5
    for idx in range(8):
        bend_ref = c << bend
        if idx % 2 == 1:
            bend_ref.mirror_y()
        bend_ref.connect("o1", stairs_port_input)

        strt = c << straight(length=stairs_sep)
        strt.connect("o1", bend_ref["o2"])

        stairs_port_input = strt["o2"]

    bend_ref = c << bend
    bend_ref.connect("o1", stairs_port_input)

    dx_stairs = bend_ref["o2"].x - mmi_start["o4"].x - radius
    dy_stairs = bend_ref["o2"].y - mmi_start["o4"].y - radius

    strt = c << straight(length=dy_stairs)
    strt.connect("o1", bend_ref["o2"])

    bend_ref = c << bend
    bend_ref.mirror_y()
    bend_ref.connect("o1", strt["o2"])

    strt = c << straight(length=dx_stairs)
    strt.connect("o1", bend_ref["o2"])

    # Create stairs 1 for the final mmi
    bend_ref = c << bend
    bend_ref.connect("o1", mmi_bot["o3"])

    dy = mmi_bot["o3"].y - gc_ref["o7"].y - 2 * radius
    strt = c << straight(length=dy)
    strt.connect("o1", bend_ref["o2"])

    bend_ref = c << bend
    bend_ref.mirror_y()
    bend_ref.connect("o1", strt["o2"])

    dx = mmi_bot["o3"].x - gc_ref["o7"].x - 2 * radius
    strt = c << straight(length=dx)
    strt.connect("o1", bend_ref["o2"])
    strt.connect("o2", gc_ref["o7"])

    # Create stairs 2 for the final mmi
    bend_ref = c << bend
    bend_ref.mirror_y()
    bend_ref.connect("o1", mmi_bot["o4"])

    dy = gc_ref["o8"].y - mmi_bot["o4"].y - 2 * radius
    strt = c << straight(length=dy)
    strt.connect("o1", bend_ref["o2"])

    bend_ref = c << bend
    bend_ref.connect("o1", strt["o2"])

    dx = mmi_bot["o4"].x - gc_ref["o8"].x - 2 * radius
    strt = c << straight(length=dx)
    strt.connect("o1", bend_ref["o2"])
    strt.connect("o2", gc_ref["o8"])

    # Calculate total length of bottom part
    comp_length_final = dy + dx + final_length
    total_length_bot = (
        comp_length_final
        + (mmi_to_mmi_length + mmi_port_distance) * (mmi_number - 3)
        + hor_length * ((mmi_number - 2) * 2 + 1)
    )

    diff = total_length_bot - total_length_top

    # Compensate also for the difference in input position of the mmi
    bot_link = dx_stairs + dy_stairs + stairs_sep * 8 + hor_length * 2
    top_link_y = mmi_top_output_ports[0].y - mmi_start["o3"].y - 2 * radius
    diff = diff + bot_link - top_link_y - hor_length

    # Use the difference to compensate top part
    bend_ref = c << bend
    bend_ref.connect("o1", mmi_start["o3"])

    strt = c << straight(length=top_link_y)
    strt.connect("o1", bend_ref["o2"])

    bend_ref = c << bend
    bend_ref.mirror_y()
    bend_ref.connect("o1", strt["o2"])

    comp_strt = c << compensator_even(
        port1=mmi_top_output_ports[0],
        port2=bend_ref["o2"],
        nbends=8,
        total_length=diff,
        n_comp=mmi_number + n_mmi,
    )
    comp_strt.connect("o1", bend_ref["o2"])

    # Connect the input mmi
    bend_ref = c << bend
    bend_ref.mirror_y()
    bend_ref.connect("o1", gc_ref["o1"])
    strt = c << straight(length=mmi_start_dy - radius * 4)
    strt.connect("o1", bend_ref["o2"])
    bend_ref = c << bend
    bend_ref.mirror_y()
    bend_ref.connect("o1", strt["o2"])
    dx1 = mmi_component.xsize
    strt = c << straight(length=dx1)
    strt.connect("o1", bend_ref["o2"])
    bend_ref = c << bend
    bend_ref.connect("o1", strt["o2"])
    dx2 = mmi_port_distance
    strt = c << straight(length=dx2)
    strt.connect("o1", bend_ref["o2"])
    bend_ref = c << bend
    bend_ref.connect("o1", strt["o2"])
    dx3 = mmi_start["o1"].x - bend_ref["o2"].x
    strt = c << straight(length=dx3)
    strt.connect("o1", bend_ref["o2"])

    # Json Generation Information = Bend
    all_blocks_dict = {}
    bend_dict = ipr.measure_component(bend_ref.cell, scale=1)
    key = list(bend_dict.keys())[0]
    bend_dict[key] *= 30
    all_blocks_dict = ipr.combine_component_dict(all_blocks_dict, bend_dict)

    # Json Generation Information = Straight
    strt_dict = ipr.measure_component(straight(length=1), scale=1)
    key = list(strt_dict.keys())[0]
    total_length = (
        total_length_bot
        + bot_link
        + mmi_start_dy
        - radius * 4
        + dx1
        + dx2
        + dx3
        + hor_length
    )
    strt_dict[key] *= total_length
    all_blocks_dict = ipr.combine_component_dict(all_blocks_dict, strt_dict)

    # Json Generation Information = MMI
    mmi_dict = ipr.measure_component(mmi_component, scale=1)
    key = list(mmi_dict.keys())[0]
    n_mmi += mmi_number * 2 - 1

    # Populate the info
    for idx in range(8):
        mmi_dict[key] = min(3 + idx * 2, mmi_number)
        block_dict = ipr.combine_component_dict(all_blocks_dict, mmi_dict)

        c.info[f"Block {idx}"] = block_dict
    c.mirror_y()
    return c


@gf.cell
def sem(
    gap: float = 0.0,
    layer: LayerSpec = LAYER.swg,
    length: float = 100,
    length_additional: float = 100,
    n: int = 11,
    width: float = 0.14,
) -> gf.Component:
    """
    Creates a SEM target structure consisting of `n` vertically stacked straight
    waveguides. All waveguides have the same width and are separated by
    `width + gap_extra`. The central waveguide (middle one) is made longer
    by `length_additional` to serve as a visual reference for SEM inspection.

    Args:
        gap_extra (float): Additional spacing added between adjacent waveguides (µm).
            Defaults to 0.0.
        layer (LayerSpec): Layer specification for the waveguides.
            Defaults to LAYER.swg.
        length (float): Length of the standard straight waveguides (µm).
            Defaults to 500.
        length_additional (float): Extra length added to the middle waveguide (µm).
            Defaults to 100.
        n (int): Number of waveguides. Adjusted to be odd if an even value is given.
            Defaults to 49.
        width (float): Width of each waveguide (µm).
            Defaults to 0.14.
    """

    # Ensure n is odd
    if n % 2 == 0:
        n += 1

    # Components initialization
    c = gf.Component()
    xs = gf.get_cross_section("strip", width=width, layer=layer)
    waveguides = []

    # Create and place the first waveguide
    wg0 = c << gf.components.straight(length=length, cross_section=xs)
    waveguides.append(wg0)

    # Vertical spacing between waveguides
    spacing = gap

    # Add the remaining waveguides
    for i in range(1, n):
        # Understand if we are at the middle
        is_middle = i == n // 2

        # Place a waveguide
        wg_length = length + length_additional if is_middle else length
        wg = c << gf.components.straight(length=wg_length, cross_section=xs)

        # Position the new waveguide below the previous one
        wg.ymax = waveguides[-1].ymin - spacing
        waveguides.append(wg)

    return c


@gf.cell
def sem_array(structure_index: int = 0):
    """
    Function used for placing sequence of sem of different material

    Args:
    structure_index(int): value used for text.
        Defaults to 0.
    """
    c = gf.Component()

    # ==========================================================
    # SEM configuration list
    # ==========================================================
    sem_specs = [
        # widths,               gap,    layers,                                 titles
        # Bool difference operation, Bridge
        ([0.410], 0.20, [LAYER.swg], f"{structure_index}.1: SI 0.41 G.2", False, False),
        ([0.410], 0.30, [LAYER.swg], f"{structure_index}.2: SI 0.41 G.3", False, False),
        ([0.930], 0.30, [LAYER.swg], f"{structure_index}.3: SI 0.93 G.3", False, False),
        ([1.500], 0.30, [LAYER.swg], f"{structure_index}.4: SI 1.50 G.3", False, False),
        (
            [0.650, 1.92],
            1.87,
            [LAYER.swg, LAYER.rwg],
            f"{structure_index}.5: SISH 0.65 G.6",
            False,
            False,
        ),
        (
            [0.268, 0.35],
            0.682,
            [LAYER.swg, LAYER.rwg],
            f"{structure_index}.6: SISH 0.268 G.6",
            False,
            False,
        ),
        (
            [0.410, 20.00, 21.00],
            0.30,
            [LAYER.swg, LAYER.rwg, LAYER.gwg],
            f"{structure_index}.7: SISH 0.41 G.3",
            False,
            False,
        ),
        (
            [0.700],
            0.30,
            [LAYER.nwg],
            f"{structure_index}.8: SIN 0.70 G.3",
            False,
            False,
        ),
        (
            [1.000],
            0.20,
            [LAYER.nwg],
            f"{structure_index}.9: SIN 1.00 G.2",
            False,
            False,
        ),
        (
            [1.000],
            0.30,
            [LAYER.nwg],
            f"{structure_index}.10: SIN 1.00 G.3",
            False,
            False,
        ),
        (
            [5.000, 5.40, 1.00],
            0.00,
            [LAYER.nwg, LAYER.rwn, LAYER.nwg],
            f"{structure_index}.11: SINSH 1.00 G4",
            True,
            False,
        ),
        (
            [0.700],
            0.35,
            [LAYER.anwg],
            f"{structure_index}.12: A 0.70 G.35",
            False,
            False,
        ),
        (
            [1.000],
            0.25,
            [LAYER.anwg],
            f"{structure_index}.13: A 1.00 G.25",
            False,
            False,
        ),
        (
            [1.000],
            0.35,
            [LAYER.anwg],
            f"{structure_index}.14: A 1.00 G.35",
            False,
            False,
        ),
        (
            [2.000],
            0.35,
            [LAYER.anwg],
            f"{structure_index}.15: A 2.00 G.35",
            False,
            False,
        ),
        (
            [5.500, 5.90, 1.50],
            0.00,
            [LAYER.anwg, LAYER.ranwg, LAYER.anwg],
            f"{structure_index}.16: ASH 1.50 G4",
            True,
            False,
        ),
        (
            [0.150, 0.41, 20.00],
            0.56,
            [LAYER.nwg, LAYER.swg],
            f"{structure_index}.17: SISIN 0.41 G.3",
            False,
            False,
        ),
        (
            [0.310, 1.30],
            1.34,
            [LAYER.nwg, LAYER.anwg],
            f"{structure_index}.18: SINA 0.31 G.35",
            False,
            False,
        ),
        (
            [0.72, 1.000],
            0.58,
            [LAYER.anwg, LAYER.nwg],
            f"{structure_index}.19: SINA 1.00 G.3",
            False,
            False,
        ),
    ]

    # ==========================================================
    # Layout configuration
    # ==========================================================
    col_count = 1  # two columns
    x_spacing = 620  # horizontal distance between columns
    y_spacing = 60  # vertical spacing between rows
    label_text_size = 21  # font size

    # Standardized label box width + height
    label_width = 305  # fixed width for all labels
    label_height = 40  # fixed height (text will be centered)
    bridge_width = 2

    # Cross section for marking
    xs_marking = gf.cross_section.strip(width=bridge_width, layer=LAYER.m_wgcnct)

    for idx, (widths, gap, layers, label, bool_diff, bridge) in enumerate(sem_specs):
        # Determine column and row
        row = idx // col_count
        col = idx % col_count

        x_offset = col * x_spacing
        y_offset = -row * y_spacing

        # ==========================================================
        # Place SEM cell (centered vertically)
        # ==========================================================
        sm_max_height = 0

        # Regular sem structure
        if not bool_diff:
            for width, layer in zip(widths[::-1], layers[::-1]):
                delta_gap = abs(widths[0] - width)

                sm = c << sem(
                    width=width,
                    length=delta_gap + 100,
                    layer=layer,
                    gap=gap - delta_gap,
                )

                sm.movex(delta_gap / 2, x_offset)
                sm.movey(sm.y, y_offset)

                if sm.ysize > sm_max_height:
                    sm_max_height = sm.ysize

        # Difference between sem structures
        else:
            # Unchanged layer 1
            sm1 = sem(width=widths[0], length=100, layer=layers[0], gap=gap)

            # Unchanged layer 2
            delta_gap = abs(widths[1] - widths[0])
            sm2 = sem(
                width=widths[1],
                length=100 + delta_gap,
                layer=layers[1],
                gap=gap - delta_gap,
            )
            sm2 = sm2.copy()
            sm2.movex(delta_gap / 2, x_offset)

            # Layer boolean operation
            delta_gap = abs(widths[2] - widths[0])
            sm3 = sem(
                width=widths[2],
                length=100 - delta_gap,
                layer=layers[2],
                gap=gap + delta_gap,
            )
            sm3 = sm3.copy()
            sm3.movex(-delta_gap / 2, x_offset)

            # Perform Boolean difference
            sm = c << gf.boolean(
                A=sm2,
                B=sm3,
                operation="A-B",
                layer=layers[1],
                layer1=layers[1],
                layer2=layers[2],
            )

            # Move unchanged layers
            sm1 = c << sm1
            sm1.movex(delta_gap / 2, x_offset)
            sm1.movey(sm1.y, y_offset)

            # Move the result of the boolean operation
            sm.movex(delta_gap / 2, x_offset)
            sm.movey(sm.y, y_offset)

            sm_max_height = sm.ysize

        # If width is too small, we need to add a bridge
        if bridge:
            sm_height = sm_max_height
            delta_height = (sm_height - sm.ysize) / 2

            for idx in range(4):
                # Place bridge
                bridge_inst = c << gf.c.rectangle(
                    size=(bridge_width, sm_height), layer=layers[0]
                )

                bridge_inst.xmin = sm.xmin + 0.5 + 98 * (idx) / 3
                bridge_inst.ymin = sm.ymin - delta_height

                # Place transition layer on both ends to avoid error
                m1 = c << gf.components.straight(length=1, cross_section=xs_marking)
                m1.rotate(90)
                m1.x = bridge_inst.x
                m1.y = bridge_inst.ymax

                m2 = c << gf.components.straight(length=1, cross_section=xs_marking)
                m2.rotate(90)
                m2.x = bridge_inst.x
                m2.y = bridge_inst.ymin

        # ==========================================================
        # Create standardized rectangle background FIRST
        # ==========================================================
        rec = c << gf.c.rectangle(size=(label_width, label_height), layer=(118, 40))

        # Place rectangle at fixed offset from SEM
        rec.xmin = x_offset + 70 + label_width / 2
        rec.y = y_offset

        # ==========================================================
        # Create text INSIDE the rectangle
        # ==========================================================
        txt = c << ipr.text(label, size=label_text_size, layer=LAYER.metal3)

        # Center text inside rectangle
        txt.move((rec.center[0] - txt.center[0], rec.center[1] - txt.center[1]))

    return c


@gf.cell
def taper_doe(
    bend: ComponentSpec,
    gc_array: ComponentSpec,
    straight: ComponentSpec,
    taper_start: ComponentSpec,
    taper_list: list[ComponentSpec],
    vertical_transition=ComponentSpec,
):
    """
    Create a test structure to detect the maximum taper length before fabrication problem.

    Args:
        bend[ComponentSpec]: silicon 90 bend to be used in curves.
        gc_array[ComponentSpec]: grating coupler to be used. Normali GC with 0.41 silicon input.
        straight[ComponentSpec]: straight to be used between taper_list output.
        taper_start[ComponentSpec]: taper to be used between vt out and taper_list input.
        taper_list[list[ComponentSpec]]: list of taper to be used.
        vertical_transition[ComponentSpec]: vertical transition to be used.
    """

    # Initialize the dictionary with cutback info
    block1_dict = {}
    block2_dict = {}
    block3_dict = {}
    block4_dict = {}

    # Generate component
    c = gf.Component()

    # Place the gc
    gc_ref = c << gc_array
    gc_ref.rotate(180)

    # Geometrical parameter definition
    radius = bend["o2"].x - bend["o1"].x
    Dx = 25
    Dy = 45
    for idx, taper in enumerate(taper_list):
        # Place a straight to be reached
        xs = gf.get_cross_section("strip", width=0.41)
        strt1 = c << straight_410_swg(length=1)

        if idx < 2:
            strt1.rotate(90)
            gc = gc_ref[f"o{2 * idx + 1}"]
            strt1.x = gc.x + radius * (9 - 4 * idx)
            strt1.y = gc.y + radius * 2
        else:
            strt1.rotate(-90)
            gc = gc_ref[f"o{2 * idx + 2}"]
            strt1.x = gc.x - Dx - radius * (4 * idx - 1)
            strt1.y = gc.y + Dy

        route1 = gf.routing.route_single(
            c, strt1["o1"], gc, cross_section=xs, bend=bend
        )

        # Place a vt
        vt1 = c << vertical_transition
        vt1.connect("o1", strt1["o2"])

        # Place a taper start
        tp_start = c << taper_start
        tp_start.connect("o1", vt1["o2"])

        # Place a taper from list
        tp1 = c << taper
        tp1.connect("o1", tp_start["o2"])

        # Place a small straight
        strt2 = c << straight(length=1)
        strt2.connect("o1", tp1["o2"])

        # Place taper inverse from list
        tp2 = c << taper
        tp2.connect("o2", strt2["o2"])

        # Place a taper start inverse
        tp_end = c << taper_start
        tp_end.connect("o2", tp2["o1"])

        # Place a vt inverse
        vt2 = c << vertical_transition
        vt2.connect("o2", tp_end["o1"])

        strt2 = c << straight_410_swg(length=1)

        if idx < 2:
            gc = gc_ref[f"o{2 * idx + 2}"]
            strt2.x = gc.x + radius
            strt2.y = gc.y
        else:
            strt2.rotate(180)
            gc = gc_ref[f"o{2 * idx + 1}"]
            strt2.x = gc.x - Dx - radius * (4 * idx - 5)
            strt2.y = gc.y + Dy - radius

        # Connect to GC
        route2 = gf.routing.route_single(
            c, vt2["o1"], strt2["o2"], cross_section=xs, bend=bend
        )

        route3 = gf.routing.route_single(
            c, gc, strt2["o1"], cross_section=xs, bend=bend
        )

        # Update the dictionary with routing
        for route in [route1, route2, route3]:
            for inst in route.instances:
                temp_dict = ipr.measure_component(inst.cell, scale=1 / 1000)
                if idx == 0:
                    block1_dict = ipr.combine_component_dict(block1_dict, temp_dict)
                elif idx == 1:
                    block2_dict = ipr.combine_component_dict(block2_dict, temp_dict)
                elif idx == 2:
                    block3_dict = ipr.combine_component_dict(block3_dict, temp_dict)
                else:
                    block4_dict = ipr.combine_component_dict(block4_dict, temp_dict)

        # Update the dictionary with components
        for comp in [strt1, strt2, vt1, vt2, tp_start, tp_end, tp1, tp2]:
            temp_dict = ipr.measure_component(comp.cell)
            if idx == 0:
                block1_dict = ipr.combine_component_dict(block1_dict, temp_dict)
            elif idx == 1:
                block2_dict = ipr.combine_component_dict(block2_dict, temp_dict)
            elif idx == 2:
                block3_dict = ipr.combine_component_dict(block3_dict, temp_dict)
            else:
                block4_dict = ipr.combine_component_dict(block4_dict, temp_dict)

    c.info["Block 4"] = block1_dict
    c.info["Block 3"] = block2_dict
    c.info["Block 2"] = block3_dict
    c.info["Block 1"] = block4_dict

    return c
