import json

import gdsfactory as gf
import iprlayout_tower as ipr  # type: ignore
import numpy as np
from iprlayout_tower.tower_tech import LAYER  # type: ignore

from T1.pdk import (
    T1_dummy_adder,
    all_metal_text,
    change_port,
    component_with_transition,
    grating_array_test_structure,
    mmi_splitter_il_extractor,
    mzis_test_group_and_effective_index,
    straight_410_swg,
    straight_700_anwg,
    straight_930_swg,
    straight_1560_swg,
    straight_2000_anwg,
    straigth_with_3d_cross_shallow,
    straigth_with_3d_cross_strip,
    tps_410_swg_930_swg_lim,
    tps_410_swg_1560_swg_lim,
    triangle_round,
    xt_sin_function,
)


def component_placement(die: gf.Component) -> gf.Component:
    """
    This function places the components in the DIE
    """

    # Take the die component
    die = gf.get_component(die)

    # Activate the pdk
    pdk = ipr.get_pdk()
    pdk.activate()

    # Feature of the the die
    bbox_layer = (118, 40)
    die_height = die.ymax - die.ymin
    die_height_semi = die_height / 2
    die_y_center = (die.ymax + die.ymin) / 2
    die_y_max = die.ymax
    die_y_min = die.ymin
    die_x_min = die.xmin
    edge_margin = 120
    edge_margin_right = 50
    structure_to_structure_margin_top = 185
    structure_to_structure_margin_middle = 150
    structure_to_structure_margin_bot = 320
    min_gc_gc_distance = 200
    bb_variation = 0.141

    ##########################
    # CROSS SECTIONS CONTROL #
    ##########################

    # Cross Section Definitions
    xs_swg = gf.get_cross_section("strip")
    xs_swg_410 = gf.get_cross_section("strip", width=0.41)
    xs_swg_930 = gf.get_cross_section("strip", width=0.93)
    xs_nwg_1000 = gf.get_cross_section("nitride", width=1.00)
    xs_awng_1500 = gf.get_cross_section("nitride2", width=1.50)
    xs_awng_2000 = gf.get_cross_section("nitride2", width=2.00)

    #####################
    # COMPONENT CONTROL #
    #####################
    # Si
    routing_bend_Si = ipr.bend_euler_custom_width(cross_section="strip")
    routing_bend_Si_TM = ipr.bend_euler_custom_width(cross_section="strip", radius=10)
    routing_half_bend_Si = ipr.bend_euler_custom_width(cross_section="strip", angle=-45)
    taper_410_930 = ipr.rib_taper(cross_section=xs_swg, width_RIB_out=0.93)
    taper_410_1560 = ipr.rib_taper(cross_section=xs_swg, width_RIB_out=1.56)
    taper_1560_410 = ipr.rib_taper(
        length=2, cross_section=xs_swg, width_RIB_in=1.560, width_RIB_out=0.41
    )
    taper_1560_410.function_name = "no_measure"

    routing_kwargs = {"bb1": taper_410_930}
    routing_strt = gf.partial(tps_410_swg_930_swg_lim, **routing_kwargs)

    routing_kwargs = {"bb1": taper_410_1560}
    routing_strt_large = gf.partial(tps_410_swg_1560_swg_lim, **routing_kwargs)

    # SiN2
    routing_bend_anwg = ipr.bend_variant(
        variant="bloss",
        angle=90,
        length_access=0,
        bloss_rho=1.038,
        width=1.280,
        dw_over_w=0.556,
        cross_section="nitride2",
        radius=50,
        npoints=100,
    )

    bend_taper = ipr.rib_taper(
        cross_section="nitride2", width_RIB_in=1.28, width_RIB_out=2.00, length=12.72
    )
    routing_kwarsg = {
        "bbmul": routing_bend_anwg,
        "bbadd": bend_taper,
        "bbmul_list": ["o1", "o2"],
    }
    bend_taper_wtaper = ipr.bb_mul_bb(**routing_kwarsg)

    # Vertical transition optimized TE
    vt_opt_te = ipr.si_anwg_transition(
        name_si_nwg_transition="VT_1_TE",
        name_nwg_anwg_transition="VT_2_TE",
        width_out=2.0,
    )
    vt_opt_te_group_index = ipr.si_anwg_transition(
        name_si_nwg_transition="VT_1_TE",
        name_nwg_anwg_transition="VT_2_TE",
        width_out=1.5,
    )
    vt1_te_group_index = ipr.si_nwg_transition(name="VT_1_TE", width_out=1.0)

    # Vertical transition polarization insensitive
    vt_pi = ipr.si_anwg_transition(
        name_si_nwg_transition="VT1_PI_D0_100",
        name_nwg_anwg_transition="VT2_POLINS_D_02",
        width_out=0.7,
    )

    # Grating coupler array
    gc_array = ipr.grating_coupler_array(
        grating_coupler=ipr.tower_gc,
        n=10,
        with_loopback=True,
        cross_section=xs_swg,
        dx=10,
    )

    # Grating coupler for TM is formed by rot + 3 si_ps_tw
    # --- Add absorber to pol split
    split = ipr.si_ps_tw()
    rotator = ipr.rotator()
    absorber = ipr.rib_absorber()
    kwargs = {
        "bbmul": split,
        "bbadd": absorber,
        "bbmul_list": ["o2", "o4"],
        "bbadd_mirror": [False, False],
    }
    split_with_abs = ipr.bb_mul_bb(**kwargs)  # pol split + absorber
    split_with_abs = change_port(split_with_abs, ["o1", "o3"], ["o1", "o2"])

    # --- Add rotator to every port of the gc array first
    rotator_inverted = change_port(rotator, ["o1", "o2"], ["o2", "o1"])
    kwargs = {
        "bbmul": gc_array,
        "bbadd": rotator_inverted,
        "bbmul_list": [f"o{idx}" for idx in range(1, 9)],
    }
    gc_array_rot = ipr.bb_mul_bb(**kwargs)  # gc + rotator, all ports

    # ---- Now develop the 3x(pol split + absorber) part
    n_rep = 3
    sep_distance = 10
    tot_size = sep_distance * (n_rep + 1) + split.xsize * n_rep + absorber.xsize
    kwargs = {
        "bb": split_with_abs,
        "sep_distance": sep_distance,
        "sep_variation": 0.141,
        "n_bb": n_rep,
        "straight": straight_410_swg,
    }
    split_with_abs_3 = ipr.nbb_straight(
        **kwargs, length=tot_size
    )  # 3(pol split + absorber)

    # --- Add the 3(pol split + absorber) chain to only every other port of gc_array_rot
    kwargs = {
        "bbmul": gc_array_rot,
        "bbadd": split_with_abs_3,
        "bbmul_list": [f"o{2 * idx + 1}" for idx in range(4)],
    }
    gc_array_tm = ipr.bb_mul_bb(**kwargs)
    gc_array_tm.name = "grating_coupler_array_tm"
    for idx in range(1, 9):
        if idx % 2 == 1:
            gc_array_tm.info[f"gc_{idx}"] = ipr.combine_component_dict(
                ipr.measure_component(ipr.tower_gc()), ipr.measure_component(rotator)
            )

            for _ in range(3):
                gc_array_tm.info[f"gc_{idx}"] = ipr.combine_component_dict(
                    gc_array_tm.info[f"gc_{idx}"], ipr.measure_component(split)
                )
        else:
            gc_array_tm.info[f"gc_{idx}"] = ipr.combine_component_dict(
                ipr.measure_component(ipr.tower_gc()), ipr.measure_component(rotator)
            )

    gc_array_long = ipr.grating_coupler_array(
        grating_coupler=ipr.tower_gc,
        n=20,
        with_loopback=True,
        cross_section=xs_swg,
        dx=10,
    )

    # 2D Crossing
    crossing_2D_ = ipr.crossing("polaris", version="60nm")
    crossing_2D = component_with_transition(crossing_2D_)

    # ################# #
    # STRUCTURE CONTROL #
    # ################# #
    # DoE Json file (should not be necessary for T1)
    doe_json_filename = "src/ComplementaryFile/DoE_component_parameters.json"
    with open(doe_json_filename) as f:
        doe_json_dict = json.load(f)
    doe_json_dict = doe_json_dict["T1"]

    # Lab Json File
    lab_filename = "src/ComplementaryFile/V7b.json"
    create_json = True
    if create_json:
        json_writer = ipr.json_writer(filename=lab_filename, die="DIE_T1")
        json_writer.reset()

    # Sim Json file
    sim_filename = "src/ComplementaryFile/sim_bb.json"
    with open(sim_filename, encoding="utf-8") as f:
        sim_filename_json = json.load(f)

    # Structure dictionary where append the wanted structure
    structures = {}
    structures_text = {}
    structure_only = []  # If void draw all structures, otherwise only the one present here

    # #############################################
    # # N.1 Prop. Loss RIB 0.93 um Test Structure #
    # #############################################
    if len(structure_only) == 0 or 1 in structure_only:
        print("\nCreation of N.1 Prop. Loss RIB 0.93 um Test Structure")

        # Parameters for the cell
        gap = 3 + 0.93 - 0.41
        sep = 14.45
        n_bends = 100
        comp_len = [5 * 10000, 10 * 10000, 15 * 10000, 20 * 10000]

        # Create the test structure 1.1
        ts = "1.1"
        t = die << ipr.test_double_spirals_from_calculation(
            bend=routing_bend_Si,
            blocks_distance=(50, 0),
            block_gc_distance=30,
            gc_array=gc_array,
            n_bends=n_bends,
            hv_ratios=[0.5, 0.89],
            straight=routing_strt,
            lengths=[comp_len[0], comp_len[3]],
            separations_rep=sep,
            separations_xs=gap,
            straight_route=routing_strt,
        )

        # Assign to the dictionary
        structures[ts] = t
        structures_text[ts] = f"{ts} PROP LOSS XT SI 0.93"

        # Json Part
        json_writer.structure_json(
            component=gf.get_component(straight_930_swg(length=0)),
            component_IO=gc_array,
            structure_title=f"TS0{ts}",
            structure=t.cell,
            extra_dict={"analysis": ["propte_dbcm", "xtte_db"]},
        )

        # Create the test structure 1.2
        ts = "1.2"
        t = die << ipr.test_double_spirals_from_calculation(
            bend=routing_bend_Si,
            blocks_distance=(50, 0),
            block_gc_distance=30,
            gc_array=gc_array,
            n_bends=n_bends,
            hv_ratios=[0.8, 0.9],
            straight=routing_strt,
            lengths=[comp_len[1], comp_len[2]],
            separations_rep=sep,
            separations_xs=gap,
            straight_route=routing_strt,
        )

        # Assign to the dictionary
        structures[ts] = t
        structures_text[ts] = f"{ts} PROP LOSS XT SI 0.93"

        # Json Part
        if create_json:
            json_writer.structure_json(
                component=gf.get_component(straight_930_swg(length=0)),
                component_IO=gc_array,
                structure_title=f"TS0{ts}",
                structure=t.cell,
                extra_dict={"analysis": ["propte_dbcm", "xtte_db"]},
            )

    # #############################################
    # # N.2 Prop. Loss RIB 0.41 um Test Structure #
    # #############################################
    if len(structure_only) == 0 or 2 in structure_only:
        print("\nCreation of N.2 Prop. Loss RIB 0.41 um Test Structure")

        # Parameters for the cell
        gap = 3
        sep = 13.41
        n_bends = 96
        comp_len = [4 * 10000, 8 * 10000, 12 * 10000, 16 * 10000]

        # Create the test structure 1.1
        ts = "2.1"
        t = die << ipr.test_double_spirals_from_calculation(
            bend=routing_bend_Si,
            blocks_distance=(50, 0),
            block_gc_distance=30,
            gc_array=gc_array,
            n_bends=n_bends,
            hv_ratios=[0.5, 0.83],
            straight=straight_410_swg,
            lengths=[comp_len[0], comp_len[3]],
            separations_rep=sep,
            separations_xs=gap,
            straight_route=straight_410_swg,
        )

        # Assign to the dictionary
        structures[ts] = t
        structures_text[ts] = f"{ts} PROP LOSS XT SI 0.41"

        # Json Part
        json_writer.structure_json(
            component=gf.get_component(straight_410_swg(length=0)),
            component_IO=gc_array,
            structure_title=f"TS0{ts}",
            structure=t.cell,
            extra_dict={"analysis": ["propte_dbcm", "xtte_db"]},
        )

        # Create the test structure 1.2
        ts = "2.2"
        t = die << ipr.test_double_spirals_from_calculation(
            bend=routing_bend_Si,
            blocks_distance=(50, 0),
            block_gc_distance=30,
            gc_array=gc_array,
            n_bends=n_bends,
            hv_ratios=[0.7, 0.75],
            straight=straight_410_swg,
            lengths=[comp_len[1], comp_len[2]],
            separations_rep=sep,
            separations_xs=gap,
            straight_route=straight_410_swg,
        )

        # Assign to the dictionary
        structures[ts] = t
        structures_text[ts] = f"{ts} PROP LOSS XT SI 0.41"

        # Json Part
        if create_json:
            json_writer.structure_json(
                component=gf.get_component(straight_410_swg(length=0)),
                component_IO=gc_array,
                structure_title=f"TS0{ts}",
                structure=t.cell,
                extra_dict={"analysis": ["propte_dbcm", "xtte_db"]},
            )

    # ##############################################
    # # N.3 Prop. Loss AWNG 2.00 um Test Structure #
    # ##############################################
    if len(structure_only) == 0 or 3 in structure_only:
        print("\nCreation of N.3 Prop. Loss Nitride2 um Test Structure")

        # Parameters for the cell
        gap = 5
        sep = 17
        n_bends = 84
        comp_len = [4 * 10000, 8 * 10000, 12 * 10000, 16 * 10000]

        # Create the test structure 3.1
        ts = "3.1"
        t = die << xt_sin_function(
            bend_SiN2=bend_taper_wtaper,
            bend_Si=routing_bend_Si,
            gc_array=gc_array,
            gc_array_dist=110,
            hv_ratios=[1, 0.065],
            n_bends=n_bends,
            total_lengths=[comp_len[0], comp_len[3]],
            separation_rep=sep,
            separation_xs=gap,
            routing_straight=routing_strt,
            vt=vt_opt_te,
        )

        # Assign to the dictionary
        structures[ts] = t
        structures_text[ts] = f"{ts} PROP LOSS XT AWNG 2.00"

        # Json Part
        if create_json:
            json_writer.structure_json(
                component=gf.get_component(straight_2000_anwg(length=0)),
                component_IO=gc_array,
                structure_title=f"TS0{ts}",
                structure=t.cell,
                extra_dict={"analysis": ["propte_dbcm", "xtte_db"]},
            )

        # Create the test structure 3.2
        ts = "3.2"
        t = die << xt_sin_function(
            bend_SiN2=bend_taper_wtaper,
            bend_Si=routing_bend_Si,
            gc_array=gc_array,
            gc_array_dist=110,
            hv_ratios=[0.1, 0.1],
            n_bends=n_bends,
            total_lengths=[comp_len[1], comp_len[2]],
            separation_rep=sep,
            separation_xs=gap,
            routing_straight=routing_strt,
            vt=vt_opt_te,
        )

        # Assign to the dictionary
        structures[ts] = t
        structures_text[ts] = f"{ts} PROP LOSS XT AWNG 2.00"

        # Json Part
        if create_json:
            json_writer.structure_json(
                component=gf.get_component(straight_2000_anwg(length=0)),
                component_IO=gc_array,
                structure_title=f"TS0{ts}",
                structure=t.cell,
                extra_dict={"analysis": ["propte_dbcm", "xtte_db"]},
            )

    # #################################################
    # # N.4 Insertion Loss Si Bend 90° Test Structure #
    # #################################################
    if len(structure_only) == 0 or 4 in structure_only:
        print("\nCreation of N.4 Insertion Loss Si Bend 90° Test Structure")

        n_bbs = [1500, 1500 * 2, 1500 * 3, 1500 * 4]

        # Calculate the size of the bends involved
        bend_rotate = routing_bend_Si.copy()
        beta = routing_half_bend_Si["o2"].orientation
        bend_rotate.rotate(beta)
        bend_sep_size = 1.5
        bend_io_size = routing_half_bend_Si["o2"].x - routing_half_bend_Si["o1"].x

        # Feature to be used for the bends
        feature_bend = {
            "straight": straight_410_swg,
            "sep_variation": 0.141,
            "bb": routing_bend_Si,
            "bb_io": routing_half_bend_Si,
            # For length calculations
            "2_bb": bend_rotate,
            "2_io_length": bend_io_size,
        }

        straights_bend = []
        fbs = []
        for idx in range(4):
            fb = feature_bend.copy()
            fb["sep_distance"] = [4.5, 2.3, 1.19, 1][idx] * bend_sep_size
            fb["bb_extra_length"] = [4.5, 2.3, 1.19, 1][idx] * bend_sep_size
            fb["2_sep_distance"] = (
                [4.5, 2.3, 1.19, 1][idx] * bend_sep_size * np.cos(beta * np.pi / 180)
            )
            fb["2_bb_extra_length"] = (
                [4.5, 2.3, 1.19, 1][idx] * bend_sep_size * np.cos(beta * np.pi / 180)
            )
            fbs.append(fb)
            straight_bend = gf.partial(ipr.nbends_angled_straight, **fb)
            straights_bend.append(straight_bend)

        # Create the test structure 4.1
        ts = "4.1"

        # Function to generate dummy
        dummy_adder = gf.partial(T1_dummy_adder, distance_metal=5, distane_wvg=10)
        t = die << ipr.test_serpentines_from_calculation(
            bend=routing_bend_Si,
            blocks_distance=(15, 15),
            block_gc_distance=30,
            dummy_adder=dummy_adder,
            gc_array=gc_array,
            max_height=1150,
            straight=straights_bend,
            lengths=fbs,
            n_bbs=n_bbs,
            separations=0,
            n_rows_pitch=9,
            separations_pitch=50,
            straight_route=straight_410_swg,
            structure_4_blocks="2x2",
        )

        # Assign to the dictionary
        structures[ts] = t
        structures_text[ts] = f"{ts} EULER SI BEND 0.41"

        # Json Part
        if create_json:
            json_writer.structure_json(
                component=routing_bend_Si,
                component_IO=gc_array,
                structure_title=f"TS0{ts}",
                structure=t.cell,
                extra_dict={"analysis": ["ilte_db"]},
            )

    # ###############################################
    # # N.5 Insertion Loss Rib Taper Test Structure #
    # ###############################################
    if len(structure_only) == 0 or 5 in structure_only:
        print("\nCreation of N.5 Insertion Loss Rib Taper Test Structure")

        n_bbs = [2000, 4000, 6000, 8000]

        # Create the test structure 5.1
        ts = "5.1"

        # Prepare the straight dict
        feature_rib_taper = {
            "bb": taper_410_930,
            "straight": straight_930_swg,
            "straight_btw": straight_410_swg,
            "sep_variation": bb_variation,
            "bb_extra_variation": bb_variation,
        }

        rib_taper_strts = []
        fts = []
        for idx in range(4):
            ft = feature_rib_taper.copy()
            ft["sep_distance"] = [3.30, 1.84, 1.32, 1.00][idx]
            ft["bb_extra_length"] = [7.50, 3.23, 1.60, 1.00][idx]
            fts.append(ft)
            rib_taper_strt = gf.partial(ipr.n_tps_tps, **ft)
            rib_taper_strts.append(rib_taper_strt)

        t = die << ipr.test_spirals_from_calculation(
            bend=routing_bend_Si,
            blocks_distance=(50, 0),
            block_gc_distance=30,
            gc_array=gc_array,
            straight=rib_taper_strts,
            lengths=fts,
            n_bbs=n_bbs,
            hv_ratios=[0.5, 0.93, 0.8, 0.6],
            separations=7,
            n_bends=115,
            straight_route=routing_strt,
            structure_4_blocks="hor",
        )

        # Assign to the dictionary
        structures[ts] = t
        structures_text[ts] = f"{ts} RIB TAPER 0.41 0.93"

        # Json Part
        if create_json:
            json_writer.structure_json(
                component=taper_410_930,
                component_IO=gc_array,
                structure_title=f"TS0{ts}",
                structure=t.cell,
                extra_dict={"analysis": ["ilte_db"]},
            )

        # Create the test structure 5.2
        ts = "5.2"

        # Prepare the straight dict
        feature_rib_taper = {
            "bb": taper_410_1560,
            "straight": straight_1560_swg,
            "straight_btw": straight_410_swg,
            "sep_variation": bb_variation,
            "bb_extra_variation": bb_variation,
        }

        rib_taper_strts = []
        fts = []
        for idx in range(4):
            ft = feature_rib_taper.copy()
            ft["sep_distance"] = [3.30, 1.84, 1.32, 1.00][idx]
            ft["bb_extra_length"] = [7.50, 3.23, 1.60, 1.00][idx]
            fts.append(ft)
            rib_taper_strt = gf.partial(ipr.n_tps_tps, **ft)
            rib_taper_strts.append(rib_taper_strt)

        t = die << ipr.test_spirals_from_calculation(
            bend=routing_bend_Si,
            blocks_distance=(50, 0),
            block_gc_distance=30,
            gc_array=gc_array,
            straight=rib_taper_strts,
            lengths=fts,
            n_bbs=n_bbs,
            hv_ratios=[0.5, 0.93, 0.8, 0.6],
            separations=7,
            n_bends=115,
            straight_route=routing_strt_large,
            structure_4_blocks="hor",
        )

        # Assign to the dictionary
        structures[ts] = t
        structures_text[ts] = f"{ts} RIB TAPER 0.41 1.56"

        # Json Part
        if create_json:
            json_writer.structure_json(
                component=taper_410_1560,
                component_IO=gc_array,
                structure_title=f"TS0{ts}",
                structure=t.cell,
                extra_dict={"analysis": ["ilte_db"]},
            )

    # ######################################################
    # # N.6 Insertion Loss Polaris Crossing Test Structure #
    # ######################################################
    if len(structure_only) == 0 or 6 in structure_only:
        print("\nCreation of N.6 Polaris Crossing Test Structure")

        n_bbs = [1250, 2500, 3750, 5000]

        # Create the test structure 6.1
        ts = "6.1"

        cross_kwargs = {
            "bbmul": crossing_2D,
            "bbadd": taper_1560_410,
            "bbmul_list": ["o2", "o4"],
        }  # Add taper
        cross_tp = ipr.bb_mul_bb(**cross_kwargs)
        cross_kwargs = {
            "bbmul": cross_tp,
            "bbadd": absorber,
            "bbmul_list": ["o2", "o4"],
            "bbadd_mirror": [True, False],
        }  # Add absorber
        cross_with_abs = ipr.bb_mul_bb(**cross_kwargs)
        cross_with_abs = change_port(
            cross_with_abs,  # Invert ports
            ["o1", "o3"],
            ["o1", "o2"],
            flatten=False,
        )

        # N crossing
        feature_cross = {
            "1_bb": cross_with_abs,
            "1_straight": straight_1560_swg,
            "1_straight_btw": straight_1560_swg,
            "1_sep_variation": bb_variation,
            "straight": ipr.nbb_straight,
            "straight_limited": straight_410_swg,
            "bb1": taper_410_1560,
            "bb2": taper_410_1560,
            "bb2_rev": True,
            "io_length": taper_410_1560.xsize,
        }

        straights_cross_tp = []
        fcs = []
        for idx in range(4):
            fc = feature_cross.copy()
            fc["1_sep_distance"] = [12.8, 6.50, 2.90, 2.50][idx]
            fc["2_bb_extra_length"] = [13.05, 6.58, 2.93, 3.50][idx]
            fcs.append(fc)
            straight_cross_tp = gf.partial(ipr.bb_straight_bb_limited, **fc)
            straights_cross_tp.append(straight_cross_tp)

        # Function to generate dummy
        dummy_adder = gf.partial(
            T1_dummy_adder,
            distance_metal=12,
            distane_wvg=12,
            delta_hor_ver_metal=-6.5,
            delta_hor_ver_wvg=-6.5,
        )

        # Generate test structure
        t = die << ipr.test_serpentines_from_calculation(
            bend=routing_bend_Si,
            blocks_distance=(50, 35),
            block_gc_distance=30,
            dummy_adder=dummy_adder,
            gc_array=gc_array,
            max_height=1150,
            straight=straights_cross_tp,
            lengths=fcs,
            n_bbs=n_bbs,
            separations=18,
            straight_route=routing_strt_large,
            structure_4_blocks="2x2",
            n_rows_pitch=7,
            separations_pitch=60,
        )

        # Assign to the dictionary
        structures[ts] = t
        structures_text[ts] = f"{ts} POLARIS_60 IL"

        # Json Part
        if create_json:
            json_writer.structure_json(
                component=crossing_2D_,
                component_IO=gc_array,
                structure_title=f"TS0{ts}",
                structure=t.cell,
                extra_dict={"analysis": ["ilte_db"]},
            )

    # #########################################################
    # # N.7 Insertion Loss Vertical Transition Test Structure #
    # #########################################################
    if len(structure_only) == 0 or 7 in structure_only:
        print("\nCreation of N.7 Vertical Transition Test Structure")

        # Create the test structure 7.1
        ts = "7.1"

        n_bbs = [180, 180 * 2, 180 * 3, 180 * 4]

        # N Vertical Transition
        feature_vt = {
            "2_bb": vt_pi,
            "1_bb1": vt_pi,
            "1_bb2": vt_pi,
            "1_bb2_rev": True,
            "1_straight": straight_700_anwg,
            "bb": ipr.bb_straight_bb,
            "sep_distance": 1.0 + bb_variation + 0.002,
            "sep_variation": bb_variation,
            "bb_extra_length": 1.0 + bb_variation + 0.002,
            "bb_extra_variation": bb_variation,
            "straight": straight_410_swg,
        }
        straight_vt = gf.partial(ipr.nbb_straight, **feature_vt)

        # Function to generate dummy
        dummy_adder = gf.partial(
            T1_dummy_adder,
            distance_metal=10.5,
            distane_wvg=10,
            delta_hor_ver_metal=-4.5,
            delta_hor_ver_wvg=-4.5,
        )
        t = die << ipr.test_serpentines_from_calculation(
            bend=routing_bend_Si,
            blocks_distance=(15, 10),
            block_gc_distance=30,
            dummy_adder=dummy_adder,
            gc_array=gc_array,
            max_height=1140,
            straight=straight_vt,
            lengths=feature_vt,
            n_bbs=n_bbs,
            separations=10,
            straight_route=routing_strt,
            structure_4_blocks="2x2",
            n_rows_pitch=12,
            separations_pitch=45,
        )

        # Assign to the dictionary
        structures[ts] = t
        structures_text[ts] = f"{ts} VT12_PI_D0 IL TE"

        # Json Part
        if create_json:
            json_writer.structure_json(
                component=vt_pi,
                component_IO=gc_array,
                structure_title=f"TS0{ts}",
                structure=t.cell,
                extra_dict={"analysis": ["ilte_db"]},
            )

        # Create the test structure 7.2
        ts = "7.2"

        n_bbs = [20, 40, 60, 80]

        # N Vertical Transition
        feature_vt = {
            "2_bb": vt_pi,
            "1_bb1": vt_pi,
            "1_bb2": vt_pi,
            "1_bb2_rev": True,
            "1_straight": straight_700_anwg,
            "bb": ipr.bb_straight_bb,
            "sep_distance": 1.0 + bb_variation + 0.002,
            "sep_variation": bb_variation,
            "bb_extra_length": 1.0 + bb_variation + 0.002,
            "bb_extra_variation": bb_variation,
            "straight": straight_410_swg,
        }
        straight_vt = gf.partial(ipr.nbb_straight, **feature_vt)

        t = die << ipr.test_serpentines_from_calculation(
            bend=routing_bend_Si_TM,
            blocks_distance=(15, 30),
            block_gc_distance=40,
            dummy_adder=dummy_adder,
            gc_array=gc_array_tm,
            max_height=950,
            straight=straight_vt,
            lengths=feature_vt,
            n_bbs=n_bbs,
            separations=20,
            straight_route=routing_strt,
            structure_4_blocks="2x2",
            n_rows_pitch=4,
            separations_pitch=100,
        )

        # Assign to the dictionary
        structures[ts] = t
        structures_text[ts] = f"{ts} VT12_PI_D0 IL TM"

        # Json Part
        if create_json:
            json_writer.structure_json(
                component=vt_pi,
                component_IO=gc_array_tm,
                structure_title=f"TS0{ts}",
                structure=t.cell,
                propagation_mode=["tm"],
                extra_dict={"analysis": ["iltm_db"]},
            )

        # Create the test structure 7.3
        ts = "7.3"

        n_bbs = [85, 85 * 2, 85 * 3, 85 * 4]

        # N Vertical Transition
        feature_vt = {
            "2_bb": vt_opt_te,
            "1_bb1": vt_opt_te,
            "1_bb2": vt_opt_te,
            "1_bb2_rev": True,
            "1_straight": straight_2000_anwg,
            "bb": ipr.bb_straight_bb,
            "sep_distance": 1.0 + bb_variation + 0.002,
            "sep_variation": bb_variation,
            "bb_extra_length": 1.0 + bb_variation + 0.002,
            "bb_extra_variation": bb_variation,
            "straight": straight_410_swg,
        }
        straight_vt = gf.partial(ipr.nbb_straight, **feature_vt)

        t = die << ipr.test_serpentines_from_calculation(
            bend=routing_bend_Si,
            blocks_distance=(15, 10),
            block_gc_distance=30,
            dummy_adder=dummy_adder,
            gc_array=gc_array,
            max_height=1100,
            straight=straight_vt,
            lengths=feature_vt,
            n_bbs=n_bbs,
            separations=10,
            straight_route=routing_strt,
            structure_4_blocks="2x2",
            n_rows_pitch=12,
            separations_pitch=45,
        )

        # Assign to the dictionary
        structures[ts] = t
        structures_text[ts] = f"{ts} VT12_TE_D0 IL"

        # Json Part
        if create_json:
            json_writer.structure_json(
                component=vt_opt_te,
                component_IO=gc_array,
                structure_title=f"TS0{ts}",
                structure=t.cell,
                extra_dict={"analysis": ["ilte_db"]},
            )

    # #############################################
    # # N.8 Group Index Transition Test Structure #
    # #############################################
    if len(structure_only) == 0 or 8 in structure_only:
        print("\nCreation of N.8 Group Index Test Structure")

        for idx in range(5):
            # Create the test structure 8.{idx+1}
            ts = f"8.{idx + 1}"

            if idx == 0:  # Si 0.41
                low_order_mzi_length = 9.5054
                high_order_mzi_length = 95.0535
                m_neff = 18
                m_ng = 180
                cross_section2 = xs_swg_410
                text = "Si 0.41"
                extra_component = None
            elif idx == 1:  # Si 0.93
                low_order_mzi_length = 22.222
                high_order_mzi_length = 80
                m_neff = 50
                m_ng = 180
                cross_section2 = xs_swg_930
                text = "Si 0.93"
                extra_component = taper_410_930
            elif idx == 2:  # SiN2 2.00
                low_order_mzi_length = 33.123
                high_order_mzi_length = 115.932
                m_neff = 40
                m_ng = 140
                cross_section2 = xs_awng_2000
                text = "SiN2 2.00"
                extra_component = vt_opt_te
            elif idx == 3:  # SiN2 1.50
                low_order_mzi_length = 33.408
                high_order_mzi_length = 116.927
                m_neff = 40
                m_ng = 140
                cross_section2 = xs_awng_1500
                text = "SiN2 1.50"
                extra_component = vt_opt_te_group_index
            else:  # SiN 1.00
                low_order_mzi_length = 30.846
                high_order_mzi_length = 61.693
                m_neff = 40
                m_ng = 80
                cross_section2 = xs_nwg_1000
                text = "SiN 1.00"
                extra_component = vt1_te_group_index

            # Create the mzi test structure
            t = die << mzis_test_group_and_effective_index(
                low_order_mzi_length=low_order_mzi_length,
                high_order_mzi_length=high_order_mzi_length,
                grating_coupler=ipr.tower_gc,
                bend=routing_bend_Si,
                cross_section=xs_swg_410,
                cross_section2=cross_section2,
                extra_component=extra_component,
            )

            # Rotate it
            t.rotate(90)

            # Assign to the dictionary
            structures[ts] = t
            structures_text[ts] = f"R{ts} EFF IDX \n{text}"

            # Json Part
            if create_json:
                json_writer.structure_json(
                    component=t.cell,
                    component_IO=gc_array,
                    structure_title=f"TS0{ts}",
                    structure=t.cell,
                    extra_dict={
                        "analysis": ["neff_au", "ng_au"],
                        "cutback": {
                            "num_components": 1,
                            "low_order_mzi_length": low_order_mzi_length,
                            "high_order_mzi_length": high_order_mzi_length,
                            "m_neff": m_neff,
                            "m_ng": m_ng,
                        },
                    },
                )

    # ##################################
    # # N.9 3D Crossing Test Structure #
    # ##################################
    if len(structure_only) == 0 or 9 in structure_only:
        print("\nCreation of N.9 3D crossing test structure")

        # 3D crossing_swg_930_anwg_2000 -> BELOW
        for idx, angle in enumerate([90]):
            # Passing signal below the nitride
            cross_straight, cross_kwargs, cross_3d = straigth_with_3d_cross_strip(
                angle=angle, separation=3.0 / np.sin(angle / 180 * np.pi), below=True
            )

            nbb_diff = int(4000 * np.sin(angle / 180 * np.pi))

            # Function to generate dummy
            dummy_adder = gf.partial(
                T1_dummy_adder, distance_metal=5, distane_wvg=10, delta_hor_ver_wvg=-4.5
            )

            # Create test structure
            ts = f"9.{idx + 1}"
            t = die << ipr.test_serpentines_from_calculation(
                bend=routing_bend_Si,
                blocks_distance=(85, 10),
                block_gc_distance=20,
                dummy_adder=dummy_adder,
                gc_array=gc_array,
                straight=cross_straight,
                separations=10.2,
                lengths=cross_kwargs,
                n_bbs=[nbb_diff, nbb_diff * 2, nbb_diff * 3, nbb_diff * 4],
                structure_4_blocks="2x2",
                max_height=1120,
                n_rows_pitch=11,
                separations_pitch=40,
                straight_route=routing_strt,
            )

            # Assign to the dictionary
            name = f"CROSS_3D_ANGLE_STRIP_{angle}_BELOW"
            structures[ts] = t
            structures_text[ts] = f"{ts} {name}"

            # Add the structures to the json file
            if create_json:
                json_writer.structure_json(
                    component=cross_3d,
                    component_IO=gc_array,
                    structure_title=f"TS0{ts}",
                    structure=t.cell,
                )

        # 3D crossing_swg_930_anwg_2000 -> ABOVE
        for idx, angle in enumerate([90, 30]):
            # Passing signal above the nitride
            cross_straight, cross_kwargs, cross_3d = straigth_with_3d_cross_strip(
                angle=angle, separation=3.0 / np.sin(angle / 180 * np.pi), below=False
            )

            nbb_diff = int(4000 * np.sin(angle / 180 * np.pi))

            # Function to generate dummy
            dummy_adder = gf.partial(
                T1_dummy_adder, distance_metal=10, distane_wvg=10, delta_hor_ver_wvg=-5
            )

            # Create test structure
            ts = f"9.{idx + 2}"
            t = die << ipr.test_serpentines_from_calculation(
                bend=routing_bend_Si,
                blocks_distance=(85, 10),
                block_gc_distance=20,
                dummy_adder=dummy_adder,
                gc_array=gc_array,
                straight=cross_straight,
                separations=10.2,
                lengths=cross_kwargs,
                n_bbs=[nbb_diff, nbb_diff * 2, nbb_diff * 3, nbb_diff * 4],
                structure_4_blocks="2x2",
                max_height=1120,
                n_rows_pitch=11,
                separations_pitch=45,
                straight_route=routing_strt,
            )

            # Assign to the dictionary
            name = f"CROSS_3D_ANGLE_STRIP_{angle}_ABOVE"
            structures[ts] = t
            structures_text[ts] = f"{ts} {name}"

            # Add the structures to the json file
            if create_json:
                json_writer.structure_json(
                    component=cross_3d,
                    component_IO=gc_array,
                    structure_title=f"TS0{ts}",
                    structure=t.cell,
                )

        # 3D crossing_gwg_410_anwg_1500 -> ABOVE
        for idx, angle in enumerate([90, 45, 30, 15]):
            # Passing signal below the nitride
            cross_straight, cross_kwargs, cross_3d = straigth_with_3d_cross_shallow(
                angle=angle,
                separation=(1.41 + 0.141 / 2) / np.sin(angle / 180 * np.pi),
                below=False,
            )
            nbb_diff = int(4000 * np.sin(angle / 180 * np.pi))

            # Function to generate dummy
            dummy_adder = gf.partial(
                T1_dummy_adder, distance_metal=5, distane_wvg=10, delta_hor_ver_wvg=-5
            )

            # Create test structure
            ts = f"9.{idx + 4}"
            t = die << ipr.test_serpentines_from_calculation(
                bend=routing_bend_Si,
                blocks_distance=(85, 10),
                block_gc_distance=20,
                dummy_adder=dummy_adder,
                gc_array=gc_array,
                straight=cross_straight,
                separations=10.2,
                lengths=cross_kwargs,
                n_bbs=[nbb_diff, nbb_diff * 2, nbb_diff * 3, nbb_diff * 4],
                structure_4_blocks="2x2",
                max_height=1120,
                n_rows_pitch=11,
                separations_pitch=45,
                straight_route=routing_strt,
            )

            # Assign to the dictionary
            name = f"CROSS_3D_ANGLE_SHALLOW_{angle}_ABOVE"
            structures[ts] = t
            structures_text[ts] = f"{ts} {name}"

            # Add the structures to the json file
            if create_json:
                json_writer.structure_json(
                    component=cross_3d,
                    component_IO=gc_array,
                    structure_title=f"TS0{ts}",
                    structure=t.cell,
                )

    # ############
    # # 10.0 MMI #
    # ############
    if len(structure_only) == 0 or 10 in structure_only:
        print("\nCreation of N.10 MMI Test Structure")

        ts_base = "10"
        for idx in range(len(doe_json_dict[f"{ts_base}.0"]["comp"])):
            ts = f"{ts_base}.{1 + idx}"

            # Select the clothoide bend from the DoE file
            comp = sim_filename_json[doe_json_dict[f"{ts_base}.0"]["comp"][idx]]
            name = comp["function"].split(".")[-1].rstrip("()")
            func = getattr(ipr, name)

            mmi = func(**comp["settings"])
            design_id = comp["design_id"]

            # Create test structure
            ts = f"{ts_base}.{2 * idx + 1}"
            t = die << ipr.test_splitter(
                bb=mmi,
                bend=routing_bend_Si,
                gc_array=gc_array_long,
                sep_variation=0.141,
                straight=straight_410_swg,
                state="bar",
                absorber=absorber,
                bb_safe_distance=45 - mmi.xsize,
            )

            # Assign to the dictionary
            structures[ts] = t
            structures_text[ts] = f"{ts} {design_id}_BAR"

            # Add the structures to the json file
            if create_json:
                json_writer.structure_json(
                    component=mmi,
                    component_IO=gc_array_long,
                    structure_title=f"TS{ts}",
                    structure=t.cell,
                )

            # Create test structure
            ts = f"{ts_base}.{2 * idx + 2}"
            t = die << ipr.test_splitter(
                bb=mmi,
                bend=routing_bend_Si,
                gc_array=gc_array_long,
                sep_variation=0.141,
                straight=straight_410_swg,
                state="cross",
                absorber=absorber,
                bb_safe_distance=45 - mmi.xsize,
            )

            # Assign to the dictionary
            structures[ts] = t
            structures_text[ts] = f"{ts} {design_id}_CROSS"

            # Add the structures to the json file
            if create_json:
                json_writer.structure_json(
                    component=mmi,
                    component_IO=gc_array_long,
                    structure_title=f"TS{ts}",
                    structure=t.cell,
                )

    # ############################
    # # 11.0 MMI - NEW STRUCTURE #
    # ############################
    if len(structure_only) == 0 or 11 in structure_only:
        print("\nCreation of N.11 MMI New Test Structure")

        ts_base = "11"
        for idx in range(len(doe_json_dict[f"{ts_base}.0"]["comp"])):
            ts = f"{ts_base}.{1 + idx}"

            # Select the clothoide bend from the DoE file
            comp = sim_filename_json[doe_json_dict[f"{ts_base}.0"]["comp"][idx]]
            name = comp["function"].split(".")[-1].rstrip("()")
            func = getattr(ipr, name)
            mmi = func(**comp["settings"])
            design_id = comp["design_id"]

            # Create test structure
            ts = f"{ts_base}.{idx + 1}"
            t = die << mmi_splitter_il_extractor(
                absorber=absorber,
                bend=routing_bend_Si,
                gc_array=gc_array,
                mmi_component=mmi,
                straight=straight_410_swg,
            )

            # Assign to the dictionary
            structures[ts] = t
            structures_text[ts] = f"{ts}\nMMI {idx + 1}\nIL - SR"

            # Add the structures to the json file
            if create_json:
                json_writer.structure_json(
                    component=mmi,
                    component_IO=gc_array,
                    structure_title=f"TS{ts}",
                    structure=t.cell,
                    extra_dict={"analysis": "il_sr_te"},
                )

    # #################
    # # 12.0 CROSSING #
    # #################
    if len(structure_only) == 0 or 12 in structure_only:
        print("\nCreation of N.12 Crossing XT Test Structure")
        cross_kwargs = {
            "bbmul": crossing_2D,
            "bbadd": taper_1560_410,
            "bbmul_list": ["o2"],
        }  # Add taper for absober

        cross_tp = ipr.bb_mul_bb(**cross_kwargs)

        taper_410_1560_inv = change_port(taper_410_1560, ["o1", "o2"], ["o2", "o1"])
        cross_kwargs = {
            "bbmul": cross_tp,
            "bbadd": taper_410_1560_inv,
            "bbmul_list": ["o1", "o3", "o4"],
        }  # Add taper for remaining part

        cross_tp = ipr.bb_mul_bb(**cross_kwargs)

        cross_kwargs = {
            "bbmul": cross_tp,
            "bbadd": absorber,
            "bbmul_list": ["o2"],
        }  # Add absorber
        cross_with_abs = ipr.bb_mul_bb(**cross_kwargs)

        # Create test structure
        ts = "12.1"
        t = die << ipr.test_crossing_xt(
            bb=cross_with_abs,
            bend=routing_bend_Si,
            gc_array=gc_array_long,
            sep_variation=0.141,
            straight=straight_410_swg,
            bb_safe_distance=5,
        )

        # Assign to the dictionary
        structures[ts] = t
        structures_text[ts] = f"{ts} POLARIS_60 XT"

        # Add the structures to the json file
        if create_json:
            json_writer.structure_json(
                component=crossing_2D_,
                component_IO=gc_array_long,
                structure_title=f"TS{ts}",
                structure=t.cell,
                extra_dict={"analysis": ["xtte_db"]},
            )

    # ##################
    # # 13.0 ALIGNMENT #
    # ##################
    if len(structure_only) == 0 or 13 in structure_only:
        print("\nCreation of N.13 Alignment Test Structure")

        for idx in range(4):
            # Create the test structure name
            ts = f"13.{idx + 1}"

            t = die << grating_array_test_structure(
                components_grating_coupler=[ipr.tower_gc] * 10,
                component_bend=routing_bend_Si,
                component_straight_routing=straight_410_swg,
            )

            # Assign to the dictionary
            structures[ts] = t
            structures_text[ts] = f"{ts} ALIGN"

            # Add the structures to the json file
            if create_json:
                json_writer.structure_json(
                    component=straight_410_swg(length=0),
                    component_IO=gc_array,
                    structure_title=f"TS{ts}",
                    structure=t.cell,
                )

    # ##################
    # # 14.0 CUSTOM GC #
    # ##################
    if len(structure_only) == 0 or 14 in structure_only:
        print("\nCreation of N.14 Custom GC Test Structure")

        # Create the test structure name
        ts = "14.1"

        # Build the single gc composed
        kwargs = {"bbmul": rotator, "bbadd": ipr.tower_gc(), "bbmul_list": ["o2"]}

        gc_tower_rotated = ipr.bb_mul_bb(**kwargs)
        kwargs = {
            "bbmul": gc_tower_rotated,
            "bbadd": split_with_abs_3,
            "bbmul_list": ["o1"],
        }

        gc_tower_rotated_with_splitters = ipr.bb_mul_bb(**kwargs)

        t = die << grating_array_test_structure(
            components_grating_coupler=[
                ipr.tower_gc,
                gc_tower_rotated,
                gc_tower_rotated_with_splitters,
                ipr.custom_grating_coupler("d2v5"),
                ipr.custom_grating_coupler("d2v5"),
                ipr.custom_grating_coupler("d1v1"),
                ipr.custom_grating_coupler("d1v1"),
                ipr.tower_gc,
                ipr.tower_gc,
                ipr.tower_gc,
            ],
            component_bend=routing_bend_Si,
            component_straight_routing=straight_410_swg,
        )

        # Assign to the dictionary
        structures[ts] = t
        structures_text[ts] = f"{ts} CUSTOM GC"

        # Add the structures to the json file
        if create_json:
            json_writer.structure_json(
                component=straight_410_swg(length=0),
                component_IO=t,
                structure_title=f"TS{ts}",
                structure=t.cell,
                extra_dict={
                    "gc": ["tower_gc", "tower_gc", "d1v1", "d1v1", "d2_v5", "d2_v5"],
                    "gc_extra": [
                        [],
                        [],
                        [],
                        [],
                        [],
                        [],
                        ["rotator", "si_ps_tw", "si_ps_tw", "si_ps_tw"],
                        ["rotator"],
                    ],
                },
            )

    #########################################################
    #########################################################
    #########################################################
    left_top_structure = [
        "13.1",
        "1.1",
        "1.2",
        "4.1",
        "6.1",
        "8.1",
        "8.2",
        "8.3",
        "8.4",
        "8.5",
        "9.1",
        "13.3",
    ]
    left_cen_structure = ["2.1", "2.2", "5.1", "9.2", "9.3", "9.4", "9.5", "9.6", "9.7"]
    left_bot_structure = [
        "13.2",
        "3.1",
        "3.2",
        "5.2",
        "7.1",
        "7.2",
        "7.3",
        "11.1",
        "11.2",
        "11.3",
        "11.4",
        "13.4",
        "14.1",
    ]
    right_structure = [f"10.{idx + 1}" for idx in range(14)] + ["12.1"]

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
        right_structure = [
            s for s in right_structure if int(s.split(".")[0]) in structure_only
        ]

    # Make text capital
    structures_text = {k: v.upper() for k, v in structures_text.items()}

    # Move left top structures
    previous_x_max = die_x_min + edge_margin
    for structure_idx in left_top_structure:
        s = structures[structure_idx]
        s.xmin = previous_x_max
        s.y = die_y_center + 2 * die_height_semi / 3
        previous_x_max = s.xmax + structure_to_structure_margin_top

        # Write the text for those
        text_to_write = structures_text[structure_idx]
        if text_to_write.startswith("R"):
            text_to_write = text_to_write[1:]
            text = die << all_metal_text(text_to_write, size=25, justify="center")
            text.move((text.xmin, text.ymax), ((s.xmin + 25), (s.ymax - 50)))
        else:
            text = die << all_metal_text(text_to_write, size=25, justify="center")
            text.move((text.xmin, text.ymin), ((s.xmin + 80), (s.ymin - 35)))
        bbox = die << gf.components.rectangle(
            size=(text.xmax - text.xmin + 2, text.ymax - text.ymin + 2),
            layer=bbox_layer,
        )
        bbox.move((bbox.xmin, bbox.ymin), ((text.xmin - 1, text.ymin - 1)))

    # Move left cen structures
    previous_x_max = die_x_min + edge_margin
    for structure_idx in left_cen_structure:
        s = structures[structure_idx]
        s.xmin = previous_x_max
        s.y = die_y_center
        previous_x_max = s.xmax + structure_to_structure_margin_middle

        # Write the text for those
        text_to_write = structures_text[structure_idx]
        if text_to_write.startswith("R"):
            text_to_write = text_to_write[1:]
            text = die << all_metal_text(text_to_write, size=25, justify="center")
            text.move((text.xmin, text.ymax), ((s.xmin + 145), (s.ymax)))
        else:
            text = die << all_metal_text(text_to_write, size=25, justify="center")
            text.move((text.xmin, text.ymin), ((s.xmin + 80), (s.ymin - 35)))

        bbox = die << gf.components.rectangle(
            size=(text.xmax - text.xmin + 2, text.ymax - text.ymin + 2),
            layer=bbox_layer,
        )
        bbox.move((bbox.xmin, bbox.ymin), ((text.xmin - 1, text.ymin - 1)))

    # Move left bot structures
    previous_x_max = die_x_min + edge_margin
    for structure_idx in left_bot_structure:
        s = structures[structure_idx]
        s.xmin = previous_x_max
        s.y = die_y_center - 2 * die_height_semi / 3
        previous_x_max = s.xmax + structure_to_structure_margin_bot

        # Write the text for those
        text_to_write = structures_text[structure_idx]
        text = die << all_metal_text(text_to_write, size=25, justify="center")
        text.move((text.xmin, text.ymin), ((s.xmin + 80), (s.ymin - 30)))

        bbox = die << gf.components.rectangle(
            size=(text.xmax - text.xmin + 2, text.ymax - text.ymin + 2),
            layer=bbox_layer,
        )
        bbox.move((bbox.xmin, bbox.ymin), ((text.xmin - 1, text.ymin - 1)))

    # Move right structures
    previous_x_max = die.xmax - edge_margin_right

    for structure_idx in right_structure:
        s = structures[structure_idx]
        s.xmax = previous_x_max - min_gc_gc_distance
        s.y = die_y_center + 600
        previous_x_max = s.xmax

        # Write the text for those
        text = die << all_metal_text(
            structures_text[structure_idx], size=25, justify="center"
        )
        text.rotate(90)
        text.move((text.xmax, text.ymin), ((s.xmin - 10), (s.ymin - 15)))

        bbox = die << gf.components.rectangle(
            size=(text.xmax - text.xmin + 2, text.ymax - text.ymin + 2),
            layer=bbox_layer,
        )
        bbox.move((bbox.xmin, bbox.ymin), ((text.xmin - 1, text.ymin - 1)))

    # MARKERS
    radius = 25
    extra_bot_top_space = 75

    for idx in range(3):
        # Chose layer
        if idx == 0:
            layer = LAYER.metal1
        elif idx == 1:
            layer = LAYER.metal2
        else:
            layer = LAYER.metal3

        # Bottom left
        squareness_length = 10
        t2 = die << triangle_round(
            layer=layer,
            size=(radius * 2 + squareness_length, radius * 2 + squareness_length),
            squareness_length=squareness_length,
        )
        t2.xmin = die.xmin + radius * 2
        t2.ymin = die_y_min + extra_bot_top_space - radius
        rec = die << gf.c.rectangle(
            size=(t2.xsize + 10, t2.ysize + 10), layer=(118, 40)
        )
        rec.xmin = t2.xmin - 5
        rec.ymin = t2.ymin - 5

        # Top left
        o1 = die << gf.components.circle(radius=radius, layer=layer)
        o1.xmin = die.xmin + radius * 2
        o1.ymax = die_y_max - radius * 2
        rec = die << gf.c.rectangle(
            size=(o1.xsize + 10, o1.ysize + 10), layer=(118, 40)
        )
        rec.xmin = o1.xmin - 5
        rec.ymin = o1.ymin - 5

        # # Top right
        o2 = die << gf.components.circle(radius=radius, layer=layer)
        o2.xmax = die.xmax - radius * 2
        o2.ymax = die_y_max - radius * 2
        rec = die << gf.c.rectangle(
            size=(o2.xsize + 10, o2.ysize + 10), layer=(118, 40)
        )
        rec.xmin = o2.xmin - 5
        rec.ymin = o2.ymin - 5

        # Bottom right
        o3 = die << gf.components.circle(radius=radius, layer=layer)
        o3.xmax = die.xmax - radius * 2
        o3.ymin = die_y_min + extra_bot_top_space - radius
        rec = die << gf.c.rectangle(
            size=(o3.xsize + 10, o3.ysize + 10), layer=(118, 40)
        )
        rec.xmin = o3.xmin - 5
        rec.ymin = o3.ymin - 5

    # Convert and save the json for LAB
    json_writer.conversion_json_and_internal(sim_filename)
    json_writer.save()
