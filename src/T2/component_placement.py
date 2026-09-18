import json

import gdsfactory as gf
import iprlayout_tower as ipr
import numpy as np
from iprlayout_tower import LAYER

from T2.benes import dilated_benes
from T2.pdk import (
    change_port,
    clothoid,  # noqa: F401
    diode_guard_ring,  # noqa: F401
    diode_linear,
    ec_with_vt,
    from_clothoid_to_straights,
    json_settings,
    measure_structure,
    pbs_with_taper,  # noqa: F401
    psr_adiabatic_taper_wabsorber,  # noqa: F401
    puc_array_test_structure,
    puc_with_diode,
    straight_410_swg,
    straight_700_anwg,
    straight_2000_anwg,
    straight_with_slots,
    tlm_linear,
    tower_pd_eo,
    tps_410_swg_930_swg_lim,
    triangle_visual,
    v7a_PUC_from_gds,
    via_23_with_metal_taper,
    via_metal2_metal3,
    via_to_metal2,  # noqa: F401
)
from T2.pdk_ec import (
    ec_sin2_strip_MAIN,  # noqa: F401
    ec_sin2_strip_MAIN_angled,  # noqa: F401
    ec_sin2_strip_single,  # noqa: F401
    ec_sin2_strip_trident,  # noqa: F401
)


def component_placement(die: gf.Component) -> gf.Component:
    """
    This function places all components in the DIE
    """

    # Take the die component
    die = gf.get_component(die)
    die_edge_hor = 75
    die_edge_ver = 125

    # Activate the pdk
    pdk = ipr.get_pdk()
    pdk.activate()

    # Feature of the the die
    bbox_layer = (118, 40)
    die_height = die.ymax - die.ymin - 2 * die_edge_ver
    die_height_semi = die_height / 2
    die_ymax = die.ymax
    die_ymin = die.ymin
    die_xmax = die.xmax
    die_y_center = (die.ymax + die.ymin) / 2
    edge_margin_left = 3330
    edge_margin_right_top = 3465
    edge_margin_right_bot = 3465 + 85 / 2
    edge_margin_top = 75
    edge_margin_bot = 75
    structure_to_structure_margin = 40
    min_gc_gc_distance = 200
    text_size = 25
    text_size_puc = 21

    ##########################
    # CROSS SECTIONS CONTROL #
    ##########################
    xs_swg = gf.get_cross_section("strip")
    xs_swg_410 = gf.get_cross_section("strip", width=0.41)
    xs_anwg_1784 = gf.get_cross_section("nitride2", width=1.784)
    xs_anwg_2000 = gf.get_cross_section("nitride2", width=2.00)
    swg = gf.partial(ipr.fast_straight, cross_section=xs_swg)

    xs_metal1_narrow = gf.get_cross_section("metal1", width=7)
    xs_metal1 = gf.get_cross_section("metal1", width=10)
    xs_metal1_wide = gf.get_cross_section("metal1", width=11)
    xs_metal2 = gf.get_cross_section("metal2", width=11)
    xs_metal2_wides = [
        gf.get_cross_section("metal2", width=30),
        gf.get_cross_section("metal2", width=34),
        gf.get_cross_section("metal2", width=38),
        gf.get_cross_section("metal2", width=42),
    ]
    xs_metal3_narrow = gf.get_cross_section("metal3", width=7)
    xs_metal3_narrow2 = gf.get_cross_section("metal3", width=10)
    xs_metal3 = gf.get_cross_section("metal3", width=11)
    xs_metal3_wides = [
        gf.get_cross_section("metal3", width=30),
        gf.get_cross_section("metal3", width=34),
        gf.get_cross_section("metal3", width=38),
        gf.get_cross_section("metal3", width=42),
    ]

    #####################
    # COMPONENT CONTROL #
    #####################
    # Bend
    routing_bend_Si = ipr.bend_euler_custom_width(cross_section="strip")
    routing_bend_Si_inv = ipr.bend_euler_custom_width(cross_section="strip", angle=-90)
    routing_half_bend_Si = ipr.bend_euler_custom_width(cross_section="strip", angle=-45)
    routing_bend_Si_TM = ipr.bend_euler_custom_width(cross_section="strip", radius=10)

    # Taper
    taper_410_930 = ipr.rib_taper(cross_section=xs_swg, width_RIB_out=0.93)
    taper_1560_410 = ipr.rib_taper(
        cross_section=xs_swg, width_RIB_in=0.41, width_RIB_out=1.56
    )
    taper_1560_410 = change_port(
        taper_1560_410,  # Invert ports
        ["o1", "o2"],
        ["o2", "o1"],
        flatten=False,
    )

    # Routing straight
    routing_kwargs = {"bb1": taper_410_930}
    routing_strt = gf.partial(tps_410_swg_930_swg_lim, **routing_kwargs)

    # Vertical transition
    vt_pi = ipr.si_anwg_transition(
        name_si_nwg_transition="VT1_PI_D0_100",
        name_nwg_anwg_transition="VT2_POLINS_D_02",
        width_out=0.7,
    )

    vt_opt_te = ipr.si_anwg_transition(
        width_out=2.0,
    )

    # Polarization rotator
    pol_rot = ipr.rotator()

    # Edge coupler
    ec_pitch = 85
    ec_pitch_PUC = 127
    ec_amount_left = 22
    ec = ipr.anwg_ec_oband()

    # Grating coupler
    gc = ipr.tower_gc()
    gc_array_puc = ipr.grating_coupler_array(grating_coupler=gc, n=9)
    gc_array_puc2 = ipr.grating_coupler_array(grating_coupler=gc, n=8)
    gc_array_puc_json = ipr.grating_coupler_array(grating_coupler=gc, n=2)

    # Grating coupler for internal structure
    gc_array_te = ipr.grating_coupler_array(
        grating_coupler=ipr.tower_gc,
        n=10,
        with_loopback=True,
        cross_section=xs_swg,
        dx=15,
    )

    kwargs = {
        "bbmul": gc_array_te,
        "bbadd": change_port(ipr.rotator(), ["o1", "o2"], ["o2", "o1"]),
        "bbmul_list": [f"o{idx + 1}" for idx in range(8)],
    }
    gc_array_tm = ipr.bb_mul_bb(**kwargs)
    gc_array_tm = ipr.bb_mul_bb(**kwargs)
    gc_array_tm.name = "grating_coupler_array_tm"
    for idx in range(1, 8):
        gc_array_tm.info[f"gc_{idx}"] = ipr.combine_component_dict(
            ipr.measure_component(ipr.tower_gc()), ipr.measure_component(ipr.rotator())
        )

    # 2D Crossing
    crossing_2D = ipr.crossing("polaris", version="60nm")

    # Absorber
    absorber = ipr.rib_absorber()

    # Metal visual triangle
    triangle_size = 650
    triangle_sqr_size = 100
    triangle_sqr_dist = 25
    triangle = triangle_visual(
        square_roundness=0.5,
        square_size=triangle_sqr_size,
        square_distance=triangle_sqr_dist,
        triangle_size=triangle_size,
        triangle_layer=ipr.LAYER.metal3,
        slot_layer=ipr.LAYER.metal3_slot,
    )

    # Place the pad array
    pad_left_size = 150
    pad_left_pitch_hor = 250
    pad_left_pitch_ver = 300
    pad_left_amount_per_row = 10
    pad_left_edge_distance = 800
    pad_ay_left = gf.c.pad_array(
        pad=ipr.open_pad(size=(pad_left_size, pad_left_size)),
        rows=1,
        column_pitch=pad_left_pitch_hor,
        columns=pad_left_amount_per_row,
        layer=ipr.LAYER.metal3,
        port_orientation=-90,
        centered_ports=True,
    )
    pad_ay_left_d = gf.c.pad_array(
        pad=ipr.open_pad(size=(pad_left_size, pad_left_size)),
        rows=1,
        column_pitch=pad_left_pitch_hor,
        columns=pad_left_amount_per_row - 1,
        layer=ipr.LAYER.metal3,
        port_orientation=-90,
        centered_ports=True,
    )
    pad_right_size = 100
    pad_right_pitch_ver = 125
    pad_right_amount_per_col = 29
    pad_right_edge_distance = 110
    pad_ay_right = gf.c.pad_array(
        pad=ipr.open_pad(size=(pad_right_size, pad_right_size)),
        rows=pad_right_amount_per_col,
        row_pitch=pad_right_pitch_ver,
        columns=1,
        layer=ipr.LAYER.metal3,
        port_orientation=0,
        centered_ports=True,
    )

    # Diode
    diode = diode_linear(
        length_contact=5.0,
        length_dop1=5.15,
        length_dop1_overlap=5.0,
        length_dop2=1.15,
        length_dop2_overlap=0.15,
        margin_silicide=0.5,
        margin_swg=0.18,
        width_contact=20,
    )

    # Via from Metal 2 to Metal 3
    via_2_3 = via_metal2_metal3(size=(xs_metal2.width, xs_metal2.width), pitch_via=0.54)
    via_2_3_large = [
        via_23_with_metal_taper(via_width=30, metal3_width=11),
        via_23_with_metal_taper(via_width=34, metal3_width=11),
        via_23_with_metal_taper(via_width=38, metal3_width=11),
        via_23_with_metal_taper(via_width=42, metal3_width=11),
    ]

    # ################# #
    # STRUCTURE CONTROL #
    # ################# #
    # Initialize lists for pads left and right
    pad_left_top_ports = []
    pad_left_bot_ports = []
    pad_right_ports = []
    ec_left_ports = []

    # DoE Json file
    doe_json_filename = "src/ComplementaryFile/DoE_component_parameters.json"
    with open(doe_json_filename) as f:
        doe_json_dict = json.load(f)
    doe_json_dict = doe_json_dict["T2"]

    # Lab Json File
    lab_filename = "src/ComplementaryFile/V7b.json"
    create_json = True
    if create_json:
        json_writer = ipr.json_writer(filename=lab_filename, die="DIE_T2")
        # json_writer.reset() Assume you run first T1 and than T2

    # Sim Json file
    sim_filename = "src/ComplementaryFile/sim_bb.json"
    with open(sim_filename, encoding="utf-8") as f:
        sim_filename_json = json.load(f)

    # Structure dictionary where append the wanted structure
    structures = {}
    structures_text = {}
    structure_only = ()

    # Electrical pad array for the Diode and TLM
    pad_array_diode = die << pad_ay_right
    pad_array_diode.rotate(180)
    pad_array_diode.xmax = die.xmax - pad_right_edge_distance
    pad_array_diode.ymin = -pad_array_diode.ysize / 2
    pad_right_edge_distance += 200
    pad_array_diode_ports = [
        pad_array_diode.ports[f"e{idx + 1}1"] for idx in range(pad_right_amount_per_col)
    ]

    puc_area = 3180
    pad_array_tlm = die << pad_ay_right
    pad_array_tlm.rotate(180)
    pad_array_tlm.xmax = die.xmax - puc_area
    pad_array_tlm.ymin = -pad_array_tlm.ysize / 2
    pad_array_tlm_ports = [
        pad_array_tlm.ports[f"e{idx + 1}1"] for idx in range(pad_right_amount_per_col)
    ]

    pad_array_multi = die << pad_ay_right
    pad_array_multi.rotate(180)
    pad_array_multi.xmax = die.xmax - pad_right_edge_distance - 200
    pad_array_multi.ymin = -pad_array_multi.ysize / 2
    pad_array_multi = [
        pad_array_multi.ports[f"e{idx + 1}1"] for idx in range(pad_right_amount_per_col)
    ]

    # Electrical pad array (shared among sturctures)
    pad_array_right = die << pad_ay_right
    pad_array_right.rotate(180)
    pad_array_right.xmax = die.xmax - pad_right_edge_distance
    pad_array_right.ymin = -pad_array_right.ysize / 2
    pad_right_ports += [
        pad_array_right.ports[f"e{idx + 1}1"] for idx in range(pad_right_amount_per_col)
    ]

    #############
    # 1.0 DIODE #
    #############
    if len(structure_only) == 0 or 1 in structure_only:
        print("\nCreation of N.1 Diode Test Structure")

        ts = "1"
        for idx, name in enumerate(doe_json_dict[f"{ts}.0"]["comp"]):
            # Select the port of the PD
            if idx < 14:
                port_top = pad_array_diode_ports[idx * 2]
                port_bot = pad_array_diode_ports[idx * 2 + 1]
            else:
                port_top = pad_array_tlm_ports[idx * 2 - 28]
                port_bot = pad_array_tlm_ports[idx * 2 - 27]

            # Select the PD from the DoE file
            comp = sim_filename_json[doe_json_dict[f"{ts}.0"]["comp"][idx]]
            name = comp["function"].split(".")[-1].rstrip("()")
            func = eval(name)

            # Restore the settings
            settings = dict(comp["settings"])
            for setting_key, setting_value in settings.items():
                if (
                    isinstance(setting_value, str)
                    and setting_value in sim_filename_json
                ):
                    comp_settings = sim_filename_json[settings[setting_key]]
                    name_settings = (
                        comp_settings["function"].split(".")[-1].rstrip("()")
                    )
                    func_settings = eval(name_settings)
                    comp_reconstruct = func_settings(**comp_settings["settings"])
                    comp["settings"][setting_key] = comp_reconstruct

            diode_doe = func(**comp["settings"])

            # Place top part
            dd = die << diode_doe
            dd.rotate(-90)
            dd.x = port_top.x - 120
            dd.y = (port_top.y + port_bot.y) / 2

            # Calculate the length to have 45 degree metal
            length = abs(dd["P"].width - xs_metal1_wide.width) / 2

            # Place the taper
            diode_tap = gf.components.taper(
                width1=dd["P"].width,
                width2=xs_metal1_wide.width,
                layer=LAYER.metal1,
                length=length,
                port_types=("electrical", "electrical"),
                port_names=("e1", "e2"),
            )
            tap = die << diode_tap
            tap.connect("e1", dd["P"], allow_type_mismatch=True)

            # Place the first via
            via1 = die << ipr.via_metal1_metal3(
                size=(xs_metal1_wide.width, xs_metal1_wide.width)
            )
            via1.connect("e1", tap["e2"], allow_layer_mismatch=True)

            # Place the other taper
            tap = die << diode_tap
            tap.connect("e1", dd["N"], allow_type_mismatch=True)

            # Route to the pad
            gf.routing.route_single(
                die,
                via1["e3"],
                port_top,
                port_type="electrical",
                auto_taper=False,
                allow_width_mismatch=True,
                cross_section=xs_metal3,
                bend="wire_corner45",
                radius=xs_metal3.width / 2,
            )

            # Place the second via
            via1 = die << ipr.via_metal1_metal3(
                size=(xs_metal1_wide.width, xs_metal1_wide.width)
            )
            via1.connect("e1", tap["e2"], allow_layer_mismatch=True)

            # Route to the pad
            gf.routing.route_single(
                die,
                via1["e3"],
                port_bot,
                port_type="electrical",
                auto_taper=False,
                allow_width_mismatch=True,
                cross_section=xs_metal3,
                bend="wire_corner45",
                radius=xs_metal3.width / 2,
            )

            # Place Text information
            txt = die << ipr.text(
                f"{ts}.{idx + 1}\nDD{idx + 1}",
                size=20,
                layer=LAYER.metal3,
                justify="center",
            )
            txt.move(
                (txt.x, txt.y),
                (dd.x + 20, dd.y + 110),
            )
            rec = die << gf.c.rectangle(
                size=(txt.xsize + 10, txt.ysize + 10), layer=(118, 40)
            )
            rec.xmin = txt.xmin - 5
            rec.ymin = txt.ymin - 5

            # Add the structures to the json file
            if create_json:
                # Create json file
                json_writer.structure_json(
                    component=diode_doe,
                    component_IO=diode_doe,
                    structure_title=f"TS0{ts}.{idx + 1}",
                    structure=measure_structure(comp["design_id"]),
                    polarization=[],
                    propagation_mode=[],
                    extra_dict={"analysis": ["i_ma", "v_v", "vt_v"]},
                )

    ##################
    # 2.0 RIGHT PUCS #
    ##################
    if len(structure_only) == 0 or 2 in structure_only:
        print("\nCreation of N.2 First PUCS Test Structure")

        # Define the pucs of structure 2.0
        n_pucs = 4
        pucs = []
        design_id = []
        ts = "2"
        for idx in range(len(doe_json_dict[f"{ts}.0"]["comp"])):
            # Select the PD from the DoE file
            comp = sim_filename_json[doe_json_dict[f"{ts}.0"]["comp"][idx]]
            name = comp["function"].split(".")[-1].rstrip("()")
            func = eval(name)
            puc = func(**comp["settings"])
            design_id.append(comp["design_id"])
            pucs.append(puc)

        # Understand which port to be used
        pad_ports = pad_right_ports[0:8]

        # Create the test structure
        s1 = die << puc_array_test_structure(
            kind="Right",
            gc_array=gc_array_puc,
            pucs=pucs,
            pad_ports=pad_ports,
            routing_straight=swg,
            routing_bend=routing_bend_Si,
        )

        # Add text to the pucs
        for idx in range(n_pucs):
            text_info = die << ipr.text(
                f"{ts}.{idx + 1} \n {design_id[idx]}",
                size=text_size_puc,
                layer=LAYER.metal3,
                justify="center",
            )
            text_info.rotate(90)
            text_info.xmin = s1.xmax - 715 - 127 * (idx % n_pucs) * 2
            text_info.xmin += [0, 0, 0, 0][idx]
            text_info.ymin = s1.ymin + 430

            rec = die << gf.c.rectangle(
                size=(text_info.xsize + 10, text_info.ysize + 10), layer=(118, 40)
            )
            rec.xmin = text_info.xmin - 5
            rec.ymin = text_info.ymin - 5

        # Add the structures to the json file
        if create_json:
            for idx in range(n_pucs):
                comp = sim_filename_json[doe_json_dict[f"{ts}.0"]["comp"][idx]]
                json_writer.structure_json(
                    component=pucs[idx],
                    component_IO=gc_array_puc_json,
                    structure_title=f"TS02.{idx + 1}",
                    structure=measure_structure(comp["design_id"]),
                    extra_dict={
                        "analysis": ["ppi_mw", "er_db", "trise_us", "tfall_us"]
                    },
                )

    ##################
    # 3.0 RIGHT PUCS #
    ##################
    if len(structure_only) == 0 or 3 in structure_only:
        print("\nCreation of N.3 Seconds PUCS Test Structure")

        # Define the pucs of structure 3.0
        n_pucs = 4
        pucs = []
        design_id = []
        ts = "3"
        for idx in range(len(doe_json_dict[f"{ts}.0"]["comp"])):
            # Select the PD from the DoE file
            comp = sim_filename_json[doe_json_dict[f"{ts}.0"]["comp"][idx]]
            name = comp["function"].split(".")[-1].rstrip("()")
            func = eval(name)
            puc = func(**comp["settings"])
            design_id.append(comp["design_id"])
            pucs.append(puc)

        # Understand which port to be used
        pad_ports = pad_right_ports[0:8]

        # Create the test structure
        s1 = die << puc_array_test_structure(
            kind="Left",
            gc_array=gc_array_puc2,
            pucs=pucs,
            pad_ports=pad_ports,
            routing_straight=swg,
            routing_bend=routing_bend_Si,
        )

        # Add text to the pucs
        for idx in range(n_pucs):
            text_info = die << ipr.text(
                f"{ts}.{idx + 1} \n {design_id[idx]}",
                size=text_size_puc,
                layer=LAYER.metal3,
                justify="center",
            )
            text_info.rotate(90)
            text_info.xmin = s1.xmax - 1845 - 127 * (idx % n_pucs) * 2
            text_info.xmin += [0, 0, 0, 0][idx]
            text_info.ymin = s1.ymin + 430

            rec = die << gf.c.rectangle(
                size=(text_info.xsize + 10, text_info.ysize + 10), layer=(118, 40)
            )
            rec.xmin = text_info.xmin - 5
            rec.ymin = text_info.ymin - 5

        # Add the structures to the json file
        if create_json:
            for idx in range(n_pucs):
                comp = sim_filename_json[doe_json_dict[f"{ts}.0"]["comp"][idx]]
                json_writer.structure_json(
                    component=pucs[idx],
                    component_IO=gc_array_puc_json,
                    structure_title=f"TS0{ts}.{idx + 1}",
                    structure=measure_structure(comp["design_id"]),
                    extra_dict={
                        "analysis": ["ppi_mw", "er_db", "trise_us", "tfall_us"]
                    },
                )

    ##################
    # 4.0 RIGHT PUCS #
    ##################
    if len(structure_only) == 0 or 4 in structure_only:
        print("\nCreation of N.4 Third PUCS Test Structure")

        # Define the pucs of structure 4.0
        n_pucs = 4
        pucs = []
        design_id = []
        ts = "4"
        for idx in range(len(doe_json_dict[f"{ts}.0"]["comp"])):
            # Select the PD from the DoE file
            comp = sim_filename_json[doe_json_dict[f"{ts}.0"]["comp"][idx]]
            name = comp["function"].split(".")[-1].rstrip("()")
            func = eval(name)
            puc = func(**comp["settings"])
            design_id.append(comp["design_id"])
            pucs.append(puc)

        # Understand which port to be used
        pad_ports = pad_right_ports[10:18]

        # Create the test structure
        s1 = die << puc_array_test_structure(
            kind="Right",
            gc_array=gc_array_puc,
            pucs=pucs,
            pad_ports=pad_ports,
            routing_straight=swg,
            routing_bend=routing_bend_Si,
        )

        # Add text to the pucs
        for idx in range(n_pucs):
            text_info = die << ipr.text(
                f"{ts}.{idx + 1} \n {design_id[idx]}",
                size=text_size_puc,
                layer=LAYER.metal3,
                justify="center",
            )
            text_info.rotate(90)
            text_info.xmin = s1.xmax - 695 - 127 * (idx % n_pucs) * 2
            text_info.xmin += [0, 0, -10, 0][idx]
            text_info.ymin = s1.ymin + 430

            rec = die << gf.c.rectangle(
                size=(text_info.xsize + 10, text_info.ysize + 10), layer=(118, 40)
            )
            rec.xmin = text_info.xmin - 5
            rec.ymin = text_info.ymin - 5

        # Add the structures to the json file
        if create_json:
            for idx in range(n_pucs):
                comp = sim_filename_json[doe_json_dict[f"{ts}.0"]["comp"][idx]]
                json_writer.structure_json(
                    component=pucs[idx],
                    component_IO=gc_array_puc_json,
                    structure_title=f"TS0{ts}.{idx + 1}",
                    structure=measure_structure(comp["design_id"]),
                    extra_dict={
                        "analysis": ["ppi_mw", "er_db", "trise_us", "tfall_us"]
                    },
                )

    #################
    # 5.0 RIGHT PUCS #
    #################
    if len(structure_only) == 0 or 5 in structure_only:
        print("\nCreation of N.5 First PUCS Test Structure")

        # Define the pucs of structure 5.0
        n_pucs = 4
        pucs = []
        design_id = []
        ts = "5"
        for idx in range(len(doe_json_dict[f"{ts}.0"]["comp"])):
            # Select the PD from the DoE file
            comp = sim_filename_json[doe_json_dict[f"{ts}.0"]["comp"][idx]]
            name = comp["function"].split(".")[-1].rstrip("()")
            func = eval(name)
            puc = func(**comp["settings"])
            design_id.append(comp["design_id"])
            pucs.append(puc)

        # Understand which port to be used
        pad_ports = pad_right_ports[10:18]

        # Create the test structure
        s1 = die << puc_array_test_structure(
            kind="Left",
            gc_array=gc_array_puc2,
            pucs=pucs,
            pad_ports=pad_ports,
            routing_straight=swg,
            routing_bend=routing_bend_Si,
        )

        # Add text to the pucs
        for idx in range(n_pucs):
            text_info = die << ipr.text(
                f"{ts}.{idx + 1} \n {design_id[idx]}",
                size=text_size_puc,
                layer=LAYER.metal3,
                justify="center",
            )
            text_info.rotate(90)
            text_info.xmin = s1.xmax - 1865 - 127 * (idx % n_pucs) * 2
            text_info.xmin += [0, 0, 0, 0][idx]
            text_info.ymin = s1.ymin + 430

            rec = die << gf.c.rectangle(
                size=(text_info.xsize + 10, text_info.ysize + 10), layer=(118, 40)
            )
            rec.xmin = text_info.xmin - 5
            rec.ymin = text_info.ymin - 5

        # Add the structures to the json file
        if create_json:
            for idx in range(n_pucs):
                comp = sim_filename_json[doe_json_dict[f"{ts}.0"]["comp"][idx]]
                json_writer.structure_json(
                    component=pucs[idx],
                    component_IO=gc_array_puc_json,
                    structure_title=f"TS0{ts}.{idx + 1}",
                    structure=measure_structure(comp["design_id"]),
                    extra_dict={
                        "analysis": ["ppi_mw", "er_db", "trise_us", "tfall_us"]
                    },
                )

    ##################
    # 6.0 RIGHT PUCS #
    ##################
    if len(structure_only) == 0 or 6 in structure_only:
        print("\nCreation of N.6 Seconds PUCS Test Structure")

        # Define the pucs of structure 6.0
        n_pucs = 4
        pucs = []
        design_id = []
        ts = "6"
        for idx in range(len(doe_json_dict[f"{ts}.0"]["comp"])):
            # Select the PD from the DoE file
            comp = sim_filename_json[doe_json_dict[f"{ts}.0"]["comp"][idx]]
            name = comp["function"].split(".")[-1].rstrip("()")
            func = eval(name)
            puc = func(**comp["settings"])
            design_id.append(comp["design_id"])
            pucs.append(puc)

        # Understand which port to be used
        pad_ports = pad_right_ports[20:28]

        # Create the test structure
        s1 = die << puc_array_test_structure(
            kind="Right",
            gc_array=gc_array_puc,
            pucs=pucs,
            pad_ports=pad_ports,
            routing_straight=swg,
            routing_bend=routing_bend_Si,
        )

        # Add text to the pucs
        for idx in range(n_pucs):
            text_info = die << ipr.text(
                f"{ts}.{idx + 1} \n {design_id[idx]}",
                size=text_size_puc,
                layer=LAYER.metal3,
                justify="center",
            )
            text_info.rotate(90)
            text_info.xmin = s1.xmax - 715 - 127 * (idx % n_pucs) * 2
            text_info.xmin += [0, 0, 10, 0][idx]
            text_info.ymin = s1.ymin + 435

            rec = die << gf.c.rectangle(
                size=(text_info.xsize + 10, text_info.ysize + 10), layer=(118, 40)
            )
            rec.xmin = text_info.xmin - 5
            rec.ymin = text_info.ymin - 5

        # Add the structures to the json file
        if create_json:
            for idx in range(n_pucs):
                comp = sim_filename_json[doe_json_dict[f"{ts}.0"]["comp"][idx]]
                json_writer.structure_json(
                    component=pucs[idx],
                    component_IO=gc_array_puc_json,
                    structure_title=f"TS0{ts}.{idx + 1}",
                    structure=measure_structure(comp["design_id"]),
                    extra_dict={
                        "analysis": ["ppi_mw", "er_db", "trise_us", "tfall_us"]
                    },
                )

    ##################
    # 7.0 RIGHT PUCS #
    ##################
    if len(structure_only) == 0 or 7 in structure_only:
        print("\nCreation of N.7 Third PUCS Test Structure")

        # Define the pucs of structure 7.0
        n_pucs = 4
        pucs = []
        design_id = []
        ts = "7"
        for idx in range(len(doe_json_dict[f"{ts}.0"]["comp"])):
            # Select the PD from the DoE file
            comp = sim_filename_json[doe_json_dict[f"{ts}.0"]["comp"][idx]]
            name = comp["function"].split(".")[-1].rstrip("()")
            func = eval(name)
            puc = func(**comp["settings"])
            design_id.append(comp["design_id"])
            pucs.append(puc)

        # Understand which port to be used
        pad_ports = pad_right_ports[20:28]

        # Create the test structure
        s1 = die << puc_array_test_structure(
            kind="Left",
            gc_array=gc_array_puc2,
            pucs=pucs,
            pad_ports=pad_ports,
            routing_straight=swg,
            routing_bend=routing_bend_Si,
        )

        # Add text to the pucs
        for idx in range(n_pucs):
            text_info = die << ipr.text(
                f"{ts}.{idx + 1} \n {design_id[idx]}",
                size=text_size_puc,
                layer=LAYER.metal3,
                justify="center",
            )
            text_info.rotate(90)
            text_info.xmin = s1.xmax - 1820 - 127 * (idx % n_pucs) * 2
            text_info.xmin += [0, 0, 0, 0][idx]
            text_info.ymin = s1.ymin + 445

            rec = die << gf.c.rectangle(
                size=(text_info.xsize + 10, text_info.ysize + 10), layer=(118, 40)
            )
            rec.xmin = text_info.xmin - 5
            rec.ymin = text_info.ymin - 5

        # Add the structures to the json file
        if create_json:
            for idx in range(n_pucs):
                comp = sim_filename_json[doe_json_dict[f"{ts}.0"]["comp"][idx]]
                json_writer.structure_json(
                    component=pucs[idx],
                    component_IO=gc_array_puc_json,
                    structure_title=f"TS0{ts}.{idx + 1}",
                    structure=measure_structure(comp["design_id"]),
                    extra_dict={
                        "analysis": ["ppi_mw", "er_db", "trise_us", "tfall_us"]
                    },
                )

    ##################
    # 8.0 THERMISTOR #
    ##################
    if len(structure_only) == 0 or 8 in structure_only:
        print("\nCreation of N.8 Thermistor Test Structure")

        ts = "8"
        tlm_port = 5

        # Create a rotated pad port
        pad_strt = die << ipr.straight(length=0, cross_section=xs_metal1)
        pad_strt.rotate(90)
        pad_strt.x = pad_array_tlm[f"e{tlm_port}1"].x
        pad_strt.y = pad_array_tlm[f"e{tlm_port}1"].y

        # Select the thermistor from the DoE file
        comp = sim_filename_json[doe_json_dict[f"{ts}.0"]["comp"][0]]
        name = comp["function"].split(".")[-1].rstrip("()")
        try:
            func = eval(name)
        except NameError:
            func = getattr(ipr, name)

        thermistor = func(**comp["settings"])
        th = die << thermistor
        th.rotate(-90)
        th.x = pad_strt["e1"].x + 105
        th.ymax = (pad_strt["e1"].y + pad_strt["e1"].y) / 2

        # Calculate the length to have 45 degree metal
        length = abs(th["e1"].width - xs_metal1.width) / 2

        # Place the taper
        thermistor_tap = gf.components.taper(
            width1=th["e1"].width,
            width2=xs_metal1.width,
            layer=LAYER.metal1,
            length=length,
            port_types=("electrical", "electrical"),
            port_names=("e1", "e2"),
        )
        tap = die << thermistor_tap
        tap.connect("e1", th["e1"], allow_type_mismatch=True)

        # Place the first via
        via1 = die << ipr.via_metal1_metal3(size=(xs_metal1.width, xs_metal1.width))
        via1.connect("e1", tap["e2"], allow_layer_mismatch=True)

        # Place the other taper
        tap = die << thermistor_tap
        tap.connect("e1", th["e2"], allow_type_mismatch=True)

        # Route to the pad
        gf.routing.route_single(
            die,
            via1["e3"],
            pad_strt["e2"],
            port_type="electrical",
            auto_taper=False,
            allow_width_mismatch=True,
            cross_section=xs_metal3_narrow2,
            bend="wire_corner45",
            radius=xs_metal3_narrow2.width / 2,
            start_straight_length=5,
        )

        # Place the second via
        via1 = die << ipr.via_metal1_metal3(size=(xs_metal1.width, xs_metal1.width))
        via1.connect("e1", tap["e2"], allow_layer_mismatch=True)

        # Route to the pad
        gf.routing.route_single(
            die,
            pad_array_tlm[f"e{tlm_port + 1}1"],
            via1["e3"],
            port_type="electrical",
            auto_taper=False,
            allow_width_mismatch=True,
            cross_section=xs_metal3_narrow2,
            bend="wire_corner45",
            radius=xs_metal3_narrow2.width / 2,
        )

        # Place Text information
        txt = die << ipr.text(
            f"{ts}.1 TH", size=20, layer=LAYER.metal3, justify="center"
        )
        txt.move(
            (txt.x, txt.y),
            (th.x, th.y + 110),
        )
        rec = die << gf.c.rectangle(
            size=(txt.xsize + 10, txt.ysize + 10), layer=(118, 40)
        )
        rec.xmin = txt.xmin - 5
        rec.ymin = txt.ymin - 5

        # Add the structures to the json file
        if create_json:
            comp = sim_filename_json[doe_json_dict[f"{ts}.0"]["comp"][0]]
            json_writer.structure_json(
                component=thermistor,
                component_IO=thermistor,
                structure_title=f"TS0{ts}.1",
                structure=measure_structure(comp["design_id"]),
                polarization=[],
                propagation_mode=[],
                extra_dict={"analysis": ["i_ma", "v_v", "vt_v"]},
            )

    ##################################
    # 9.0 EDGE COUPLER - PREPARATION #
    ##################################
    if len(structure_only) == 0 or 9 in structure_only:
        print("\nCreation of N.9 Edge Coupler - Preparation")

        ts = "9"

        for idx in range(3):
            # Place top part
            ec_top = die << ec
            ec_top.rotate(-90)
            ec_top.ymax = die_ymax - edge_margin_top
            ec_top.xmax = die.xmax - edge_margin_right_top
            vt_top = die << vt_pi
            vt_top.connect("o2", ec_top["o1"])

            edge_margin_right_top += ec_pitch

            # Place bot part
            ec_bot = die << ec
            ec_bot.rotate(90)
            ec_bot.ymin = die_ymin + edge_margin_bot
            ec_bot.xmax = die.xmax - edge_margin_right_bot
            vt_bot = die << vt_pi
            vt_bot.connect("o2", ec_bot["o1"])

            edge_margin_right_bot += ec_pitch
            out_port = vt_bot["o1"]

            if idx == 0:
                name = "LOOP"
                polarization = ["te", "tm"]
            elif idx == 1:
                name = "ROT TM_TE"
                strt = die << straight_410_swg(length=5)
                strt.connect("o1", vt_bot["o1"])
                pol_rot_ref = die << pol_rot
                pol_rot_ref.connect("o1", strt["o2"])
                out_port = pol_rot_ref["o2"]
                polarization = ["tm"]
            elif idx == 2:
                name = "ROT TE_TM"
                strt = die << straight_410_swg(length=5)
                strt.connect("o1", vt_bot["o1"])
                pol_rot_ref = die << pol_rot
                pol_rot_ref.connect("o2", strt["o2"])
                out_port = pol_rot_ref["o1"]
                polarization = ["te"]

            # Connect bottom and top
            route = gf.routing.route_single(
                die,
                port1=vt_top["o1"],
                port2=out_port,
                cross_section=xs_swg,
                straight=straight_410_swg,
                bend=routing_bend_Si,
                auto_taper=False,
                start_straight_length=(vt_top["o1"].y - out_port.y) / 2,
            )

            # Add text TOP and BOT
            for jdx in range(2):
                text = die << ipr.text(
                    f"{ts}.{idx + 1} {name}",
                    size=text_size,
                    layer=LAYER.metal3,
                    justify="center",
                )
                text.rotate(90)
                if jdx == 0:
                    text.move(
                        (text.xmin, text.ymax),
                        ((ec_top.xmax - 73), (ec_top.ymax - 410)),
                    )
                else:
                    text.move(
                        (text.xmin, text.ymin),
                        ((ec_bot.xmax - 73), (ec_bot.ymin + 410)),
                    )

                bbox = die << gf.components.rectangle(
                    size=(text.xmax - text.xmin + 2, text.ymax - text.ymin + 2),
                    layer=bbox_layer,
                )
                bbox.move((bbox.xmin, bbox.ymin), ((text.xmin - 1, text.ymin - 1)))

            # Add the structures to the json file
            if create_json:
                # Measure the EC and its path
                mc = ipr.measure_component(ec)
                mc = ipr.combine_component_dict(mc, mc)

                for inst in route.instances:
                    temp_dict = ipr.measure_component(inst.cell, scale=1 / 1000)
                    mc = ipr.combine_component_dict(mc, temp_dict)

                # Add pol rotator
                if idx != 0:
                    pol_dict = ipr.measure_component(pol_rot_ref.cell, scale=1)
                    mc = ipr.combine_component_dict(pol_dict, mc)

                for key, item in mc.items():
                    mc[key] = [item]

                # Create json file
                json_writer.structure_json(
                    component=ec,
                    component_IO=ec,
                    structure_title=f"TS0{ts}.{idx + 1}",
                    structure=ec,
                    polarization=polarization,
                    propagation_mode=polarization,
                    extra_dict={
                        "nepoxy": [1, 1.428],
                        "analysis": ["ilte_db", "iltm_db"],
                        "edge_coupler": ["ec_main",
                                         "ec_main"],
                        "cutback": mc,
                    },
                )

    ###################
    # 10.0 PHOTODIODE #
    ###################
    if len(structure_only) == 0 or 10 in structure_only:
        print("\nCreation of N.10 PhotoDiode Test Structure")

        ts_base = "10"
        tlm_port = 22
        tlm_port_gnd = 24

        # Create the test structure
        for idx in range(len(doe_json_dict[f"{ts_base}.0"]["comp"])):
            ts = f"{ts_base}.{1 + idx}"

            # Select the PD from the DoE file
            comp = sim_filename_json[doe_json_dict[f"{ts_base}.0"]["comp"][idx]]
            name = comp["function"].split(".")[-1].rstrip("()")
            func = getattr(ipr, name)
            pd_original = func(**comp["settings"])

            # Change port just to allow measurement to work
            pd_original = change_port(
                pd_original, ["o1", "e1", "e2"], ["o1", "e1", "e2"]
            )

            if idx == 0:
                pd = tower_pd_eo(pd_original, kind=1)
            else:
                pd = tower_pd_eo(pd_original, kind=2)

            # Place EC on bot
            ec_bot = die << ec
            ec_bot.rotate(90)
            ec_bot.ymin = die_ymin + edge_margin_bot
            ec_bot.xmax = die.xmax - edge_margin_right_bot
            edge_margin_right_bot += ec_pitch
            edge_margin_right_top += ec_pitch

            # Place VT
            vt_bot = die << vt_pi
            vt_bot.connect("o2", ec_bot["o1"])

            # Place a straight
            strt = die << straight_410_swg(length=300)
            strt.connect("o1", vt_bot["o1"])

            # Place PD
            pd_ref = die << pd
            pd_ref.connect("o1", strt["o2"])

            # Electrical routing
            gf.routing.route_single(
                auto_taper=False,
                bend="wire_corner45",
                allow_width_mismatch=True,
                component=die,
                cross_section=xs_metal3,
                port1=pd_ref["e1"],
                port2=pad_array_tlm[f"e{tlm_port - idx}1"],
                radius=xs_metal3.width / 2,
                straight=ipr.straight,
            )

            gf.routing.route_single(
                auto_taper=False,
                bend="wire_corner45",
                allow_width_mismatch=True,
                component=die,
                cross_section=xs_metal3,
                port1=pd_ref["e2"],
                port2=pad_array_tlm[f"e{tlm_port_gnd}1"],
                radius=xs_metal3.width / 2,
                straight=ipr.straight,
            )

            # Add text BOT
            text = die << ipr.text(
                f"{ts}. PD", size=text_size, layer=LAYER.metal3, justify="center"
            )
            text.rotate(90)
            text.move((text.xmin, text.ymin), ((ec_bot.xmax - 73), (ec_bot.ymin + 410)))

            bbox = die << gf.components.rectangle(
                size=(text.xmax - text.xmin + 2, text.ymax - text.ymin + 2),
                layer=bbox_layer,
            )
            bbox.move((bbox.xmin, bbox.ymin), ((text.xmin - 1, text.ymin - 1)))

            # Add the structures to the json file
            if create_json:
                # Measure the PD
                mc = {}

                pd_dict = ipr.measure_component(pd_original, scale=1)

                mc = ipr.combine_component_dict(pd_dict, mc)

                for key, item in mc.items():
                    mc[key] = [item]

                # Create json file
                json_writer.structure_json(
                    component=pd_original,
                    component_IO=ec,
                    structure_title=f"TS{ts}",
                    structure=ec,
                    polarization=["te", "tm"],
                    propagation_mode=["te", "tm"],
                    extra_dict={
                        "nepoxy": [1, 1.428],
                        "analysis": ["r_aw", "idark_na", "psat_dbm"],
                        "edge_coupler": [f"{ec.name}"],
                        "cutback": mc,
                    },
                )

                # Add a large ground straight to improve conductivity

        strt = die << straight_with_slots(
            length=424.979 + len(doe_json_dict[f"{ts_base}.0"]["comp"]) * 85.2,
            cross_section=xs_metal3_wides[-1],
        )
        strt.xmax = pad_array_tlm.xmin
        strt.y = pad_array_tlm[f"e{tlm_port_gnd}1"].y

    #####################
    # 11.0 EDGE COUPLER #
    #####################
    if len(structure_only) == 0 or 11 in structure_only:
        print("\nCreation of N.11 Edge Coupler Test Structure")

        ts_base = "11"
        for idx, name in enumerate(doe_json_dict[f"{ts_base}.0"]["comp"]):
            ts = f"{ts_base}.{idx + 1}"

            # Select the EC from the DoE file
            comp = sim_filename_json[doe_json_dict[f"{ts_base}.0"]["comp"][idx]]
            name = comp["function"].split(".")[-1].rstrip("()")

            # Try getting from ipronics
            try:
                func = getattr(ipr, name)
            except AttributeError:
                func = eval(name)
            ec_DoE = func(**comp["settings"])

            ec_with_vt_DoE = ec_with_vt(ec=ec_DoE)

            # Understand if the EC is tilted
            tilt = doe_json_dict[f"{ts_base}.0"]["tilt"][idx]
            if tilt:
                edge_margin_right_top += ec_pitch

            # Place top part
            ec_top = die << ec_with_vt_DoE
            ec_top.rotate(-90)
            ec_top.ymax = die_ymax - edge_margin_top
            ec_top.movex(
                ec_top["oaux1"].x, die.xmax - edge_margin_right_top - ec.ysize / 2
            )
            edge_margin_right_top += ec_pitch

            # Place bot part
            ec_bot = die << ec_with_vt_DoE
            ec_bot.rotate(90)
            ec_bot.ymin = die_ymin + edge_margin_bot
            ec_bot.movex(
                ec_bot["oaux1"].x, die.xmax - edge_margin_right_bot - ec.ysize / 2
            )
            edge_margin_right_bot += ec_pitch
            if tilt:
                edge_margin_right_bot += ec_pitch

            # Connect bottom and top
            route = gf.routing.route_single(
                die,
                port1=ec_top["o1"],
                port2=ec_bot["o1"],
                cross_section=xs_swg,
                straight=straight_410_swg,
                bend=routing_bend_Si,
                auto_taper=False,
                start_straight_length=(ec_top["o1"].y - ec_bot["o1"].y) / 2,
            )

            # Add text TOP and BOT
            for jdx in range(2):
                text = die << ipr.text(
                    (f"{ts} AWNG EC").upper(),
                    size=text_size,
                    layer=LAYER.metal3,
                    justify="center",
                )
                text.rotate(90)
                if jdx == 0:
                    text.move(
                        (text.xmin, text.ymax),
                        ((ec_top.xmax - 73), (ec_top.ymax - 425)),
                    )
                else:
                    text.move(
                        (text.xmin, text.ymin),
                        ((ec_bot.xmax - 73), (ec_bot.ymin + 425)),
                    )

                bbox = die << gf.components.rectangle(
                    size=(text.xmax - text.xmin + 2, text.ymax - text.ymin + 2),
                    layer=bbox_layer,
                )
                bbox.move((bbox.xmin, bbox.ymin), ((text.xmin - 1, text.ymin - 1)))

            # Add the structures to the json file
            if create_json:
                # Measure the EC and its path
                mc = ipr.measure_component(ec_DoE)
                mc = ipr.combine_component_dict(mc, mc)
                for inst in route.instances:
                    temp_dict = ipr.measure_component(inst.cell, scale=1 / 1000)
                    mc = ipr.combine_component_dict(mc, temp_dict)
                for key, item in mc.items():
                    mc[key] = [item]

                # Create json file
                json_writer.structure_json(
                    component=ec_DoE,
                    component_IO=ec_DoE,
                    structure_title=f"TS{ts}",
                    structure=ec_DoE,
                    polarization=["te", "tm"],
                    propagation_mode=["te", "tm"],
                    extra_dict={
                        "nepoxy": [1, 1.428],
                        "analysis": ["ilte_db", "iltm_db"],
                        "edge_coupler": [f"{comp['design_id']}"] * 2,
                        "cutback": mc,
                    },
                )

    ###########################
    # 12.0 PBS TEST STRUCTURE #
    ###########################
    if len(structure_only) == 0 or 12 in structure_only:
        print("\nCreation of N.12 PBS Test Structure")

        ts_base = "12"

        # Create the test structure
        for idx in range(len(doe_json_dict[f"{ts_base}.0"]["comp"])):
            ts = f"{ts_base}.{1 + idx}"

            # Select the PBS from the DoE file
            comp = sim_filename_json[doe_json_dict[f"{ts_base}.0"]["comp"][idx]]
            name = comp["function"].split(".")[-1].rstrip("()")
            func = eval(name)
            pbs = func(**comp["settings"])

            # Place EC on top
            ec_top = die << ec
            ec_top.rotate(-90)
            ec_top.ymax = die_ymax - edge_margin_top
            ec_top.xmax = die_xmax - edge_margin_right_top

            vt_top = die << vt_pi
            vt_top.connect("o2", ec_top["o1"])
            edge_margin_right_top += ec_pitch

            # Place EC on bot
            ec_bot = die << ec
            ec_bot.rotate(90)
            ec_bot.ymin = die_ymin + edge_margin_bot
            ec_bot.xmax = die_xmax - edge_margin_right_bot
            edge_margin_right_bot += ec_pitch

            vt_bot = die << vt_pi
            vt_bot.connect("o2", ec_bot["o1"])

            # Place Second EC on top/bot depending on case
            ec_aux = die << ec
            if idx % 2 == 0:
                ec_aux.rotate(-90)
                ec_aux.ymax = die_ymax - edge_margin_top
                ec_aux.xmax = die_xmax - edge_margin_right_top
                edge_margin_right_top += ec_pitch
            else:
                ec_aux.rotate(90)
                ec_aux.ymin = die_ymin + edge_margin_bot
                ec_aux.xmax = die_xmax - edge_margin_right_bot
                edge_margin_right_bot += ec_pitch

            vt_aux = die << vt_pi
            vt_aux.connect("o2", ec_aux["o1"])

            # Place the pbs in the center
            pbs_ref = die << pbs
            if idx % 2 == 0:
                pbs_ref.rotate(90)
                pbs_ref.mirror_x()
                pbs_ref.movex(pbs_ref["o1"].x, ec_bot.x)
                pbs_ref.ymin = vt_bot.ymax + 0.5
            else:
                pbs_ref.rotate(-90)
                pbs_ref.movex(pbs_ref["o1"].x, ec_top.x)
                pbs_ref.ymax = vt_top.ymin - 0.5

            # Place absorber
            abs_ref = die << absorber
            if idx % 2 == 0:
                abs_ref.mirror_x()
            abs_ref.connect("o1", pbs_ref["o2"])

            # Connect bottom and top
            route1 = gf.routing.route_single(
                die,
                port1=pbs_ref["o1"],
                port2=vt_bot["o1"] if idx % 2 == 0 else vt_top["o1"],
                cross_section=xs_swg,
                straight=straight_410_swg,
                bend=routing_bend_Si,
                auto_taper=False,
            )

            route2 = gf.routing.route_single(
                die,
                port1=pbs_ref["o3"],
                port2=vt_top["o1"] if idx % 2 == 0 else vt_bot["o1"],
                cross_section=xs_swg,
                straight=straight_410_swg,
                bend=routing_bend_Si,
                auto_taper=False,
            )

            route3 = gf.routing.route_single(
                die,
                port1=pbs_ref["o4"],
                port2=vt_aux["o1"],
                cross_section=xs_swg,
                straight=straight_410_swg,
                bend=routing_bend_Si,
                auto_taper=False,
                start_straight_length=200,
            )

            # Add text TOP and BOT
            for jdx in range(3):
                text = (
                    f"{ts} " + comp["design_id"]
                    if jdx == 0
                    else "TM"
                    if jdx == 1
                    else "TE"
                )

                text_cell = die << ipr.text(
                    text.upper(), size=text_size, layer=LAYER.metal3, justify="center"
                )
                text_cell.rotate(90)
                if jdx == 0:
                    if idx % 2 == 0:
                        text_cell.move(
                            (text_cell.xmin, text_cell.ymin),
                            ((ec_bot.xmax - 80), (ec_bot.ymax + 15)),
                        )
                    else:
                        text_cell.move(
                            (text_cell.xmin, text_cell.ymax),
                            ((ec_top.xmax - 80), (ec_top.ymin - 15)),
                        )
                elif jdx == 1:
                    if idx % 2 == 0:
                        text_cell.move(
                            (text_cell.xmin, text_cell.ymax),
                            ((ec_top.xmax - 80), (ec_top.ymin - 15)),
                        )
                    else:
                        text_cell.move(
                            (text_cell.xmin, text_cell.ymin),
                            ((ec_bot.xmax - 80), (ec_bot.ymax + 15)),
                        )
                else:
                    if idx % 2 == 0:
                        text_cell.move(
                            (text_cell.xmin, text_cell.ymax),
                            ((ec_aux.xmax - 80), (ec_aux.ymin - 15)),
                        )
                    else:
                        text_cell.move(
                            (text_cell.xmin, text_cell.ymin),
                            ((ec_aux.xmax - 80), (ec_aux.ymax + 15)),
                        )

                bbox = die << gf.components.rectangle(
                    size=(
                        text_cell.xmax - text_cell.xmin + 2,
                        text_cell.ymax - text_cell.ymin + 2,
                    ),
                    layer=bbox_layer,
                )
                bbox.move(
                    (bbox.xmin, bbox.ymin), ((text_cell.xmin - 1, text_cell.ymin - 1))
                )

            # Add the structures to the json file
            if create_json:
                # Measure the EC
                mc1 = {}
                mc2 = {}
                for inst in route1.instances:
                    temp_dict = ipr.measure_component(inst.cell, scale=1 / 1000)
                    mc1 = ipr.combine_component_dict(mc1, temp_dict)
                    mc2 = ipr.combine_component_dict(mc2, temp_dict)
                for inst in route2.instances:
                    temp_dict = ipr.measure_component(inst.cell, scale=1 / 1000)
                    mc1 = ipr.combine_component_dict(mc1, temp_dict)
                for inst in route3.instances:
                    temp_dict = ipr.measure_component(inst.cell, scale=1 / 1000)
                    mc2 = ipr.combine_component_dict(mc2, temp_dict)
                temp_dict = ipr.measure_component(pbs_ref.cell, scale=1)
                mc1 = ipr.combine_component_dict(mc1, temp_dict)
                mc2 = ipr.combine_component_dict(mc2, temp_dict)

                mc = {}
                for key in mc1.keys():
                    mc[key] = [mc1[key], mc2[key]]

                # Create json file
                json_writer.structure_json(
                    component=pbs,
                    component_IO=ec,
                    structure_title=f"TS{ts}",
                    structure=ec,
                    polarization=["te", "tm"],
                    propagation_mode=["te", "tm"],
                    extra_dict={
                        "nepoxy": [1, 1.428],
                        "analysis": ["ilte_db", "iltm_db", "xtte_db", "xttm_db"],
                        "edge_coupler": [f"{ec.name}"] * 3,
                        "cutback": mc,
                    },
                )

    ############################
    # 13.0 PBSR TEST STRUCTURE #
    ############################
    if len(structure_only) == 0 or 13 in structure_only:
        print("\nCreation of N.13 PBSR Test Structure")

        ts_base = "13"

        # Create the test structure
        pbsr_list = []

        # PBSR full BB
        for idx in range(len(doe_json_dict[f"{ts_base}.0"]["comp"])):
            # Select the PBSR from the DoE file
            comp = sim_filename_json[doe_json_dict[f"{ts_base}.0"]["comp"][idx]]
            name = comp["function"].split(".")[-1].rstrip("()")

            try:
                func = eval(name)
            except NameError:
                func = getattr(ipr, name)
            pbsr = func(**comp["settings"])
            pbsr_list.append(pbsr)

        # PBS + Rot
        for idx in range(len(doe_json_dict[f"{ts_base}.1"]["comp"])):
            # Select the SiN2 from the DoE file
            comp = sim_filename_json[doe_json_dict[f"{ts_base}.1"]["comp"][idx]]
            name = comp["function"].split(".")[-1].rstrip("()")
            try:
                func = eval(name)
            except NameError:
                func = getattr(ipr, name)
            pbs = func(**comp["settings"])

            # Change port
            pbs = change_port(
                pbs, ports_i=["o1", "o2", "o3", "o4"], ports_o=["o4", "o1", "o3", "o2"]
            )

            # Select the rotator
            comp = sim_filename_json[doe_json_dict[f"{ts_base}.1"]["rotator"][idx]]
            name = comp["function"].split(".")[-1].rstrip("()")
            try:
                func = eval(name)
            except NameError:
                func = getattr(ipr, name)
            rot = func(**comp["settings"])

            # Add taper to rotator
            tp = ipr.rib_taper(
                width_RIB_in=rot["o2"].width, width_RIB_out=0.41, length=1
            )
            kwargs_tp = {"bbmul": rot, "bbadd": tp, "bbmul_list": ["o2"]}
            rot_ref = ipr.bb_mul_bb(**kwargs_tp)

            # Join rotator and pbs
            kwargs_bb = {
                "bbmul": pbs,
                "bbadd": rot_ref,
                "bbmul_list": ["o2"],
                "bbadd_mirror": [True],
            }
            pbsr = ipr.bb_mul_bb(**kwargs_bb)

            # Join spiral and pbrs
            kwargs_sp = {
                "bbmul": pbsr,
                "bbadd": ipr.rib_absorber(),
                "bbmul_list": ["o4"],
                "bbadd_mirror": [True],
            }
            pbsr_with_spiral = ipr.bb_mul_bb(**kwargs_sp)

            # Join spiral and sbend
            sbend = ipr.bend_bezier_s_custom_width()
            kwargs_sb = {
                "bbmul": pbsr_with_spiral,
                "bbadd": sbend,
                "bbmul_list": ["o3"],
            }
            pbsr = ipr.bb_mul_bb(**kwargs_sb)

            pbsr.function_name = pbs.function_name + "__" + rot.function_name
            pbs_settings = pbs.settings.model_dump()
            rot_settings = rot.settings.model_dump()
            tot_settings = pbs_settings | rot_settings
            pbsr.settings = json_settings(tot_settings)

            pbsr.flatten()

            pbsr_list.append(pbsr)

        for idx, pbsr in enumerate(pbsr_list):
            ts = f"{ts_base}.{1 + idx}"

            # Place EC on top
            ec_top = die << ec
            ec_top.rotate(-90)
            ec_top.ymax = die_ymax - edge_margin_top
            ec_top.xmax = die.xmax - edge_margin_right_top

            vt_top = die << vt_pi
            vt_top.connect("o2", ec_top["o1"])
            edge_margin_right_top += ec_pitch

            # Place EC on bot
            ec_bot = die << ec
            ec_bot.rotate(90)
            ec_bot.ymin = die_ymin + edge_margin_bot
            ec_bot.xmax = die.xmax - edge_margin_right_bot
            edge_margin_right_bot += ec_pitch

            vt_bot = die << vt_pi
            vt_bot.connect("o2", ec_bot["o1"])

            # Place Second EC on top/bot depending on case
            ec_aux = die << ec
            if idx % 2 == 0:
                ec_aux.rotate(-90)
                ec_aux.ymax = die_ymax - edge_margin_top
                ec_aux.xmax = die.xmax - edge_margin_right_top
                edge_margin_right_top += ec_pitch
            else:
                ec_aux.rotate(90)
                ec_aux.ymin = die_ymin + edge_margin_bot
                ec_aux.xmax = die.xmax - edge_margin_right_bot
                edge_margin_right_bot += ec_pitch

            vt_aux = die << vt_pi
            vt_aux.connect("o2", ec_aux["o1"])

            # Place the pbsr in the center
            pbsr_ref = die << pbsr

            if idx % 2 == 0:
                pbsr_ref.rotate(90)
                pbsr_ref.movex(pbsr_ref["o1"].x, ec_bot.x)
                pbsr_ref.ymin = vt_bot.ymax + 0.5
            else:
                pbsr_ref.rotate(-90)
                pbsr_ref.mirror_x()
                pbsr_ref.movex(pbsr_ref["o1"].x, ec_top.x)
                pbsr_ref.ymax = vt_top.ymin - 0.5
            port_rot = pbsr_ref["o3"]

            # Connect bottom and top
            route1 = gf.routing.route_single(
                die,
                port1=pbsr_ref["o1"],
                port2=vt_bot["o1"] if idx % 2 == 0 else vt_top["o1"],
                cross_section=xs_swg,
                straight=straight_410_swg,
                bend=routing_bend_Si,
                auto_taper=False,
            )

            route2 = gf.routing.route_single(
                die,
                port1=pbsr_ref["o2"],
                port2=vt_top["o1"] if idx % 2 == 0 else vt_bot["o1"],
                cross_section=xs_swg,
                straight=straight_410_swg,
                bend=routing_bend_Si,
                auto_taper=False,
            )

            route3 = gf.routing.route_single(
                die,
                port1=port_rot,
                port2=vt_aux["o1"],
                cross_section=xs_swg,
                straight=straight_410_swg,
                bend=routing_bend_Si,
                auto_taper=False,
            )

            # Add text TOP and BOT
            for jdx in range(3):
                text = f"{ts} " + "PSR" if jdx == 0 else "TM" if jdx == 1 else "TE"

                text_cell = die << ipr.text(
                    text, size=text_size, layer=LAYER.metal3, justify="center"
                )
                text_cell.rotate(90)
                if jdx == 0:
                    if idx % 2 == 0:
                        text_cell.move(
                            (text_cell.xmin, text_cell.ymin),
                            ((ec_bot.xmax - 80), (ec_bot.ymax + 15)),
                        )
                    else:
                        text_cell.move(
                            (text_cell.xmin, text_cell.ymax),
                            ((ec_top.xmax - 80), (ec_top.ymin - 15)),
                        )
                elif jdx == 1:
                    if idx % 2 == 0:
                        text_cell.move(
                            (text_cell.xmin, text_cell.ymax),
                            ((ec_top.xmax - 80), (ec_top.ymin - 15)),
                        )
                    else:
                        text_cell.move(
                            (text_cell.xmin, text_cell.ymin),
                            ((ec_bot.xmax - 80), (ec_bot.ymax + 15)),
                        )
                else:
                    if idx % 2 == 0:
                        text_cell.move(
                            (text_cell.xmin, text_cell.ymax),
                            ((ec_aux.xmax - 80), (ec_aux.ymin - 15)),
                        )
                    else:
                        text_cell.move(
                            (text_cell.xmin, text_cell.ymin),
                            ((ec_aux.xmax - 80), (ec_aux.ymax + 15)),
                        )

                bbox = die << gf.components.rectangle(
                    size=(
                        text_cell.xmax - text_cell.xmin + 2,
                        text_cell.ymax - text_cell.ymin + 2,
                    ),
                    layer=bbox_layer,
                )
                bbox.move(
                    (bbox.xmin, bbox.ymin), ((text_cell.xmin - 1, text_cell.ymin - 1))
                )

            # Add the structures to the json file
            if create_json:
                # Measure the EC
                mc1 = {}
                mc2 = {}
                for inst in route1.instances:
                    temp_dict = ipr.measure_component(inst.cell, scale=1 / 1000)
                    mc1 = ipr.combine_component_dict(mc1, temp_dict)
                    mc2 = ipr.combine_component_dict(mc2, temp_dict)
                for inst in route2.instances:
                    temp_dict = ipr.measure_component(inst.cell, scale=1 / 1000)
                    mc1 = ipr.combine_component_dict(mc1, temp_dict)
                for inst in route3.instances:
                    temp_dict = ipr.measure_component(inst.cell, scale=1 / 1000)
                    mc2 = ipr.combine_component_dict(mc2, temp_dict)
                temp_dict = ipr.measure_component(pbsr_ref.cell, scale=1)
                mc1 = ipr.combine_component_dict(mc1, temp_dict)
                mc2 = ipr.combine_component_dict(mc2, temp_dict)

                mc = {}
                for key in mc1.keys():
                    mc[key] = [mc1[key], mc2[key]]

                # Create json file
                json_writer.structure_json(
                    component=pbsr,
                    component_IO=ec,
                    structure_title=f"TS{ts}",
                    structure=ec,
                    polarization=["te", "tm"],
                    propagation_mode=["te", "tm"],
                    extra_dict={
                        "nepoxy": [1, 1.428],
                        "analysis": ["ilte_db", "iltm_db", "xtte_db", "xttm_db"],
                        "edge_coupler": [f"{ec.name}"] * 3,
                        "cutback": mc,
                    },
                )

    ###############################
    # 14.0 POL ROT TEST STRUCTURE #
    ###############################
    if len(structure_only) == 0 or 14 in structure_only:
        print("\nCreation of N.14 Pol Rotator Test Structure")

        ts_base = "14"

        # Rot BB
        for idx in range(len(doe_json_dict[f"{ts_base}.0"]["comp"])):
            ts = f"{ts_base}.{1 + idx}"

            # Select the Pol Rot from the DoE file
            comp = sim_filename_json[doe_json_dict[f"{ts_base}.0"]["comp"][idx]]
            name = comp["function"].split(".")[-1].rstrip("()")
            try:
                func = eval(name)
            except NameError:
                func = getattr(ipr, name)
            rot = func(**comp["settings"])

            # Add taper to rotator
            tp = ipr.rib_taper(
                width_RIB_in=rot["o2"].width, width_RIB_out=0.41, length=1
            )
            kwargs_tp = {"bbmul": rot, "bbadd": tp, "bbmul_list": ["o2"]}
            rot_tap = ipr.bb_mul_bb(**kwargs_tp)

            # Place EC on top
            ec_top = die << ec
            ec_top.rotate(-90)
            ec_top.ymax = die_ymax - edge_margin_top
            ec_top.xmax = die.xmax - edge_margin_right_top

            vt_top = die << vt_pi
            vt_top.connect("o2", ec_top["o1"])
            edge_margin_right_top += ec_pitch

            # Place EC on bot
            ec_bot = die << ec
            ec_bot.rotate(90)
            ec_bot.ymin = die_ymin + edge_margin_bot
            ec_bot.xmax = die.xmax - edge_margin_right_bot
            edge_margin_right_bot += ec_pitch

            vt_bot = die << vt_pi
            vt_bot.connect("o2", ec_bot["o1"])

            prev_port = vt_bot["o1"]

            # Calculate number of rotator
            n_comp = doe_json_dict[f"{ts_base}.0"]["n_comp"][idx]

            # Calculate lengths random
            lengths = ipr.random_number_array(
                mean=1.141, variation=0.141, n_elements=n_comp
            )
            for idx in range(n_comp):
                # Place a small straight
                strt = die << straight_410_swg(length=lengths[idx])
                strt.connect("o1", prev_port)

                # Place the rotator
                rot_ref = die << rot_tap

                # Connect to previous port
                if idx % 2 == 1:
                    rot_ref.connect("o1", strt["o2"])
                    prev_port = rot_ref["o2"]
                else:
                    rot_ref.connect("o2", strt["o2"])
                    prev_port = rot_ref["o1"]

            # Calculate th straight up to half of the die
            straight_length = die_y_center - prev_port.y - 10
            route = gf.routing.route_single(
                die,
                port1=prev_port,
                port2=vt_top["o1"],
                cross_section=xs_swg,
                straight=straight_410_swg,
                bend=routing_bend_Si,
                auto_taper=False,
                start_straight_length=straight_length,
            )

            # Add text TOP and BOT
            for jdx in range(2):
                text = (f"{ts} POL ROT").upper()

                text_cell = die << ipr.text(
                    text, size=text_size, layer=LAYER.metal3, justify="center"
                )
                text_cell.rotate(90)
                if jdx % 2 == 0:
                    text_cell.move(
                        (text_cell.xmin, text_cell.ymin),
                        ((ec_bot.xmax - 80), (ec_bot.ymax + 15)),
                    )
                else:
                    text_cell.move(
                        (text_cell.xmin, text_cell.ymax),
                        ((ec_top.xmax - 80), (ec_top.ymin - 15)),
                    )

                bbox = die << gf.components.rectangle(
                    size=(
                        text_cell.xmax - text_cell.xmin + 2,
                        text_cell.ymax - text_cell.ymin + 2,
                    ),
                    layer=bbox_layer,
                )
                bbox.move(
                    (bbox.xmin, bbox.ymin), ((text_cell.xmin - 1, text_cell.ymin - 1))
                )

            # Add the structures to the json file
            if create_json:
                # Measure the EC
                mc1 = {}
                for inst in route.instances:
                    temp_dict = ipr.measure_component(inst.cell, scale=1 / 1000)
                    mc1 = ipr.combine_component_dict(mc1, temp_dict)
                temp_dict = ipr.measure_component(rot_ref.cell, scale=1)
                mc1 = ipr.combine_component_dict(mc1, temp_dict)

                mc = {}
                for key in mc1.keys():
                    if key in temp_dict:
                        mc[key] = [mc1[key] * n_comp]
                    else:
                        mc[key] = [mc1[key]]

                # Create json file
                json_writer.structure_json(
                    component=rot,
                    component_IO=ec,
                    structure_title=f"TS{ts}",
                    structure=ec,
                    polarization=["te"],
                    propagation_mode=["te"],
                    extra_dict={
                        "nepoxy": [1, 1.428],
                        "analysis": ["iltm_db", "xtte_db"],
                        "edge_coupler": [f"{ec.name}"] * 2,
                        "cutback": mc,
                    },
                )

    ##################################
    # 15.0 POL SCHEME TEST STRUCTURE #
    ##################################
    if len(structure_only) == 0 or 15 in structure_only:
        print("\nCreation of N.15 Pol Scheme Test Structure")

        ts_base = "15"

        # Polarization scheme definition
        comp_list = doe_json_dict[f"{ts_base}.0"]["comp_list"]
        in_port_list = doe_json_dict[f"{ts_base}.0"]["in_port_list"]
        out_port_list = doe_json_dict[f"{ts_base}.0"]["out_port_list"]
        port_final_list = doe_json_dict[f"{ts_base}.0"]["port_final_list"]
        for idx in range(len(comp_list)):
            ts = f"{ts_base}.{1 + idx}"

            # Select the components
            comps = []
            design_id = ""
            for jdx in range(len(comp_list[idx])):
                comp = sim_filename_json[comp_list[idx][jdx]]
                name = comp["function"].split(".")[-1].rstrip("()")

                try:
                    func = eval(name)
                except NameError:
                    func = getattr(ipr, name)
                comp_ref = func(**comp["settings"])

                # Add them to the list
                comps.append(comp_ref)
                if len(design_id) == 0:
                    design_id = comp["design_id"]
                else:
                    design_id += "_" + comp["design_id"]

            # Place EC on top
            ec_top = die << ec
            ec_top.rotate(-90)
            ec_top.ymax = die_ymax - edge_margin_top
            ec_top.xmax = die.xmax - edge_margin_right_top

            vt_top = die << vt_pi
            vt_top.connect("o2", ec_top["o1"])

            strt_top = die << straight_410_swg(length=1)
            strt_top.connect("o1", vt_top["o1"])
            edge_margin_right_top += ec_pitch

            # Place EC on bot
            ec_bot = die << ec
            ec_bot.rotate(90)
            ec_bot.ymin = die_ymin + edge_margin_bot
            ec_bot.xmax = die.xmax - edge_margin_right_bot

            vt_bot = die << vt_pi
            vt_bot.connect("o2", ec_bot["o1"])

            strt_bot = die << straight_410_swg(length=1)
            strt_bot.connect("o1", vt_bot["o1"])
            edge_margin_right_bot += ec_pitch

            prev_top_port = strt_top["o2"]
            port_final_top = None
            for jdx, comp in enumerate(comps):
                # Place the comp
                comp_ref = die << comp

                # Connect with previous one
                comp_ref.connect(in_port_list[idx][jdx], prev_top_port)
                prev_top_port = comp_ref[out_port_list[idx][jdx]]

                # Check the final port
                if port_final_list[idx][jdx] is not None:
                    port_final_top = comp_ref[port_final_list[idx][jdx]]

                # Add absorber
                for port in comp_ref.ports:
                    if (
                        port.name != out_port_list[idx][jdx]
                        and port.name != port_final_list[idx][jdx]
                        and port.name != in_port_list[idx][jdx]
                    ):
                        abs_ref = die << absorber
                        abs_ref.mirror_x()
                        abs_ref.connect("o1", port)

            prev_bot_port = strt_bot["o2"]
            port_final_bot = None
            for jdx, comp in enumerate(comps):
                # Place the comp
                comp_ref = die << comp

                # Connect with previous one
                comp_ref.connect(in_port_list[idx][jdx], prev_bot_port)
                prev_bot_port = comp_ref[out_port_list[idx][jdx]]

                # Check the final port
                if port_final_list[idx][jdx] is not None:
                    port_final_bot = comp_ref[port_final_list[idx][jdx]]

                # Add absorber
                for port in comp_ref.ports:
                    if (
                        port.name != out_port_list[idx][jdx]
                        and port.name != port_final_list[idx][jdx]
                        and port.name != in_port_list[idx][jdx]
                    ):
                        abs_ref = die << absorber
                        abs_ref.mirror_x()
                        abs_ref.connect("o1", port)

            if idx in [2, 3]:
                sbend = die << ipr.bend_bezier_s_custom_width()
                sbend.connect("o1", port_final_top)
                port_final_top = sbend["o2"]

                sbend = die << ipr.bend_bezier_s_custom_width()
                sbend.connect("o1", port_final_bot)
                port_final_bot = sbend["o2"]

            route1 = gf.routing.route_single(
                die,
                port1=port_final_bot,
                port2=prev_top_port,
                cross_section=xs_swg,
                straight=straight_410_swg,
                bend=routing_bend_Si,
                auto_taper=False,
            )

            route2 = gf.routing.route_single(
                die,
                port1=port_final_top,
                port2=prev_bot_port,
                cross_section=xs_swg,
                straight=straight_410_swg,
                bend=routing_bend_Si,
                auto_taper=False,
            )

            # Add text TOP and BOT
            for jdx in range(2):
                text = (f"{ts} " + "P. S." + str(idx + 1)).upper()

                text_cell = die << ipr.text(
                    text, size=text_size, layer=LAYER.metal3, justify="center"
                )
                text_cell.rotate(90)
                if jdx % 2 == 0:
                    text_cell.move(
                        (text_cell.xmin, text_cell.ymin),
                        ((ec_bot.xmax - 80), (ec_bot.ymax + 15)),
                    )
                else:
                    text_cell.move(
                        (text_cell.xmin, text_cell.ymax),
                        ((ec_top.xmax - 80), (ec_top.ymin - 15)),
                    )

                bbox = die << gf.components.rectangle(
                    size=(
                        text_cell.xmax - text_cell.xmin + 2,
                        text_cell.ymax - text_cell.ymin + 2,
                    ),
                    layer=bbox_layer,
                )
                bbox.move(
                    (bbox.xmin, bbox.ymin), ((text_cell.xmin - 1, text_cell.ymin - 1))
                )

            # Add the structures to the json file
            if create_json:
                # Measure the EC
                mc1 = {"num_components": 2}
                for inst in route1.instances:
                    temp_dict = ipr.measure_component(inst.cell, scale=1 / 1000)
                    mc1 = ipr.combine_component_dict(mc1, temp_dict)

                if idx in [2, 3]:
                    for _ in range(2):
                        temp_dict = ipr.measure_component(sbend.cell, scale=1)
                        mc1 = ipr.combine_component_dict(mc1, temp_dict)

                mc = {}
                for key in mc1.keys():
                    mc[key] = [mc1[key]]

                # Create json file
                moke_component = gf.Component(f"POL_SCHEME_{idx + 1}")
                json_writer.structure_json(
                    component=moke_component,
                    component_IO=ec,
                    structure_title=f"TS{ts}",
                    structure=ec,
                    polarization=["te", "tm"],
                    propagation_mode=["te", "tm"],
                    extra_dict={
                        "nepoxy": [1, 1.428],
                        "design_id": design_id,
                        "dut_type": "pbs_psr_prc_pbs",
                        "analysis": ["il_db"],
                        "edge_coupler": [f"{ec.name}"] * 2,
                        "cutback": mc,
                    },
                )

    ##################################
    # 16.0 TM CUTBACK TEST STRUCTURE #
    ##################################
    if len(structure_only) == 0 or 16 in structure_only:
        print("\nCreation of N.16 TM Cutback Test Structure")

        ts_base = "16"

        # Place EC on top
        edge_margin_right_top = 13575
        edge_margin_right_bot = 13532.5
        for idx in range(3):
            ts = f"{ts_base}.{idx + 1}"
            # Place EC on top
            ec_top = die << ec
            ec_top.rotate(-90)
            ec_top.ymax = die_ymax - edge_margin_top
            ec_top.xmax = die.xmax - edge_margin_right_top

            vt_top = die << vt_pi
            vt_top.connect("o2", ec_top["o1"])

            strt_top = die << straight_410_swg(length=1)
            strt_top.connect("o1", vt_top["o1"])
            edge_margin_right_top += ec_pitch

            # Place EC on bot
            ec_bot = die << ec
            ec_bot.rotate(90)
            ec_bot.ymin = die_ymin + edge_margin_bot
            ec_bot.xmax = die.xmax - edge_margin_right_bot

            vt_bot = die << vt_pi
            vt_bot.connect("o2", ec_bot["o1"])

            strt_bot = die << straight_410_swg(length=1)
            strt_bot.connect("o1", vt_bot["o1"])
            edge_margin_right_bot += ec_pitch

            # Routing of the central : VT TM
            bend_radius = 10
            if idx == 0:
                # Use normal routing
                strt = straight_410_swg
                steps = []
                for _ in range(14):
                    steps.extend(
                        [
                            {"dy": 90},
                            {"dx": -3 * bend_radius},
                            {"dy": 90},
                            {"dx": 3 * bend_radius},
                        ]
                    )
                steps.pop(-1)
                steps.pop(-1)
                steps[-1] = {"x": vt_top["o1"].x}

                # Component to be used
                comp = straight_410_swg(length=0)

                # Text to be written
                text = "TM LOOP"
                analysis = "proptm_dbcm"

            elif idx == 1:
                # Create a straight of different vt
                kwargs_vt = {
                    "bb1": vt_pi,
                    "bb2": vt_pi,
                    "bb2_rev": True,
                    "straight": straight_700_anwg,
                    "straight_limited": straight_410_swg,
                }
                bb = gf.partial(ipr.bb_straight_bb, **kwargs_vt)
                comp = vt_pi

                kwargs_vt_strt = {
                    "bb": bb,
                    "bb_extra_length": 1.141,
                    "bb_extra_variation": 0.141,
                    "sep_distance": 1.141,
                    "sep_variation": 0.141,
                    "straight": straight_410_swg,
                }

                strt = gf.partial(ipr.nbb_straight, **kwargs_vt_strt)

                # Calculate the steps do be done
                steps = [{"dy": 175}]
                for _ in range(3):
                    steps.extend(
                        [
                            {"x": -1510},
                            {"dy": bend_radius * 2},
                            {"x": -1150},
                            {"dy": bend_radius * 2},
                        ]
                    )
                steps[-1] = {"dy": 100}

                for _ in range(10):
                    steps.extend(
                        [
                            {"dx": -3 * bend_radius},
                            {"dy": 105},
                            {"dx": 3 * bend_radius},
                            {"dy": 105},
                        ]
                    )
                steps.append({"x": vt_top["o1"].x})

                # Text to be written
                text = "TM VT PI"
                analysis = "iltm_db"

            # Routing of the longest : Strip TM
            elif idx == 2:
                # Use normal routing
                strt = straight_410_swg
                comp = straight_410_swg(length=0)

                # Initial step to go lateral to the EC
                steps = [{"dy": 150}, {"dx": -100}, {"dy": -550}]

                # Steps to go up for n times
                for _ in range(12):
                    steps.extend(
                        [
                            {"x": -2780},
                            {"dy": bend_radius * 2},
                            {"x": -1370},
                            {"dy": bend_radius * 2},
                        ]
                    )
                steps[16] = {"dy": 200}
                steps[28] = {"dy": 280}
                steps[40] = {"dy": 200}

                # Steps to go on top
                steps.extend([{"x": -2780}, {"y": -600}, {"x": vt_top["o1"].x}])

                # Text to be written
                text = "TM SWG 410"
                analysis = "proptm_dbcm"

            route = gf.routing.route_single(
                die,
                port1=vt_bot["o1"],
                port2=vt_top["o1"],
                cross_section=xs_swg,
                straight=strt,
                bend=routing_bend_Si_TM,
                auto_taper=False,
                steps=steps,
            )

            # Add text TOP and BOT
            for jdx in range(2):
                text = (f"{ts} " + text).upper()

                text_cell = die << ipr.text(
                    text, size=text_size, layer=LAYER.metal3, justify="center"
                )
                text_cell.rotate(90)
                if jdx % 2 == 0:
                    text_cell.move(
                        (text_cell.xmin, text_cell.ymin),
                        ((ec_bot.xmax - 80), (ec_bot.ymax + 15)),
                    )
                else:
                    text_cell.move(
                        (text_cell.xmin, text_cell.ymax),
                        ((ec_top.xmax - 80), (ec_top.ymin - 15)),
                    )

                bbox = die << gf.components.rectangle(
                    size=(
                        text_cell.xmax - text_cell.xmin + 2,
                        text_cell.ymax - text_cell.ymin + 2,
                    ),
                    layer=bbox_layer,
                )
                bbox.move(
                    (bbox.xmin, bbox.ymin), ((text_cell.xmin - 1, text_cell.ymin - 1))
                )

            # Add the structures to the json file
            if create_json:
                # Measure the EC
                mc1 = {}
                for inst in route.instances:
                    scale = 1 / 1000

                    if "410_swg" in inst.name:
                        scale /= 10000
                    temp_dict = ipr.measure_component(inst.cell, scale=scale)
                    mc1 = ipr.combine_component_dict(mc1, temp_dict)

                for _ in range(2):
                    temp_dict = ipr.measure_component(vt_pi)
                    mc1 = ipr.combine_component_dict(mc1, temp_dict)

                mc = {}
                for key in mc1.keys():
                    mc[key] = [mc1[key]]

                # Create json file
                json_writer.structure_json(
                    component=comp,
                    component_IO=ec,
                    structure_title=f"TS{ts}",
                    structure=ec,
                    polarization=["tm"],
                    propagation_mode=["tm"],
                    extra_dict={
                        "nepoxy": [1, 1.428],
                        "analysis": [analysis],
                        "edge_coupler": [f"{ec.name}"] * 2,
                        "cutback": mc,
                    },
                )

    ######################
    # 17.0 BEND VARIANTS #
    ######################
    if len(structure_only) == 0 or 17 in structure_only:
        print("\nCreation of N.17 Bend Variants Test Structure")

        n_bbs = [625, 625 * 2, 625 * 3, 625 * 4]
        ts_base = "17"
        n_cloth = 0
        for idx in range(len(doe_json_dict[f"{ts_base}.0"]["comp"])):
            n_cloth += 1
            ts = f"{ts_base}.{1 + idx}"

            # Select the clothoide bend from the DoE file
            comp = sim_filename_json[doe_json_dict[f"{ts_base}.0"]["comp"][idx]]
            name = comp["function"].split(".")[-1].rstrip("()")
            func = eval(name)
            cloth_ref = func(**comp["settings"])

            # Create clothoide bend straight
            clothoid_straight, clothoid_kwargs = from_clothoid_to_straights(
                component=cloth_ref
            )

            # Create test structure
            t = die << ipr.test_serpentines_from_calculation(
                bend=routing_bend_Si,
                blocks_distance=(15, 10),
                block_gc_distance=30,
                gc_array=gc_array_te,
                max_height=1100,
                straight=clothoid_straight,
                lengths=clothoid_kwargs,
                n_bbs=n_bbs,
                separations=15,
                n_rows_pitch=7,
                separations_pitch=35,
                straight_route=routing_strt,
                structure_4_blocks="hor",
            )

            # Assign to the dictionary
            structures[ts] = t
            structures_text[ts] = f"{ts} {comp['design_id']}"

            # Add the structures to the json file
            if create_json:
                json_writer.structure_json(
                    component=cloth_ref,
                    component_IO=gc_array_te,
                    structure_title=f"TS{ts}",
                    structure=t.cell,
                )

        for idx in range(len(doe_json_dict[f"{ts_base}.1"]["comp"])):
            if idx == 2:
                n_bbs = [1500, 1500 * 2, 1500 * 3, 1500 * 4]
            else:
                n_bbs = [2500, 2500 * 2, 2500 * 3, 2500 * 4]

                # Select the clothoide bend from the DoE file
            comp = sim_filename_json[doe_json_dict[f"{ts_base}.1"]["comp"][idx]]
            name = comp["function"].split(".")[-1].rstrip("()")
            func = getattr(ipr, name)
            bend_ref = func(**comp["settings"])

            # Calculate the size of the bends involved
            bend_rotate = bend_ref.copy()
            beta_half = routing_bend_Si_inv if idx == 2 else routing_half_bend_Si
            beta = beta_half["o2"].orientation
            bend_rotate.rotate(beta)
            bend_sep_size = abs(np.round(1 * np.cos(beta * np.pi / 180), 3))
            bend_io_size = beta_half["o2"].x - beta_half["o1"].x

            # Feature to be used for the bends
            feature_bend = {
                "straight": straight_410_swg,
                "sep_distance": 1.141,
                "sep_variation": 0.141,
                "bb": bend_ref,
                "bb_io": beta_half,
                # For length calculations
                "2_bb": bend_rotate,
                "2_io_length": bend_io_size,
                "2_sep_distance": bend_sep_size,
                "2_bb_extra_length": bend_sep_size,
            }

            # Create straight for bends
            bend_strt = gf.partial(ipr.nbends_angled_straight, **feature_bend)

            # Create the test structure
            ts = f"{ts_base}.{idx + 1 + n_cloth}"

            t = die << ipr.test_serpentines_from_calculation(
                bend=routing_bend_Si,
                blocks_distance=(15, 10),
                block_gc_distance=30,
                gc_array=gc_array_te,
                max_height=1150,
                straight=bend_strt,
                lengths=feature_bend,
                n_bbs=n_bbs,
                separations=15 if idx == 2 else 0,
                n_rows_pitch=8,
                separations_pitch=30,
                straight_route=routing_strt,
                structure_4_blocks="2x2",
            )

            # Assign to the dictionary
            structures[ts] = t
            structures_text[ts] = f"{ts} {name}"

            # Json Part
            if create_json:
                json_writer.structure_json(
                    component=bend_ref,
                    component_IO=gc_array_te,
                    structure_title=f"TS{ts}",
                    structure=t.cell,
                    extra_dict={"analysis": ["ilte_dbcm"]},
                )

    ##################
    # 18.0 SiN2 Bend #
    ##################
    if len(structure_only) == 0 or 18 in structure_only:
        print("\nCreation of N.18 Insertion Loss SiN2 Bend 90° Test Structure")

        n_bbs = [500, 1000, 1500, 2000]
        ts_base = "18"

        # Create the test structure
        for idx in range(len(doe_json_dict[f"{ts_base}.0"]["comp"])):
            ts = f"{ts_base}.{1 + idx}"

            # Select the SiN2 from the DoE file
            comp = sim_filename_json[doe_json_dict[f"{ts_base}.0"]["comp"][idx]]
            name = comp["function"].split(".")[-1].rstrip("()")
            func = getattr(ipr, name)
            bend_SiN2 = func(**comp["settings"])

            # Create a taper for it
            comp_taper = sim_filename_json[doe_json_dict[f"{ts_base}.0"]["taper"][idx]]
            name_taper = comp_taper["function"].split(".")[-1].rstrip("()")
            func_taper = getattr(ipr, name_taper)
            taper_DoE = func_taper(**comp_taper["settings"])

            bend_with_taper_kwargs = {
                "bbmul": bend_SiN2,
                "bbadd": taper_DoE,
                "bbmul_list": ["o1", "o2"],
            }

            # Create a bend with taper included
            bend_DoE = ipr.bb_mul_bb(**bend_with_taper_kwargs)

            bend_io = ipr.bend_euler(
                cross_section=xs_anwg_2000, radius=comp["settings"]["radius"], angle=-45
            )

            # Calculate the size of the bends involved
            bend_rotate = bend_DoE.copy()
            beta = bend_io["o2"].orientation
            bend_rotate.rotate(beta)
            bend_sep_size = 1.141 * np.cos(beta * np.pi / 180)
            bend_io_size = bend_io["o2"].x - bend_io["o1"].x

            # Routing bend + straight
            feature_vtstraight = {
                "bbmul": vt_opt_te,
                "bbadd": straight_410_swg(0.5),
                "bbmul_list": ["o1"],
            }
            vt_with_straight = ipr.bb_mul_bb(**feature_vtstraight)

            # Feature to be used for the bends
            feature_bend = {
                "straight": ipr.nbends_angled_straight,
                "bb1": vt_with_straight,
                "bb2": vt_with_straight,
                "bb2_rev": True,
                "1_straight": straight_2000_anwg,
                "1_sep_distance": 1.141,
                "1_sep_variation": 0.141,
                "1_bb": bend_DoE,
                "1_bb_io": bend_io,
                # For length calculations
                "2_bb": bend_rotate,
                "2_io_length": bend_io_size,
                "2_sep_distance": bend_sep_size,
                "2_bb_extra_length": bend_sep_size,
            }

            # Create straight for bends
            bend_strt = gf.partial(ipr.bb_straight_bb, **feature_bend)

            t = die << ipr.test_serpentines_from_calculation(
                bend=routing_bend_Si,
                blocks_distance=(15, 5),
                block_gc_distance=30,
                gc_array=gc_array_te,
                max_height=1120,
                straight=bend_strt,
                lengths=feature_bend,
                n_bbs=n_bbs,
                separations=10.5,
                separations_pitch=40,
                n_rows_pitch=10,
                straight_route=routing_strt,
                structure_4_blocks="2x2",
            )

            # Assign to the dictionary
            structures[ts] = t
            structures_text[ts] = f"R{ts} ANWG BEND"

            # Json Part
            if create_json:
                json_writer.structure_json(
                    component=bend_SiN2,
                    component_IO=gc_array_te,
                    structure_title=f"TS{ts}",
                    structure=t.cell,
                    extra_dict={"analysis": ["ilte_dbcm"]},
                )

    ############
    # 19.0 TLM #
    ############
    if len(structure_only) == 0 or 19 in structure_only:
        print("\nCreation of N.19 Transfer Length Method Test Structure")
        ts = 19

        # Electrical pad where to start placing the TLM
        minimum_pad = 6

        # Length used for the TLM
        lengths = [10, 20, 40, 80]
        contact_width = xs_metal1_narrow.width

        # P++ and N++ TLM structure
        for jdx in range(2):
            tlm_ref = die << tlm_linear(
                lengths_array=lengths,
                layer=LAYER.cpi if jdx == 0 else LAYER.cni,
                contact_width=contact_width,
            )

            # Place in place
            tlm_ref.rotate(-90)
            center_pad = (len(lengths) + 1) // 2
            tlm_ref.x = pad_array_tlm[center_pad + minimum_pad].x - 120
            tlm_ref.movey(
                tlm_ref[f"e{center_pad + 1}"].y,
                pad_array_tlm[center_pad + minimum_pad].y,
            )

            # Calculate the length to have 45 degree metal
            length = abs(tlm_ref["e1"].width - xs_metal1.width) / 2

            for idx in range(len(lengths) + 1):
                # Select the port
                tlm_port = tlm_ref[f"e{idx + 1}"]

                # Place the taper
                straight = die << ipr.straight(
                    length=10, cross_section=xs_metal1_narrow
                )
                straight.connect("e1", tlm_port, allow_type_mismatch=True)

                # Place the first via
                via1 = die << ipr.via_metal1_metal3(size=(contact_width, contact_width))
                via1.connect(
                    "e1",
                    straight["e2"],
                    allow_layer_mismatch=True,
                    allow_width_mismatch=True,
                )

                # Route to the pad
                gf.routing.route_single(
                    die,
                    via1["e3"],
                    pad_array_tlm[idx + minimum_pad],
                    port_type="electrical",
                    auto_taper=False,
                    allow_width_mismatch=True,
                    cross_section=xs_metal3_narrow,
                    start_straight_length=40 - abs(idx - center_pad) * 15,
                    bend="wire_corner45",
                    radius=xs_metal3_narrow.width / 2,
                )

            # Update minimum pad for next iteration
            minimum_pad += center_pad + len(lengths) - 1

            # Place Text information
            text = f"{ts}.1 \n TLM P++" if jdx == 0 else f"{ts}.2 \n TLM N++"
            txt = die << ipr.text(text, size=20, layer=LAYER.metal3, justify="center")
            txt.rotate(90)
            txt.move(
                (txt.x, txt.y),
                (tlm_ref.x - 15, tlm_ref.y + 170),
            )
            rec = die << gf.c.rectangle(
                size=(txt.xsize + 10, txt.ysize + 10), layer=(118, 40)
            )
            rec.xmin = txt.xmin - 5
            rec.ymin = txt.ymin - 5

    #####################
    # 20.0 TIME SHARING #
    #####################
    if len(structure_only) == 0 or 20 in structure_only:
        print("\nCreation of N.20 Time Sharing Test Structure")
        ts = 20
        for idx in range(ec_amount_left):
            # Place the left edge couplers
            ec_left = die << ec
            ec_left.xmin = die.xmin + die_edge_hor
            ec_left.y = (
                die.y + (idx - ec_amount_left / 2) * ec_pitch_PUC + ec_pitch_PUC / 2
            )

            # Place polarization insensitive vertical transition
            if idx > 1 and idx < ec_amount_left - 2:
                vt = die << vt_pi
                vt.connect("o2", ec_left["o1"])
                ec_left_ports.append(vt.ports["o1"])
            else:
                tp = die << ipr.rib_taper(
                    length=24.975,
                    width_RIB_in=0.7,
                    width_RIB_out=1.784,
                    m_RIB=0.578,
                    cross_section="nitride2",
                )
                tp.connect("o1", ec_left["o1"])
                ec_left_ports.append(tp["o2"])

        # Create the trench rectangle at the edge
        dx = 65
        dy = ec_left_ports[-1].y - ec_left_ports[0].y + 460
        lateral_trench = die << gf.c.rectangle(size=(dx, dy), layer=LAYER.scrbo)
        lateral_trench.xmin = die.xmin + 10
        lateral_trench.y = die_y_center

        # Bend for the looping
        comp = sim_filename_json[doe_json_dict["18.0"]["comp"][1]]
        name = comp["function"].split(".")[-1].rstrip("()")
        func = getattr(ipr, name)
        bend = func(**comp["settings"])

        # Create a bend with taper included
        for idx in range(2):
            gf.routing.route_single(
                die,
                port1=ec_left_ports[0 + (ec_amount_left - 2) * idx],
                port2=ec_left_ports[1 + (ec_amount_left - 2) * idx],
                cross_section=xs_anwg_1784,
                bend=bend,
                auto_taper=False,
            )

        # Center index of the structure
        ec_center = ec_amount_left // 2

        # Place the pad array on top left
        pad_array_left_top = die << pad_ay_left
        pad_array_left_top.xmin = die.xmin + die_edge_hor + pad_left_edge_distance
        pad_array_left_top.ymax = die.ymax - die_edge_ver
        pad_left_top_ports += [
            pad_array_left_top.ports[f"e1{idx + 1}"]
            for idx in range(pad_left_amount_per_row)
        ]

        pad_array_left_top = die << pad_ay_left_d
        pad_array_left_top.xmin = (
            die.xmin + die_edge_hor + pad_left_edge_distance + pad_left_pitch_hor / 2
        )
        pad_array_left_top.ymax = die.ymax - die_edge_ver - pad_left_pitch_ver
        pad_left_top_ports += [
            pad_array_left_top.ports[f"e1{idx + 1}"]
            for idx in range(pad_left_amount_per_row - 1)
        ]

        # Place the pad array on bot left
        pad_array_left_bot = die << pad_ay_left
        pad_array_left_bot.rotate(180)
        pad_array_left_bot.mirror_x()
        pad_array_left_bot.xmin = die.xmin + die_edge_hor + pad_left_edge_distance
        pad_array_left_bot.ymin = die.ymin + die_edge_ver
        pad_left_bot_ports += [
            pad_array_left_bot.ports[f"e1{idx + 1}"]
            for idx in range(pad_left_amount_per_row)
        ]

        pad_array_left_bot = die << pad_ay_left_d
        pad_array_left_bot.rotate(180)
        pad_array_left_bot.mirror_x()
        pad_array_left_bot.xmin = (
            die.xmin + die_edge_hor + pad_left_edge_distance + pad_left_pitch_hor / 2
        )
        pad_array_left_bot.ymin = die.ymin + die_edge_ver + pad_left_pitch_ver
        pad_left_bot_ports += [
            pad_array_left_bot.ports[f"e1{idx + 1}"]
            for idx in range(pad_left_amount_per_row - 1)
        ]

        # Shuffle the array
        pad_left_top_ports_ = [
            x
            for pair in zip(
                pad_left_top_ports[: pad_left_amount_per_row - 1],
                pad_left_top_ports[pad_left_amount_per_row:],
            )
            for x in pair
        ]
        pad_left_top_ports_ = pad_left_top_ports_ + [
            pad_left_top_ports[-pad_left_amount_per_row]
        ]

        pad_left_bot_ports_ = [
            x
            for pair in zip(
                pad_left_bot_ports[: pad_left_amount_per_row - 1],
                pad_left_bot_ports[pad_left_amount_per_row:],
            )
            for x in pair
        ]
        pad_left_bot_ports_ = pad_left_bot_ports_ + [
            pad_left_bot_ports[-pad_left_amount_per_row]
        ]

        tri = die << triangle
        tri.xmin = -12450
        tri.ymin = -1840

        # Add a straight to the array to avoid slot - pad intersection
        pad_left_top_ports = []
        pad_left_bot_ports = []
        for kdx, ports in enumerate([pad_left_top_ports_, pad_left_bot_ports_]):
            for idx, port in enumerate(ports):
                if idx not in [14]:
                    # Chose cross section
                    if idx in [0, 1, 2, 3]:
                        cross_section = xs_metal3_wides[3 - idx]
                    elif idx in [17, 18]:
                        cross_section = xs_metal3_wides[-1]
                    else:
                        cross_section = xs_metal3

                    # Place the straight
                    strt = die << ipr.fast_straight(
                        length=80.001, cross_section=cross_section
                    )

                    # Place in correct position
                    if idx == 17:
                        if kdx == 0:
                            strt.rotate(90)
                            strt.ymin = port.y
                        else:
                            strt.rotate(-90)
                            strt.ymax = port.y
                        strt.x = port.x
                    else:
                        strt.connect("e1", port, allow_width_mismatch=True)

                    # Append the new port
                    if kdx == 0:
                        pad_left_top_ports.append(strt["e2"])
                    else:
                        pad_left_bot_ports.append(strt["e2"])
                else:
                    if kdx == 0:
                        pad_left_top_ports.append(port)
                    else:
                        pad_left_bot_ports.append(port)

        # Connect two pads for calculating resistance
        for idx in range(2):
            if idx == 0:
                port1 = pad_left_top_ports[17]
                port2 = pad_left_top_ports[18]
            else:
                port1 = pad_left_bot_ports[17]
                port2 = pad_left_bot_ports[18]

            gf.routing.route_single(
                die,
                port1=port1,
                port2=port2,
                cross_section=xs_metal3_wides[-1],
                bend=gf.c.wire_corner45,
                radius=xs_metal3_wides[-1].width / 2,
                auto_taper=False,
                port_type="electrical",
                allow_width_mismatch=True,
                start_straight_length=50,
                straight=gf.partial(
                    straight_with_slots, cross_section=xs_metal3_wides[-1]
                ),
            )

            # Place the straight
            strt = die << ipr.fast_straight(length=80, cross_section=xs_metal3)

            # Position the straight
            if idx == 0:
                strt.rotate(-90)
                strt.ymin = port1.y - 160
                strt.x = port1.x
                pad_left_top_ports[17] = strt["e2"]
            else:
                # Place the straight
                strt.rotate(90)
                strt.ymax = port1.y + 160
                strt.x = port1.x
                pad_left_bot_ports[17] = strt["e2"]

        # Puc generation
        puc = v7a_PUC_from_gds(name="v7a_T2_PUC_03_design0_ts")
        puc = gf.partial(puc_with_diode, puc, diode)

        # Insert the mesh
        benes = die << dilated_benes(
            order=8,
            extra_stages=0,
            crossing=crossing_2D,
            puc=puc,
            bend=routing_bend_Si,
            taper=taper_410_930,
            cross_section=xs_swg_410,
            optical_routing_spacing=10 - 3.91,
            distance_y=70.0,
            size_x_cross_matrix_array=[410, 410, 410],
            distance_cross=31,
            transition_output=False,
        )

        # Move in wanted position
        benes.x = ec_left.x + 1375
        benes.movey(origin=benes["o7"].y, destination=ec_left_ports[ec_center].y)

        # Add 4 PUCS at the end of the benes
        o_benes_ports = []
        o_benes_ports_abs = []
        e1_benes_ports = []
        e2_benes_ports = []
        e3_benes_ports = []
        e4_benes_ports = []
        for idx in range(4):
            puc_ref = die << puc()
            puc_ref.movex(puc_ref["o3"].x, benes[f"o{4 * idx + 17}"].x + 315)
            puc_ref.movey(
                puc_ref["o3"].y,
                (benes[f"o{4 * idx + 17}"].y + benes[f"o{4 * idx + 19}"].y) / 2,
            )

            # Route the mesh to the PUCS
            gf.routing.route_single(
                auto_taper=False,
                bend=routing_bend_Si,
                component=die,
                cross_section=xs_swg,
                port1=puc_ref["o2"],
                port2=benes[f"o{4 * idx + 17}"],
                straight=routing_strt,
            )

            gf.routing.route_single(
                auto_taper=False,
                bend=routing_bend_Si,
                component=die,
                cross_section=xs_swg,
                port1=puc_ref["o1"],
                port2=benes[f"o{4 * idx + 19}"],
                straight=routing_strt,
            )

            # Add the PUC optical ports
            o_benes_ports_abs.append(benes[f"o{4 * idx + 18}"])
            o_benes_ports_abs.append(benes[f"o{4 * idx + 20}"])
            if idx == 0 or idx == 3:
                o_benes_ports.append(puc_ref["o3"])
                o_benes_ports.append(puc_ref["o4"])
            elif idx == 1:
                o_benes_ports.append(puc_ref["o3"])
                o_benes_ports_abs.append(puc_ref["o4"])
            else:
                o_benes_ports.append(puc_ref["o4"])
                o_benes_ports_abs.append(puc_ref["o3"])

            # Add the PUC electrical ports
            e1_benes_ports.append(puc_ref["e1"])
            e2_benes_ports.append(puc_ref["e2"])
            e3_benes_ports.append(puc_ref["e3"])
            e4_benes_ports.append(puc_ref["e4"])

        # Insert the small mesh
        benes_small = die << dilated_benes(
            order=2,
            extra_stages=0,
            crossing=crossing_2D,
            puc=puc,
            bend=routing_bend_Si,
            taper=taper_410_930,
            cross_section=xs_swg_410,
            optical_routing_spacing=10 - 3.91,
            distance_y=78.5,
            size_x_cross_matrix_array=[800],
            distance_cross=31,
            transition_output=False,
        )
        benes_small.rotate(-90)

        # Move small mesh in position
        benes_small.xmin = benes.xmax + 685
        benes_small.y = benes.y

        # Select input optical port
        i_benes_ports = [
            benes.ports[f"o{idx + 1}"] for idx in reversed(range(16)) if idx % 2 == 0
        ]
        i_benes_ports_abs = [
            benes.ports[f"o{idx + 1}"] for idx in reversed(range(16)) if idx % 2 == 1
        ]
        i_benes_small_port = [
            benes_small.ports[f"o{idx + 1}"]
            for idx in reversed(range(4))
            if idx % 2 == 0
        ]
        o_benes_small_port = [
            benes_small.ports[f"o{idx + 5}"] for idx in range(4) if idx % 2 == 0
        ]

        # Optical connect the mesh input
        gf.routing.route_bundle(
            auto_taper=False,
            bend=routing_bend_Si,
            component=die,
            cross_section=xs_swg,
            ports1=i_benes_ports,
            ports2=ec_left_ports[ec_center - 4 : ec_center + 4],
            straight=routing_strt,
            separation=30,
        )

        # Optical connect the mesh output top part
        gf.routing.route_bundle(
            auto_taper=False,
            bend=routing_bend_Si,
            component=die,
            cross_section=xs_swg,
            ports1=o_benes_ports[:3],
            ports2=ec_left_ports[ec_center + 4 : ec_center + 7],
            straight=routing_strt,
            separation=50,
        )

        # Optical connect the mesh output bot part
        gf.routing.route_bundle(
            auto_taper=False,
            bend=routing_bend_Si,
            component=die,
            cross_section=xs_swg,
            ports1=o_benes_ports[3:],
            ports2=ec_left_ports[ec_center - 7 : ec_center - 4],
            straight=routing_strt,
            separation=50,
        )

        # Add absorber if port is not connected
        abs_idx = 0
        for ports_abs in [i_benes_ports_abs, o_benes_ports_abs]:
            for port in ports_abs:
                if port.port_type == "optical":
                    ref_abs = die << absorber

                    if abs_idx in [0, 1, 2, 3, 4, 5, 6, 7, 15]:
                        ref_abs.mirror_y()
                    abs_idx += 1
                    ref_abs.connect("o1", port)

        # Optical connect the smaller mesh top
        gf.routing.route_bundle(
            auto_taper=False,
            bend=routing_bend_Si,
            component=die,
            cross_section=xs_swg,
            ports1=i_benes_small_port,
            ports2=ec_left_ports[ec_center + 7 : ec_center + 9],
            straight=routing_strt,
            separation=50,
        )

        # Optical connect the smaller mesh top
        gf.routing.route_bundle(
            auto_taper=False,
            bend=routing_bend_Si,
            component=die,
            cross_section=xs_swg,
            ports1=o_benes_small_port,
            ports2=ec_left_ports[ec_center - 9 : ec_center - 7],
            straight=routing_strt,
            separation=50,
        )

        # Add absorber to the smaller mesh
        for port in benes_small.ports:
            if port not in o_benes_small_port and port not in i_benes_small_port:
                if port.port_type == "optical":
                    ref_abs = die << absorber
                    if int(port.name.replace("o", "")) < 5:
                        ref_abs.mirror_y()

                    ref_abs.connect("o1", port)

        # #####################
        # # COLUMN SELECTOR 1 #
        # #####################
        # Select electrical port
        e3_benes_ports_top = [
            benes.ports[f"puc{idx}_bot_e3"] for idx in range(32) if idx % 8 < 4
        ]
        e3_benes_ports_bot = [
            benes.ports[f"puc{idx}_bot_e3"] for idx in range(32) if idx % 8 > 3
        ]
        e3_benes_ports_top.extend(e3_benes_ports[0:2])
        e3_benes_ports_bot.extend(e3_benes_ports[2:4])

        # Rotate the port
        puc_rout_dist = 20
        idx = 0
        for ports in [e3_benes_ports_top, e3_benes_ports_bot]:
            for port in ports:
                # Create a straight going right
                strt = die << straight_with_slots(
                    length=puc_rout_dist, cross_section=xs_metal3
                )
                strt.connect("e1", port)

                if idx < 18:
                    val_idx = idx // 4 + 1
                else:
                    val_idx = 13 - (idx - 2) // 4
                die.add_label(
                    text=f"PWM{val_idx}",
                    position=strt["e1"].center,
                    layer=xs_metal3.layer,
                )
                idx += 1

        # Metal3 routing
        for idx in range(5):
            # Position and dimension of the big metal 3 top part
            if idx != 4:
                dy = e3_benes_ports_top[idx * 4].y - e3_benes_ports_top[idx * 4 + 3].y
                y = e3_benes_ports_top[idx * 4 + 3].y - xs_metal3.width / 2
                x = e3_benes_ports_top[idx * 4 + 3].x + puc_rout_dist
            else:
                dy = e3_benes_ports_top[idx * 4].y - e3_benes_ports_top[idx * 4 + 1].y
                y = e3_benes_ports_top[idx * 4 + 1].y - xs_metal3.width / 2
                x = e3_benes_ports_top[idx * 4 + 1].x + puc_rout_dist
            strt = die << straight_with_slots(length=dy, cross_section=xs_metal3)
            strt.rotate(90)
            strt.ymin = y
            strt.xmin = x
            die.add_label(
                text=f"PWM{idx + 1}", position=strt["e1"].center, layer=xs_metal3.layer
            )

            # Route to the PAD
            gf.routing.route_single(
                die,
                strt["e2"],
                pad_left_top_ports[idx * 2 + 4],
                cross_section=xs_metal3,
                bend=gf.c.wire_corner45,
                radius=xs_metal3.width / 2,
                auto_taper=False,
                start_straight_length=[700, 600, 750, 650, 850][idx],
                straight=gf.partial(straight_with_slots, cross_section=xs_metal3),
                port_type="electrical",
                allow_width_mismatch=True,
            )

            # Position and dimension of the big metal 3 bot part
            if idx != 4:
                dy = (
                    e3_benes_ports_bot[idx * 4].y
                    - e3_benes_ports_bot[idx * 4 + 3].y
                    - xs_metal3.width / 2
                )
                y = e3_benes_ports_bot[idx * 4].y + xs_metal3.width / 2
                x = e3_benes_ports_bot[idx * 4].x + puc_rout_dist
            else:
                dy = (
                    e3_benes_ports_bot[idx * 4].y
                    - e3_benes_ports_bot[idx * 4 + 1].y
                    - xs_metal3.width / 2
                )
                y = e3_benes_ports_bot[idx * 4].y + xs_metal3.width / 2
                x = e3_benes_ports_bot[idx * 4].x + +puc_rout_dist
            strt = die << straight_with_slots(length=dy, cross_section=xs_metal3)
            strt.rotate(90)
            strt.ymax = y
            strt.xmin = x
            die.add_label(
                text=f"PWM{9 - idx}", position=strt["e1"].center, layer=xs_metal3.layer
            )

            # Route to the PAD
            gf.routing.route_single(
                die,
                strt["e1"],
                pad_left_bot_ports[idx * 2 + 4],
                cross_section=xs_metal3,
                bend=gf.c.wire_corner45,
                radius=xs_metal3.width / 2,
                auto_taper=False,
                start_straight_length=[700, 570, 820, 720, 920][idx],
                straight=gf.partial(straight_with_slots, cross_section=xs_metal3),
                port_type="electrical",
                allow_width_mismatch=True,
            )

        # #####################
        # # COLUMN SELECTOR 2 #
        # #####################
        # Select electrical port
        e4_benes_ports_top = [
            benes.ports[f"puc{idx}_bot_e4"] for idx in range(32) if idx % 8 < 4
        ]
        e4_benes_ports_bot = [
            benes.ports[f"puc{idx}_bot_e4"] for idx in range(32) if idx % 8 > 3
        ]
        e4_benes_ports_top.extend(e4_benes_ports[0:2])
        e4_benes_ports_bot.extend(e4_benes_ports[2:4])

        # Rotate the port
        puc_rout_dist = 55
        idx = 0
        for ports in [e4_benes_ports_top, e4_benes_ports_bot]:
            for port in ports:
                # Create a straight going right
                strt = die << straight_with_slots(
                    length=puc_rout_dist, cross_section=xs_metal2
                )
                strt.connect("e1", port, allow_layer_mismatch=True)

                if idx < 18:
                    val_idx = idx // 4 + 1
                else:
                    val_idx = 13 - (idx - 2) // 4
                die.add_label(
                    text=f"PWM{val_idx}_d",
                    position=strt["e1"].center,
                    layer=xs_metal2.layer,
                )

                idx += 1

        # Metal2 routing
        for idx in range(5):
            # Position and dimension of the big metal 3 top part
            if idx != 4:
                dy = (
                    e4_benes_ports_top[idx * 4].y
                    - e4_benes_ports_top[idx * 4 + 3].y
                    + 50
                )
                y = e4_benes_ports_top[idx * 4 + 3].y - xs_metal3.width / 2
                x = e4_benes_ports_top[idx * 4 + 3].x + puc_rout_dist
            else:
                dy = (
                    e4_benes_ports_top[idx * 4].y
                    - e4_benes_ports_top[idx * 4 + 1].y
                    + 50
                )
                y = e4_benes_ports_top[idx * 4 + 1].y - xs_metal3.width / 2
                x = e4_benes_ports_top[idx * 4 + 1].x + puc_rout_dist
            strt = die << straight_with_slots(length=dy, cross_section=xs_metal2)
            strt.rotate(90)
            strt.ymin = y
            strt.xmin = x

            die.add_label(
                text=f"PWM{idx + 1}_d",
                position=strt["e1"].center,
                layer=xs_metal2.layer,
            )

            # Place the via to metal 3
            via_ref = die << via_2_3
            via_ref.connect(
                "e1", strt["e2"], allow_width_mismatch=True, allow_layer_mismatch=True
            )

            # Route to the via
            gf.routing.route_single(
                die,
                via_ref["e3"],
                pad_left_top_ports[idx * 2 + 5],
                cross_section=xs_metal3,
                bend=gf.c.wire_corner45,
                radius=xs_metal3.width / 2,
                auto_taper=False,
                start_straight_length=[620, 520, 670, 670, 870][idx],
                straight=gf.partial(straight_with_slots, cross_section=xs_metal3),
                port_type="electrical",
                allow_width_mismatch=True,
            )

            # Position and dimension of the big metal 3 bot part
            if idx != 4:
                dy = (
                    e4_benes_ports_bot[idx * 4].y
                    - e4_benes_ports_bot[idx * 4 + 3].y
                    + 15
                )
                y = e4_benes_ports_bot[idx * 4].y + xs_metal3.width / 2
                x = e4_benes_ports_bot[idx * 4].x + puc_rout_dist
            else:
                dy = (
                    e4_benes_ports_bot[idx * 4].y
                    - e4_benes_ports_bot[idx * 4 + 1].y
                    + 15
                )
                y = e4_benes_ports_bot[idx * 4].y + xs_metal3.width / 2
                x = e4_benes_ports_bot[idx * 4].x + puc_rout_dist
            strt = die << straight_with_slots(length=dy, cross_section=xs_metal2)
            strt.rotate(90)
            strt.ymax = y
            strt.xmin = x
            die.add_label(
                text=f"PWM{9 - idx}", position=strt["e1"].center, layer=xs_metal2.layer
            )

            # Place the via to metal 3
            via_ref = die << via_2_3
            via_ref.connect(
                "e1", strt["e1"], allow_width_mismatch=True, allow_layer_mismatch=True
            )

            # Route to the via
            gf.routing.route_single(
                die,
                via_ref["e3"],
                pad_left_bot_ports[idx * 2 + 5],
                cross_section=xs_metal3,
                bend=gf.c.wire_corner45,
                radius=xs_metal3.width / 2,
                auto_taper=False,
                start_straight_length=[585, 455, 655, 705, 905][idx],
                straight=gf.partial(straight_with_slots, cross_section=xs_metal3),
                port_type="electrical",
                allow_width_mismatch=True,
            )

        # ################
        # # ROW SELECTOR #
        # ################
        # Select electrical port
        e1_benes_ports_top = [benes.ports[f"puc{idx}_top_e1"] for idx in range(32)]
        e2_benes_ports_top = [benes.ports[f"puc{idx}_top_e2"] for idx in range(32)]
        e1_benes_ports_top.extend(e1_benes_ports[0:4])
        e2_benes_ports_top.extend(e2_benes_ports[0:4])

        # Create row selector in metal 2 above and below
        distance_metal_start = 50
        distance_pad = 50
        distance_metal = [83, 135, 187, 239]

        dwidth = []
        offset = 0
        for x in xs_metal3_wides:
            dwidth.append(offset)
            offset += x.width

        # TOP parts
        for idx in range(4):
            # Vias array to be filled
            vias_top = []
            for jdx in range(5):
                if idx < 2 or jdx != 4:
                    via_ref = die << via_2_3_large[idx]
                    via_ref.movey(
                        via_ref["e3"].y, benes.ymax + dwidth[idx] + distance_metal[idx]
                    )

                    via_ref.xmax = (
                        e2_benes_ports_top[idx].x
                        + jdx * 410
                        + -idx * distance_metal_start
                        - dwidth[idx]
                    )
                    if jdx > 0:
                        via_ref.xmax += dwidth[idx] + idx * distance_metal_start
                        via_ref.xmax -= distance_pad * idx
                    if jdx == 4:
                        via_ref.xmax -= 100
                    vias_top.append(via_ref)

                    # Connect diode to the via
                    port2 = e2_benes_ports_top[idx + jdx * 8]
                    gf.routing.route_single(
                        die,
                        via_ref["e4"],
                        port2,
                        cross_section=xs_metal3,
                        bend=gf.c.wire_corner45,
                        radius=xs_metal3.width / 2,
                        auto_taper=False,
                        port_type="electrical",
                        straight=gf.partial(
                            straight_with_slots, cross_section=xs_metal3
                        ),
                        allow_width_mismatch=True,
                    )

                    # Route to the PAD
                    if jdx == 0:
                        gf.routing.route_single(
                            die,
                            pad_left_top_ports[3 - idx],
                            via_ref["e2"],
                            cross_section=xs_metal3_wides[idx],
                            bend=gf.c.wire_corner45,
                            radius=xs_metal3_wides[idx].width / 2,
                            auto_taper=False,
                            start_straight_length=[242, 438, 30, 150][idx],
                            straight=gf.partial(
                                straight_with_slots, cross_section=xs_metal3_wides[idx]
                            ),
                            port_type="electrical",
                            allow_width_mismatch=True,
                        )

            # Connect with stragiht
            for jdx in range(len(vias_top) - 1):
                dx = vias_top[jdx + 1]["e1"].x - vias_top[jdx]["e3"].x

                strt_top = die << straight_with_slots(
                    length=dx, cross_section=xs_metal2_wides[idx]
                )
                strt_top.connect(
                    "e1",
                    vias_top[jdx + 1]["e1"],
                    allow_layer_mismatch=True,
                    allow_width_mismatch=True,
                )
                die.add_label(
                    text=f"CTRL{idx + 1}",
                    position=strt_top["e1"].center,
                    layer=xs_metal2.layer,
                )

            # BOT PART
            # Vias to change layer
            vias_bot = []
            for jdx in range(5):
                if idx > 1 or jdx != 4:
                    via_ref = die << via_2_3_large[idx]
                    via_ref.rotate(180)
                    via_ref.movey(
                        via_ref["e3"].y, benes.ymin - dwidth[idx] - distance_metal[idx]
                    )

                    via_ref.xmax = (
                        e2_benes_ports_top[idx].x
                        + jdx * 410
                        + -idx * distance_metal_start
                        - dwidth[idx]
                    )
                    if jdx > 0:
                        via_ref.xmax += dwidth[idx] + idx * distance_metal_start
                        via_ref.xmax -= distance_pad * idx

                    vias_bot.append(via_ref)

                    if jdx == 4:
                        extra_index = 2
                    else:
                        extra_index = 0

                    # Connect via to the via
                    port2 = e2_benes_ports_top[7 - idx + jdx * 8 - extra_index]

                    gf.routing.route_single(
                        die,
                        via_ref["e4"],
                        port2,
                        cross_section=xs_metal3,
                        bend=gf.c.wire_corner45,
                        radius=xs_metal3.width / 2,
                        auto_taper=False,
                        port_type="electrical",
                        straight=gf.partial(
                            straight_with_slots, cross_section=xs_metal3
                        ),
                        allow_width_mismatch=True,
                    )

                    # Route to the PAD
                    if jdx == 0:
                        gf.routing.route_single(
                            die,
                            pad_left_bot_ports[3 - idx],
                            via_ref["e2"],
                            cross_section=xs_metal3_wides[idx],
                            bend=gf.c.wire_corner45,
                            radius=xs_metal3_wides[idx].width / 2,
                            auto_taper=False,
                            start_straight_length=[364, 560, 152, 340][idx],
                            straight=gf.partial(
                                straight_with_slots, cross_section=xs_metal3_wides[idx]
                            ),
                            port_type="electrical",
                            allow_width_mismatch=True,
                        )

            # Connect with stragiht
            for jdx in range(len(vias_bot) - 1):
                dx = vias_bot[jdx + 1]["e3"].x - vias_bot[jdx]["e1"].x

                strt_bot = die << straight_with_slots(
                    length=dx, cross_section=xs_metal2_wides[idx]
                )
                strt_bot.connect(
                    "e2",
                    vias_bot[jdx]["e1"],
                    allow_layer_mismatch=True,
                    allow_width_mismatch=True,
                )
                die.add_label(
                    text=f"CTRL{idx + 1}",
                    position=strt_top["e1"].center,
                    layer=xs_metal2.layer,
                )

            # Connect top and bottom straight
            p_top_m2 = gf.Port(
                name="top_m2",
                center=vias_top[-1]["e3"].center,
                orientation=vias_top[-1]["e3"].orientation,
                width=xs_metal2_wides[0].width,
                layer=xs_metal2_wides[0].layer,
                port_type=vias_top[-1]["e3"].port_type,
            )

            p_bot_m2 = gf.Port(
                name="bot_m2",
                center=vias_bot[-1]["e1"].center,
                orientation=vias_bot[-1]["e1"].orientation,
                width=xs_metal2_wides[0].width,
                layer=xs_metal2_wides[0].layer,
                port_type=vias_bot[-1]["e1"].port_type,
            )

            gf.routing.route_single(
                die,
                p_top_m2,
                p_bot_m2,
                cross_section=xs_metal2_wides[idx],
                bend=gf.c.wire_corner45,
                radius=xs_metal2_wides[idx].width / 2,
                auto_taper=False,
                start_straight_length=[225, 355, 799, 937][idx],
                end_straight_length=100,
                straight=gf.partial(
                    straight_with_slots, cross_section=xs_metal2_wides[idx]
                ),
                port_type="electrical",
                allow_width_mismatch=True,
            )

        # #############################
        # # CONTROL SIGNAL SMALL MESH #
        # #############################
        # Select electrical port
        e1_benes_small = [
            benes_small.ports[f"puc{1}_top_e2"],
            benes_small.ports[f"puc{3}_top_e2"],
        ]
        e2_benes_small = [
            benes_small.ports[f"puc{0}_top_e2"],
            benes_small.ports[f"puc{2}_top_e2"],
        ]

        for idx in range(2):
            # Connect control signal top part
            gf.routing.route_single(
                die,
                e1_benes_small[idx],
                pad_left_top_ports[15],
                cross_section=xs_metal3,
                bend=gf.c.wire_corner45,
                radius=xs_metal3.width / 2,
                auto_taper=False,
                port_type="electrical",
                allow_width_mismatch=True,
                start_straight_length=20 - idx * 1.6,
                straight=gf.partial(straight_with_slots, cross_section=xs_metal3),
            )

            # Connect control signal bot part
            gf.routing.route_single(
                die,
                e2_benes_small[idx],
                pad_left_bot_ports[15],
                cross_section=xs_metal3,
                bend=gf.c.wire_corner45,
                radius=xs_metal3.width / 2,
                auto_taper=False,
                port_type="electrical",
                allow_width_mismatch=True,
                straight=gf.partial(straight_with_slots, cross_section=xs_metal3),
                steps=[
                    {"dy": 20 - idx * 1.6},
                    {"x": -9380},
                    {"y": -700},
                    {"x": pad_left_bot_ports[15].x},
                ],
            )

        # #########################
        # # ROW SIGNAL SMALL MESH #
        # #########################
        e3_benes_small = [
            benes_small.ports["puc1_bot_e3"],
            benes_small.ports["puc0_bot_e3"],
            benes_small.ports["puc3_bot_e3"],
            benes_small.ports["puc2_bot_e3"],
        ]
        e4_benes_small = [
            benes_small.ports["puc1_bot_e4"],
            benes_small.ports["puc0_bot_e4"],
            benes_small.ports["puc3_bot_e4"],
            benes_small.ports["puc2_bot_e4"],
        ]

        # Connect together PUCs
        for jdx in range(4):
            # Connect control signal bot part
            xs = xs_metal3 if jdx < 2 else xs_metal2
            puc_port1 = (
                e3_benes_small[2 * jdx] if jdx < 2 else e4_benes_small[2 * jdx - 4]
            )
            puc_port2 = (
                e3_benes_small[2 * jdx + 1] if jdx < 2 else e4_benes_small[2 * jdx - 3]
            )
            strt_length = 30 if jdx < 2 else 60
            gf.routing.route_single(
                die,
                puc_port1,
                puc_port2,
                cross_section=xs,
                bend=gf.c.wire_corner45,
                radius=xs.width / 2,
                auto_taper=False,
                port_type="electrical",
                allow_width_mismatch=True,
                start_straight_length=strt_length,
                straight=gf.partial(straight_with_slots, cross_section=xs_metal3),
            )

            # Create vias on the right to bypass the right trace
            via_ref = die << via_2_3
            if jdx < 2:
                via_ref.xmin = e3_benes_small[1].x + 60 + jdx * 26.35
                via_ref.ymin = e3_benes_small[1].y - jdx * 60
            else:
                via_ref.xmin = e3_benes_small[3].x + 60 + (jdx - 2) * 26.35
                via_ref.ymin = e3_benes_small[3].y - (jdx - 2) * 60

            # Final route to the pad
            if jdx < 2:
                port1 = via_ref["e2"]
                port2 = pad_left_top_ports[16 + jdx]
                s_straight_length = 180 + jdx * 90
            else:
                port1 = via_ref["e4"]
                port2 = pad_left_bot_ports[14 + jdx]
                s_straight_length = 250 + jdx * 30

            # Route to the pad
            gf.routing.route_single(
                die,
                port1,
                port2,
                cross_section=xs_metal3,
                bend=gf.c.wire_corner45,
                radius=xs_metal3.width / 2,
                auto_taper=False,
                port_type="electrical",
                allow_width_mismatch=True,
                start_straight_length=s_straight_length,
                straight=gf.partial(straight_with_slots, cross_section=xs_metal3),
            )

            # Route to the via
            dx = 54.5 if jdx % 2 == 0 else 113.37
            strt = die << straight_with_slots(length=dx, cross_section=xs_metal2)
            strt.connect("e1", via_ref["e1"], allow_layer_mismatch=True)

    #####################
    # 21.0 MULTICONTACT #
    #####################
    if len(structure_only) == 0 or 21 in structure_only:
        print("\nCreation of N.21 MultiContact Test Structure")

        # Connect everything with a single straight
        sr = die << ipr.straight(
            length=pad_array_multi[0].y - pad_array_multi[-1].y, cross_section=xs_metal1
        )
        sr.rotate(90)
        sr.x = pad_array_multi[0].x
        sr.ymax = pad_array_multi[0].y

        # Add via from M1 to M3
        for pad_multi in pad_array_multi:
            via = die << ipr.via_metal1_metal3(size=(xs_metal1.width, xs_metal1.width))
            via.x = pad_multi.x
            via.y = pad_multi.y

        # Add text
        text_info = die << ipr.text(
            "21.0 MULTICONTACT",
            size=text_size_puc,
            layer=LAYER.metal3,
            justify="center",
        )

        text_info.xmax = sr.xmin - 100
        text_info.ymin = -1650

        rec = die << gf.c.rectangle(
            size=(text_info.xsize + 10, text_info.ysize + 10), layer=(118, 40)
        )
        rec.xmin = text_info.xmin - 5
        rec.ymin = text_info.ymin - 5

    ####################################################################################################
    left_top_structure = ["17.1", "18.1"]
    left_cen_structure = ["17.2", "18.2"]
    left_bot_structure = ["17.3", "17.4", "17.5"]

    # Place only structure complain with structure_only
    if len(structure_only) != 0:
        left_top_structure = [
            s for s in left_top_structure if int(s.split(".")[0]) in structure_only
        ]
        left_cen_structure = [
            s for s in left_cen_structure if int(s.split(".")[0]) in structure_only
        ]
        left_bot_structure = [
            s for s in left_bot_structure if int(s.split(".")[0]) in structure_only
        ]

    # Make text capital
    structures_text = {k: v.upper() for k, v in structures_text.items()}

    # Move left top structures
    previous_x_min = die.xmin - min_gc_gc_distance + edge_margin_left
    previous_x_max = previous_x_min
    for structure_idx in left_top_structure:
        s = structures[structure_idx]
        s.xmin = previous_x_max + structure_to_structure_margin
        if (s.xmin - previous_x_min) < min_gc_gc_distance:
            s.xmin = previous_x_min + min_gc_gc_distance
        s.y = die_y_center + 2 * die_height_semi / 3
        previous_x_max = s.xmax
        previous_x_min = s.xmin

        # Write the text for those
        text_to_write = structures_text[structure_idx]
        if text_to_write.startswith("R"):
            text_to_write = text_to_write[1:]
            text = die << ipr.text(
                text_to_write, size=25, layer=LAYER.metal3, justify="center"
            )
            text.move((text.xmin, text.ymin), ((s.xmin + 85), (s.ymin - 15)))
        else:
            text = die << ipr.text(
                text_to_write, size=25, layer=LAYER.metal3, justify="center"
            )
            text.move((text.xmin, text.ymin), ((s.xmin + 85), (s.ymin - 35)))

        bbox = die << gf.components.rectangle(
            size=(text.xmax - text.xmin + 2, text.ymax - text.ymin + 2),
            layer=bbox_layer,
        )
        bbox.move((bbox.xmin, bbox.ymin), ((text.xmin - 1, text.ymin - 1)))

    # Move left cen structures
    previous_x_min = die.xmin - min_gc_gc_distance + edge_margin_left
    previous_x_max = previous_x_min
    for structure_idx in left_cen_structure:
        s = structures[structure_idx]
        s.xmin = previous_x_max + structure_to_structure_margin
        if (s.xmin - previous_x_min) < min_gc_gc_distance:
            s.xmin = previous_x_min + min_gc_gc_distance
        s.y = die_y_center
        previous_x_max = s.xmax
        previous_x_min = s.xmin

        # Write the text for those
        text_to_write = structures_text[structure_idx]
        if text_to_write.startswith("R"):
            text_to_write = text_to_write[1:]
            text = die << ipr.text(
                text_to_write, size=25, layer=LAYER.metal3, justify="center"
            )
            text.move((text.xmin, text.ymin), ((s.xmin + 85), (s.ymin - 20)))
        else:
            text = die << ipr.text(
                text_to_write, size=25, layer=LAYER.metal3, justify="center"
            )
            text.move((text.xmin, text.ymin), ((s.xmin + 85), (s.ymin - 35)))

        bbox = die << gf.components.rectangle(
            size=(text.xmax - text.xmin + 2, text.ymax - text.ymin + 2),
            layer=bbox_layer,
        )
        bbox.move((bbox.xmin, bbox.ymin), ((text.xmin - 1, text.ymin - 1)))

    # Move left bot structures
    previous_x_min = die.xmin - min_gc_gc_distance + edge_margin_left
    previous_x_max = previous_x_min
    for structure_idx in left_bot_structure:
        s = structures[structure_idx]
        s.xmin = previous_x_max + structure_to_structure_margin
        if (s.xmin - previous_x_min) < min_gc_gc_distance:
            s.xmin = previous_x_min + min_gc_gc_distance
        s.y = die_y_center - 2 * die_height_semi / 3
        previous_x_max = s.xmax
        previous_x_min = s.xmin

        # Write the text for those
        text = die << ipr.text(
            structures_text[structure_idx],
            size=text_size,
            layer=LAYER.metal3,
            justify="center",
        )
        text.move((text.xmin, text.ymin), ((s.xmin + 80), (s.ymin - 35)))

        bbox = die << gf.components.rectangle(
            size=(text.xmax - text.xmin + 2, text.ymax - text.ymin + 2),
            layer=bbox_layer,
        )
        bbox.move((bbox.xmin, bbox.ymin), ((text.xmin - 1, text.ymin - 1)))

    # Create the trench rectangle at the top/bottom
    if edge_margin_right_top != 3465:
        for idx in range(2):
            # Define parameter of the lateral trench
            extra_length = 105
            if idx == 0:
                dx = edge_margin_right_top - 3465 + extra_length * 2 - 21
            else:
                dx = edge_margin_right_bot - 3465 + extra_length * 2 - 21
            dy = 65
            lateral_trench = die << gf.c.rectangle(size=(dx, dy), layer=LAYER.scrbo)

            # Move the lateral trench in position
            if idx == 0:
                lateral_trench.ymax = die_ymax - 10
                lateral_trench.xmin = (
                    die_xmax - edge_margin_right_top - extra_length + 21
                )
            else:
                lateral_trench.ymin = die_ymin + 10
                lateral_trench.xmin = (
                    die_xmax - edge_margin_right_bot - extra_length + 21
                )

    # Convert and save the json for LAB
    json_writer.conversion_json_and_internal(sim_filename, die="DIE_T2")
    json_writer.save()
