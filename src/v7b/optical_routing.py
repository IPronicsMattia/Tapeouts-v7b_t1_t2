import gdsfactory as gf
import iprlayout_tower as ipr
import numpy as np

import v7b
from v7b.pdk import (
    custom_sin_cross_compensation,
    mzi_cell,
    spaced_bend,
)


def optical_routing(
    die: gf.Component,
    meshes: list,
    mua_in: list,
    mua_out: list,
    ec_in: list,
    ec_out: list,
):
    """This function places the components in the DIE"""

    die = gf.get_component(die)
    pdk = ipr.get_pdk()
    pdk.activate()

    #############################
    # Helpers                   #
    #############################
    def _generate_seeded_array(x, seed, bound) -> list:
        rng = np.random.default_rng(seed)
        return rng.uniform(-bound, bound, size=x).tolist()

    #############################
    # Cross sections            #
    #############################
    xs = gf.get_cross_section("strip", width=0.41, radius_min=3.0)
    xs_w = gf.get_cross_section("strip", width=0.93)
    xs_n1 = gf.get_cross_section("nitride", width=1)
    # xs_n = gf.get_cross_section("nitride2", width=2)
    xs_n = gf.cross_section.cross_section(width=2,
                                          radius=5,
                                          radius_min=5,
                                          layer=(259, 0),
                                          main_section_name="anwgt")

    #############################
    # Definitions               #
    #############################
    cross3D = ipr.crossing_3D(
        cross_section1=xs_w,
        cross_section2=xs_n,
        length1=1.5,
        length2=0.93,
        angle=90,
    )
    randoms = _generate_seeded_array(71, seed=42, bound=0.142)
    matrix_kwargs = dict(
        cross_section1=xs_w,
        cross_section2=xs_n,
        crossing=cross3D,
        separation1=125.5,  # Between SiN
        separation2=3.2,  # Between Si
        separation_random1=0,
        separation_random2=randoms,
    )
    matrix_comp_kwargs = dict(
        cross_section1=xs_w,
        cross_section2=xs_n,
        crossing=cross3D,
        separation1=88.5,  # Between SiN
        separation2=3.2,  # Between Si
        separation_random1=0,
        separation_random2=randoms[::-1],
    )

    #############################
    # Components                #
    #############################
    anwg_si_transition = ipr.si_anwg_transition(width_out=2)
    nwg_si_transition = ipr.si_nwg_transition(width_in=0.41, width_out=1)
    bend_r5 = spaced_bend()
    splitter = ipr.mmi(name="mmi_inv_d3", version="30nm")
    taper = ipr.rib_taper(width1=0.41, width2=0.93, cross_section=xs)
    cross3D = ipr.crossing_3D(
        cross_section1=xs_w, cross_section2=xs_n, length1=2, length2=0.93, angle=90
    )
    aux_bend = ipr.bend_with_taper(bend_r5, taper)
    psr = ipr.si_psr_tw()
    absorber = ipr.rib_absorber(cross_section=xs)
    loop_sin_si_transition = ipr.si_anwg_transition(
        name_si_nwg_transition="VT1_PI_D0_100",
        name_nwg_anwg_transition="VT2_POLINS_D_02",
        width_out=0.7,
    )
    ac = ipr.bend_bezier_s_custom_width(layer_RIB=xs.layer)

    #############################
    # EC IN  TRIANGLES          #
    #############################
    triangle_right_ref = die << ipr.crossing_3D_matrix(
        **matrix_kwargs,
        n_start_columns=1,
        n_crossings=35,
    )
    triangle_right_ref.rotate(180)
    triangle_right_ref.move(
        (triangle_right_ref["o2"].x, triangle_right_ref.ymax),
        (ec_in[0][70].x, ec_in[0][71].y - 289),
    )

    triangle_left_ref = die << ipr.crossing_3D_matrix(
        **matrix_kwargs,
        n_start_columns=36,
        n_crossings=36,
    )
    triangle_left_ref.rotate(180)
    triangle_left_ref.move(
        (triangle_left_ref["o37"].x, triangle_left_ref["o1"].y),
        (ec_in[0][35].x, triangle_right_ref["o1"].y),
    )

    ec_sin_output = []
    ec_si_output = []
    top_si_inputs = []
    top_sin_inputs = []
    bot_sin_outputs = []
    right_conex = []
    left_conex = []

    for i in range(35):
        st_ref = die << gf.c.straight(1, cross_section=xs_w)
        st_ref.connect("o1", triangle_right_ref[f"o{1 + i * 2}"])
        top_si_inputs.append(st_ref["o2"])

        right_conex.append(triangle_right_ref[f"o{71 + i}"])

        cross3d_comp_ref = die << custom_sin_cross_compensation(70 - i, randoms)
        cross3d_comp_ref.connect("o1", triangle_right_ref[f"o{2 + i * 2}"])
        tran_ref = die << anwg_si_transition
        tran_ref.connect("o2", cross3d_comp_ref["o2"])
        top_sin_inputs.append(tran_ref["o1"])

        st_ref = die << gf.c.straight(1, cross_section=xs_n)
        st_ref.connect("o1", triangle_right_ref[f"o{140 - i}"])
        tran_ref = die << anwg_si_transition
        tran_ref.connect("o2", st_ref["o2"])
        bot_sin_outputs.append(tran_ref["o1"])

        ec_sin_output.append(ec_in[0][70 - i])
        ec_si_output.append(ec_in[1][71 - i])

    for i in range(36):
        st_ref = die << gf.c.straight(1, cross_section=xs_w)
        st_ref.connect("o1", triangle_left_ref[f"o{36 + i * 2}"])
        top_si_inputs.append(st_ref["o2"])

        if i < 35:
            left_conex.append(triangle_left_ref[f"o{35 - i}"])

        cross3d_comp_ref = die << custom_sin_cross_compensation(35 - i, randoms)
        cross3d_comp_ref.connect("o1", triangle_left_ref[f"o{37 + i * 2}"])
        tran_ref = die << anwg_si_transition
        tran_ref.connect("o2", cross3d_comp_ref["o2"])
        top_sin_inputs.append(tran_ref["o1"])

        st_ref = die << gf.c.straight(1, cross_section=xs_n)
        st_ref.connect("o1", triangle_left_ref[f"o{214 - i}"])
        tran_ref = die << anwg_si_transition
        tran_ref.connect("o2", st_ref["o2"])
        bot_sin_outputs.append(tran_ref["o1"])

        ec_sin_output.append(ec_in[0][35 - i])
        ec_si_output.append(ec_in[1][36 - i])

    for k, comp in enumerate(left_conex):
        gf.routing.route_single(
            die,
            comp,
            right_conex[k],
            bend=bend_r5,
            cross_section=xs_w,
            auto_taper=False,
        )

    for k, comp in enumerate(ec_si_output):
        bend_ref = die << bend_r5
        bend_ref.connect("o1", comp, mirror=True)
        bend_ref2 = die << bend_r5
        bend_ref2.connect("o1", bend_ref["o2"])
        tap_ref = die << taper
        tap_ref.connect("o1", bend_ref2["o2"])

        gf.routing.route_bundle(
            die,
            [tap_ref["o2"]],
            [top_si_inputs[k]],
            bend=aux_bend,
            min_straight_taper=1,
            route_width=0.93,
            cross_section="strip",
        )

    gf.routing.route_bundle(
        die, ec_sin_output, top_sin_inputs, bend=bend_r5, cross_section=xs
    )

    st_ref = die << gf.c.straight(7.605, cross_section=xs)
    st_ref.connect("o1", ec_in[0][71])
    tran_ref = die << anwg_si_transition
    tran_ref.connect("o1", st_ref["o2"])

    cross3d_comp_ref = die << custom_sin_cross_compensation(71, randoms)
    cross3d_comp_ref.connect("o2", tran_ref["o2"])
    tran_ref = die << anwg_si_transition
    tran_ref.connect("o2", cross3d_comp_ref["o1"])

    bot_sin_outputs.insert(0, tran_ref["o1"])

    #############################
    # TE INPUT COMPENSTAION     #
    #############################
    bend_ref = die << bend_r5
    bend_ref.connect("o1", ec_in[1][0], mirror=True)
    bend_ref2 = die << bend_r5
    bend_ref2.connect("o1", bend_ref["o2"])
    tap_ref = die << taper
    tap_ref.connect("o1", bend_ref2["o2"])
    st_ref = die << gf.c.straight(100.921, cross_section=xs_w)
    st_ref.connect("o1", tap_ref["o2"])
    tap_ref = die << taper
    tap_ref.connect("o2", st_ref["o2"])
    bend_ref = die << bend_r5
    bend_ref.connect("o2", tap_ref["o1"])
    tap_ref = die << taper
    tap_ref.connect("o1", bend_ref["o1"])
    st_ref = die << gf.c.straight(91.745, cross_section=xs_w)
    st_ref.connect("o1", tap_ref["o2"])

    triangle_comp_ref = die << ipr.crossing_3D_matrix(
        **matrix_comp_kwargs,
        n_start_columns=1,
        n_crossings=71,
    )
    triangle_comp_ref.move(
        (triangle_comp_ref.xmax, triangle_comp_ref["o212"].y),
        (st_ref["o2"].x - 1, triangle_left_ref["o108"].y),
    )

    for i in range(71):
        sin_ext = die << gf.c.rectangle(
            (5, 2), (259, 0), port_type="optical", port_orientations=[0]
        )
        sin_ext.connect("o1", triangle_comp_ref[f"o{284 - i}"])
        sin_ext = die << gf.c.rectangle(
            (5, 2), (259, 0), port_type="optical", port_orientations=[0]
        )
        sin_ext.connect("o1", triangle_comp_ref[f"o{2 + i * 2}"])

    gf.routing.route_single(
        die,
        triangle_comp_ref["o213"],
        st_ref["o2"],
        cross_section=xs_w,
        auto_taper=False,
    )
    for i in range(1, 71):
        gf.routing.route_single(
            die,
            triangle_comp_ref[f"o{142 + i}"],
            triangle_left_ref[f"o{178 - i}"],
            cross_section=xs_w,
            auto_taper=False,
        )
    outputs = []
    inputs = []
    for i in range(72):
        start_st_ref = die << gf.c.straight(1, cross_section=xs_w)
        if i == 0:
            start_st_ref.connect("o1", triangle_left_ref["o178"])
        else:
            start_st_ref.connect("o1", triangle_comp_ref[f"o{143 - i * 2}"])
        leng = 5 if i != 0 else 42
        st_ref = die << gf.c.straight(leng, cross_section=xs_w)
        st_ref.connect("o1", start_st_ref["o2"])
        tap_ref = die << taper
        tap_ref.connect("o2", st_ref["o2"])
        bend_ref = die << bend_r5
        bend_ref.connect("o1", tap_ref["o1"])
        tap_ref = die << taper
        tap_ref.connect("o1", bend_ref["o2"])
        st_ref = die << gf.c.straight(
            tap_ref["o1"].y - (triangle_comp_ref["o142"].y - 20), cross_section=xs_w
        )
        st_ref.connect("o1", tap_ref["o2"])

        if i <= 35:
            extra = 0
        else:
            extra = 317.5
        rib_comp = die << ipr.spiral_compensation(
            gf.c.straight(5 + 36.25 * i + extra, cross_section=xs_w),
            5,
            0,
            0,
            taper,
            gf.partial(spaced_bend),
        )
        rib_comp.connect("o1", st_ref["o2"], mirror=True)
        tap_ref = die << taper
        tap_ref.connect("o1", mua_in[0][-1 - i]["o2"])
        outputs.append(rib_comp["o2"])
        inputs.append(tap_ref["o2"])

    inputs.reverse()
    gf.routing.route_bundle(
        die,
        inputs,
        outputs,
        bend=aux_bend,
        min_straight_taper=1,
        sort_ports=True,
        route_width=0.93,
        cross_section="strip",
        separation=3,
    )

    #############################
    # TM INPUT COMPENSTAION     #
    #############################
    out = []
    inp = []
    for i in range(72):
        tap_ref = die << taper
        tap_ref.connect("o1", mua_in[1][i]["o2"])
        st_ref = die << gf.c.straight(60, cross_section=xs_w)
        st_ref.connect("o1", tap_ref["o2"])

        if i < 36:
            extra = 0
        else:
            extra = 317.5
        rib_comp = die << ipr.spiral_compensation(
            gf.c.straight(56.25 * i + extra + 5, cross_section=xs_w),
            5,
            0,
            0,
            taper,
            gf.partial(spaced_bend),
        )
        rib_comp.connect("o1", st_ref["o2"])
        inp.append(rib_comp["o2"])

        tap_ref = die << taper
        tap_ref.connect("o1", bot_sin_outputs[-1 - i])
        out.append(tap_ref["o2"])

    out.reverse()
    for k, comp in enumerate(inp[::-1]):
        gf.routing.route_bundle(
            die,
            [out[k]],
            [comp],
            bend=aux_bend,
            cross_section="strip",
            route_width=0.93,
            start_straight_length=1 + 4 * k,
        )

    #############################
    # EC OUT TRIANGLES          #
    #############################
    triangle_left_ref = die << ipr.crossing_3D_matrix(
        **matrix_kwargs,
        n_start_columns=1,
        n_crossings=35,
    )
    triangle_left_ref.move(
        (triangle_left_ref["o2"].x, triangle_left_ref.ymin),
        (ec_out[0][1].x, ec_out[0][71].y + 289),
    )

    triangle_right_ref = die << ipr.crossing_3D_matrix(
        **matrix_kwargs,
        n_start_columns=36,
        n_crossings=36,
    )
    triangle_right_ref.move(
        (triangle_right_ref["o37"].x, triangle_right_ref["o1"].y),
        (ec_out[0][36].x, triangle_left_ref["o1"].y),
    )

    ec_sin_output = []
    ec_si_output = []
    top_si_inputs = []
    top_sin_inputs = []
    bot_sin_outputs = []
    right_conex = []
    left_conex = []

    for i in range(35):
        st_ref = die << gf.c.straight(1, cross_section=xs_w)
        st_ref.connect("o1", triangle_left_ref[f"o{1 + i * 2}"])
        top_si_inputs.append(st_ref["o2"])

        right_conex.append(triangle_left_ref[f"o{71 + i}"])

        cross3d_comp_ref = die << custom_sin_cross_compensation(70 - i, randoms)
        cross3d_comp_ref.connect("o1", triangle_left_ref[f"o{2 + i * 2}"])
        tran_ref = die << anwg_si_transition
        tran_ref.connect("o2", cross3d_comp_ref["o2"])
        top_sin_inputs.append(tran_ref["o1"])

        st_ref = die << gf.c.straight(1, cross_section=xs_n)
        st_ref.connect("o1", triangle_left_ref[f"o{140 - i}"])
        tran_ref = die << anwg_si_transition
        tran_ref.connect("o2", st_ref["o2"])
        bot_sin_outputs.append(tran_ref["o1"])

        ec_sin_output.append(ec_out[0][1 + i])
        ec_si_output.append(ec_out[1][i])

    for i in range(36):
        st_ref = die << gf.c.straight(1, cross_section=xs_w)
        st_ref.connect("o1", triangle_right_ref[f"o{36 + i * 2}"])
        top_si_inputs.append(st_ref["o2"])

        if i < 35:
            left_conex.append(triangle_right_ref[f"o{35 - i}"])

        cross3d_comp_ref = die << custom_sin_cross_compensation(35 - i, randoms)
        cross3d_comp_ref.connect("o1", triangle_right_ref[f"o{37 + i * 2}"])
        tran_ref = die << anwg_si_transition
        tran_ref.connect("o2", cross3d_comp_ref["o2"])
        top_sin_inputs.append(tran_ref["o1"])

        st_ref = die << gf.c.straight(1, cross_section=xs_n)
        st_ref.connect("o1", triangle_right_ref[f"o{214 - i}"])
        tran_ref = die << anwg_si_transition
        tran_ref.connect("o2", st_ref["o2"])
        bot_sin_outputs.append(tran_ref["o1"])

        ec_sin_output.append(ec_out[0][36 + i])
        ec_si_output.append(ec_out[1][35 + i])

    for k, comp in enumerate(left_conex):
        gf.routing.route_bundle(
            die,
            [comp],
            [right_conex[k]],
            bend=aux_bend,
            route_width=0.93,
            cross_section="strip",
            auto_taper=False,
        )

    for k, comp in enumerate(ec_si_output):
        bend_ref = die << bend_r5
        bend_ref.connect("o1", comp, mirror=True)
        bend_ref2 = die << bend_r5
        bend_ref2.connect("o1", bend_ref["o2"])
        tap_ref = die << taper
        tap_ref.connect("o1", bend_ref2["o2"])

        gf.routing.route_bundle(
            die,
            [tap_ref["o2"]],
            [top_si_inputs[k]],
            bend=aux_bend,
            min_straight_taper=1,
            route_width=0.93,
            cross_section="strip",
        )

    gf.routing.route_bundle(
        die,
        ec_sin_output,
        top_sin_inputs,
        bend=bend_r5,
        cross_section=xs,
    )

    st_ref = die << gf.c.straight(7.605, cross_section=xs)
    st_ref.connect("o1", ec_out[0][0])
    tran_ref = die << anwg_si_transition
    tran_ref.connect("o1", st_ref["o2"])

    cross3d_comp_ref = die << custom_sin_cross_compensation(71, randoms)
    cross3d_comp_ref.connect("o2", tran_ref["o2"])
    tran_ref = die << anwg_si_transition
    tran_ref.connect("o2", cross3d_comp_ref["o1"])

    bot_sin_outputs.insert(0, tran_ref["o1"])

    #############################
    # TM OUTPUT COMPENSTAION    #
    #############################
    bend_ref = die << bend_r5
    bend_ref.connect("o1", ec_out[1][71], mirror=True)
    bend_ref2 = die << bend_r5
    bend_ref2.connect("o1", bend_ref["o2"])
    tap_ref = die << taper
    tap_ref.connect("o1", bend_ref2["o2"])
    st_ref = die << gf.c.straight(100.921, cross_section=xs_w)
    st_ref.connect("o1", tap_ref["o2"])
    tap_ref = die << taper
    tap_ref.connect("o2", st_ref["o2"])
    bend_ref = die << bend_r5
    bend_ref.connect("o2", tap_ref["o1"])
    tap_ref = die << taper
    tap_ref.connect("o1", bend_ref["o1"])
    st_ref = die << gf.c.straight(91.745, cross_section=xs_w)
    st_ref.connect("o1", tap_ref["o2"])

    triangle_comp_ref = die << ipr.crossing_3D_matrix(
        **matrix_comp_kwargs,
        n_start_columns=1,
        n_crossings=71,
    )
    triangle_comp_ref.rotate(180)
    triangle_comp_ref.move(
        (triangle_comp_ref.xmin, triangle_comp_ref["o213"].y),
        (st_ref["o2"].x + 1, st_ref["o1"].y),
    )

    for i in range(71):
        sin_ext = die << gf.c.rectangle(
            (5, 2), (259, 0), port_type="optical", port_orientations=[0]
        )
        sin_ext.connect("o1", triangle_comp_ref[f"o{284 - i}"])
        sin_ext = die << gf.c.rectangle(
            (5, 2), (259, 0), port_type="optical", port_orientations=[0]
        )
        sin_ext.connect("o1", triangle_comp_ref[f"o{2 + i * 2}"])

    gf.routing.route_single(
        die,
        triangle_comp_ref["o213"],
        st_ref["o2"],
        cross_section=xs_w,
        auto_taper=False,
    )
    for i in range(1, 71):
        gf.routing.route_single(
            die,
            triangle_comp_ref[f"o{213 - i}"],
            triangle_right_ref[f"o{107 + i}"],
            cross_section=xs_w,
            auto_taper=False,
        )

    for i in range(72):
        start_st_ref = die << gf.c.straight(1, cross_section=xs_w)
        if i == 0:
            start_st_ref.connect("o1", triangle_right_ref["o178"])
        else:
            start_st_ref.connect("o1", triangle_comp_ref[f"o{143 - i * 2}"])
        leng = 5 if i != 0 else 42
        st_ref = die << gf.c.straight(leng, cross_section=xs_w)
        st_ref.connect("o1", start_st_ref["o2"])
        tap_ref = die << taper
        tap_ref.connect("o2", st_ref["o2"])
        bend_ref = die << bend_r5
        bend_ref.connect("o1", tap_ref["o1"])
        tap_ref = die << taper
        tap_ref.connect("o1", bend_ref["o2"])
        st_ref = die << gf.c.straight(
            (triangle_comp_ref["o142"].y + 20) - tap_ref["o1"].y, cross_section=xs_w
        )
        st_ref.connect("o1", tap_ref["o2"])

        if i < 36:
            extra = 0
        else:
            extra = 317.5
        rib_comp = die << ipr.spiral_compensation(
            gf.c.straight(36.425 * i + extra + 5 + 13.625, cross_section=xs_w),
            5,
            0,
            0,
            taper,
            gf.partial(spaced_bend),
        )
        rib_comp.connect("o1", st_ref["o2"], mirror=True)

        # Placing a taper to the MUA output to have in the correct cross-section
        tap_ref = die << taper
        tap_ref.connect("o1", mua_out[1][i]["o4"])

        gf.routing.route_single(
            die,
            rib_comp["o2"],
            tap_ref["o2"],
            cross_section=xs_w,
            auto_taper=False,
            bend=bend_r5,
        )

    #############################
    # TE OUTPUT COMPENSTAION    #
    #############################
    out = []
    inp = []
    aux = []
    for i in range(72):
        tap_ref = die << taper
        tap_ref.connect("o1", mua_out[0][i]["o4"])

        st_ref = die << gf.c.straight(60, cross_section=xs_w)
        st_ref.connect("o1", tap_ref["o2"])

        aux.append(st_ref["o2"])

        tap_ref = die << taper
        tap_ref.connect("o1", bot_sin_outputs[i])
        out.append(tap_ref["o2"])

    for i in range(72):
        if i < 36:
            extra = 0
        else:
            extra = 317.5
        rib_comp = die << ipr.spiral_compensation(
            gf.c.straight(56.075 * i + extra + 5, cross_section=xs_w),
            5,
            0,
            0,
            taper,
            gf.partial(spaced_bend),
        )
        rib_comp.connect("o1", aux[-1 - i])
        inp.append(rib_comp["o2"])

    out.reverse()
    for k, comp in enumerate(inp):
        gf.routing.route_bundle(
            die,
            [out[k]],
            [comp],
            bend=aux_bend,
            cross_section="strip",
            route_width=0.93,
            start_straight_length=280.03 - 3.93 * k,
        )

    #############################
    # Core demultiplexer        #
    #############################
    muas = []
    demux_in = []
    for i in range(72):
        muas.append(mua_in[0][71 - i]["o4"])
        demux_in.append(meshes[0][f"o{1 + i}"])

    gf.routing.route_bundle(
        die,
        demux_in,
        muas,
        bend=bend_r5,
        taper=taper,
        min_straight_taper=1,
        cross_section="strip",
        separation=3.59,
        sort_ports=True,
        steps=[{"dx": -170, "dy": 50}, {"dy": 1}],
        end_straight_length=55,
    )

    muas = []
    demux_in = []
    for i in range(72):
        muas.append(mua_in[1][71 - i]["o4"])
        demux_in.append(meshes[1][f"o{1 + i}"])

    gf.routing.route_bundle(
        die,
        demux_in,
        muas,
        bend=bend_r5,
        taper=taper,
        min_straight_taper=1,
        cross_section="strip",
        separation=3.59,
        sort_ports=True,
        steps=[{"dx": -170, "dy": 50}, {"dy": 1}],
        end_straight_length=55,
    )

    #############################
    # Core multiplexer          #
    #############################
    muas = []
    mux_in = []
    for i in range(72):
        tran_ref = die << taper
        tran_ref.connect("o1", mua_out[0][i]["o2"])
        muas.append(tran_ref["o2"])
        tran_ref = die << taper
        tran_ref.connect("o1", meshes[0][f"o{73 + i}"])
        mux_in.append(tran_ref["o2"])

    gf.routing.route_bundle(
        die,
        mux_in,
        muas,
        bend=aux_bend,
        cross_section="strip",
        route_width=0.93,
        separation=3,
        sort_ports=True,
        steps=[
            {"dx": 225.815, "dy": -50},
            {"dy": -1},  # Unnecessary but the function complains if not placed
        ],
        end_straight_length=29.484,
    )

    muas = []
    mux_in = []
    for i in range(72):
        tran_ref = die << taper
        tran_ref.connect("o1", mua_out[1][i]["o2"])
        muas.append(tran_ref["o2"])
        tran_ref = die << taper
        tran_ref.connect("o1", meshes[1][f"o{73 + i}"])
        mux_in.append(tran_ref["o2"])

    gf.routing.route_bundle(
        die,
        mux_in,
        muas,
        bend=aux_bend,
        route_width=0.93,
        cross_section="strip",
        separation=3,
        sort_ports=True,
        steps=[
            {"dx": 225.815, "dy": -50},
            {"dy": -1},  # Unnecessary but the function complains if not placed
        ],
        end_straight_length=29.484,
    )

    #############################
    # Neff & Ng                 #
    #############################
    # Silicon 0.41
    out = []
    inp = []
    mzi1 = die << mzi_cell(splitter=splitter, order_mzi_length=9.5054)
    mzi1.rotate(180)
    mzi1.move((mzi1.x, mzi1.ymin), (-5556 + 63.5, 11850))
    inp.extend((mzi1["o1"], mzi1["o2"]))

    mzi2 = die << mzi_cell(splitter=splitter, order_mzi_length=95.0535)
    mzi2.rotate(180)
    mzi2.move((mzi2.x, mzi2.ymin), (-5302 + 63.5, 11850))
    inp.extend((mzi2["o1"], mzi2["o2"]))

    search_area = (-5600.91, 12074.98, -5104.21, 12535.24)
    up_ec_matrix = v7b.build_matrix(die, "ec_main*", area=search_area)

    for i in range(4):
        mzi = mzi1 if i < 2 else mzi2
        abs_ref = die << absorber
        abs_ref.connect("o1", mzi[f"o{3 + i % 2 }"], mirror=i % 2 == 0)
        vt_ref1 = die << loop_sin_si_transition
        vt_ref1.connect("o2", up_ec_matrix[0][i]["o1"])
        out.append(vt_ref1["o1"])

    for i, start in enumerate(out):
        gf.routing.route_single(
            die,
            start,
            inp[i],
            bend=bend_r5,
            cross_section=xs,
            auto_taper=False,
        )

    # Silicon 1.0
    out = []
    inp = []
    mzi1 = die << mzi_cell(
        splitter=splitter,
        order_mzi_length=22.222,
        cross_section2=xs_w,
        extra_component=taper,
    )
    mzi1.rotate(180)
    mzi1.move((mzi1.x, mzi1.ymin), (5111 + 63.5, 11850))
    inp.extend((mzi1["o1"], mzi1["o2"]))

    mzi2 = die << mzi_cell(
        splitter=splitter,
        order_mzi_length=80,
        cross_section2=xs_w,
        extra_component=taper,
    )
    mzi2.rotate(180)
    mzi2.move((mzi2.x, mzi2.ymin), (5365 + 63.5, 11850))
    inp.extend((mzi2["o1"], mzi2["o2"]))

    search_area = (5069.16, 12084.79, 5569.95, 12533.72)
    up_ec_matrix = v7b.build_matrix(die, "ec_main*", area=search_area)

    for i in range(4):
        mzi = mzi1 if i < 2 else mzi2
        abs_ref = die << absorber
        abs_ref.connect("o1", mzi[f"o{3 + i % 2 }"], mirror=i % 2 == 0)
        vt_ref1 = die << loop_sin_si_transition
        vt_ref1.connect("o2", up_ec_matrix[0][i]["o1"])
        out.append(vt_ref1["o1"])

    for i, start in enumerate(out):
        gf.routing.route_single(
            die,
            start,
            inp[i],
            bend=bend_r5,
            cross_section=xs,
            auto_taper=False,
        )

    # Silicon Nitride 1.0
    out = []
    inp = []
    mzi1 = die << mzi_cell(
        splitter=ipr.mmi(name="mmi_inv_d3", version="30nm"),
        order_mzi_length=30.846,
        cross_section2=xs_n1,
        extra_component=nwg_si_transition,
    )
    mzi1.move((mzi1.x, mzi1.ymax), (-5492 + 63.5, -11850))
    inp.extend((mzi1["o2"], mzi1["o1"]))

    mzi2 = die << mzi_cell(
        splitter=ipr.mmi(name="mmi_inv_d3", version="30nm"),
        order_mzi_length=61.693,
        cross_section2=xs_n1,
        extra_component=nwg_si_transition,
    )
    mzi2.move((mzi2.x, mzi2.ymax), (-5238 + 63.5, -11850))
    inp.extend((mzi2["o2"], mzi2["o1"]))

    search_area = (-5539.61, -12536.53, -5059.49, -12070.76)
    up_ec_matrix = v7b.build_matrix(die, "ec_main*", area=search_area)

    for i in range(4):
        mzi = mzi1 if i < 2 else mzi2
        abs_ref = die << absorber
        abs_ref.connect("o1", mzi[f"o{3 + i % 2 }"], mirror=i % 2 == 0)
        vt_ref1 = die << loop_sin_si_transition
        vt_ref1.connect("o2", up_ec_matrix[0][i]["o1"])
        out.append(vt_ref1["o1"])

    for i, start in enumerate(out):
        gf.routing.route_single(
            die,
            start,
            inp[i],
            bend=bend_r5,
            cross_section=xs,
            auto_taper=False,
        )

    # Advanced Silicon Nitride 1.0
    out = []
    inp = []
    mzi1 = die << mzi_cell(
        splitter=ipr.mmi(name="mmi_inv_d3", version="30nm"),
        order_mzi_length=33.123,
        cross_section2=xs_n,
        extra_component=anwg_si_transition,
    )
    mzi1.move((mzi1.x, mzi1.ymax), (5175 + 63.5, -11800))
    inp.extend((mzi1["o2"], mzi1["o1"]))

    mzi2 = die << mzi_cell(
        splitter=ipr.mmi(name="mmi_inv_d3", version="30nm"),
        order_mzi_length=115.932,
        cross_section2=xs_n,
        extra_component=anwg_si_transition,
    )
    mzi2.move((mzi2.x, mzi2.ymax), (5429 + 63.5, -11800))
    inp.extend((mzi2["o2"], mzi2["o1"]))

    search_area = (5129.02, -12520.9, 5610.16, -12067.95)
    up_ec_matrix = v7b.build_matrix(die, "ec_main*", area=search_area)

    for i in range(4):
        mzi = mzi1 if i < 2 else mzi2
        abs_ref = die << absorber
        abs_ref.connect("o1", mzi[f"o{3 + i % 2 }"], mirror=i % 2 == 0)
        vt_ref1 = die << loop_sin_si_transition
        vt_ref1.connect("o2", up_ec_matrix[0][i]["o1"])
        out.append(vt_ref1["o1"])

    for i, start in enumerate(out):
        gf.routing.route_single(
            die,
            start,
            inp[i],
            bend=bend_r5,
            cross_section=xs,
            auto_taper=False,
        )

    #############################
    # Loops                     #
    #############################
    # Left side
    out = []
    inp = []
    search_area = (-6100, 12047.34, -4728.40, 12548.72)
    up_ec_matrix = v7b.build_matrix(die, "ec_main*", area=search_area)
    search_area = (-6050, -12544.08, -4667.14, -12072.79)
    lw_ec_matrix = v7b.build_matrix(die, "ec_main*", area=search_area)
    search_area = (-11391.97, 10065.26, -11187.37, 10384.81)
    mua_matrix = v7b.build_matrix(die, "pucmua*", area=search_area)

    for i in range(2):
        vt_ref1 = die << loop_sin_si_transition
        vt_ref1.connect("o2", up_ec_matrix[0][i * 2]["o1"])
        vt_ref2 = die << loop_sin_si_transition
        vt_ref2.connect("o2", up_ec_matrix[0][1 + i * 2]["o1"])

        gf.routing.route_single(
            die,
            vt_ref1["o1"],
            vt_ref2["o1"],
            cross_section=xs,
            bend=bend_r5,
            auto_taper=False,
        )

    for i in range(2):
        vt_ref1 = die << loop_sin_si_transition
        vt_ref1.connect("o2", lw_ec_matrix[0][i * 2]["o1"])
        vt_ref2 = die << loop_sin_si_transition
        vt_ref2.connect("o2", lw_ec_matrix[0][1 + i * 2]["o1"])

        gf.routing.route_single(
            die,
            vt_ref1["o1"],
            vt_ref2["o1"],
            cross_section=xs,
            bend=bend_r5,
            auto_taper=False,
        )

    vt_ref = die << loop_sin_si_transition
    vt_ref.connect("o2", up_ec_matrix[0][10]["o1"])
    st_ref = die << gf.c.straight(1, cross_section=xs)
    st_ref.connect("o1", vt_ref["o1"])
    psr_ref = die << psr
    psr_ref.connect("o2", st_ref["o2"], mirror=True)
    ac_ref1 = die << ac
    ac_ref1.connect("o1", psr_ref["o3"], mirror=True)
    ac_ref2 = die << ac
    ac_ref2.connect("o1", psr_ref["o4"])
    abs_ref = die << absorber
    abs_ref.connect("o1", psr_ref["o1"])
    out.extend((ac_ref1["o2"], ac_ref2["o2"]))

    for i in range(2):
        st_ref = die << gf.c.straight(0, cross_section=xs)
        st_ref.connect("o1", mua_matrix[0][i]["o2"])
        inp.append(st_ref["o2"])

    gf.routing.route_bundle(
        die,
        out,
        inp,
        taper=taper,
        bend=bend_r5,
        min_straight_taper=1,
        cross_section="strip",
        separation=4.53,
        start_straight_length=110,
    )
    out.clear()

    aux = []
    aux2 = []
    for i in range(5):
        st_ref = die << gf.c.straight(10, cross_section=xs_w)
        st_ref.rotate(-90)
        st_ref.move((st_ref.x, st_ref.y), (-11570 + 4.93 * i, 9780))
        aux.append(st_ref["o1"])
        aux2.append(st_ref["o2"])

    for i in range(1):
        vt_ref = die << loop_sin_si_transition
        vt_ref.connect("o2", up_ec_matrix[0][8 + i]["o1"])
        tap_ref = die << taper
        tap_ref.connect("o1", vt_ref["o1"])
        out.append(tap_ref["o2"])

    vt_ref = die << loop_sin_si_transition
    vt_ref.connect("o2", up_ec_matrix[0][9]["o1"])
    st_ref = die << gf.c.straight(1, cross_section=xs)
    st_ref.connect("o1", vt_ref["o1"])
    psr_ref = die << psr
    psr_ref.connect("o2", st_ref["o2"], mirror=True)
    abs_ref = die << absorber
    abs_ref.connect("o1", psr_ref["o1"])
    ac_ref1 = die << ac
    ac_ref1.connect("o1", psr_ref["o3"], mirror=True)
    tap_ref = die << taper
    tap_ref.connect("o1", ac_ref1["o2"])
    out.append(tap_ref["o2"])
    ac_ref2 = die << ac
    ac_ref2.connect("o1", psr_ref["o4"])
    tap_ref = die << taper
    tap_ref.connect("o1", ac_ref2["o2"])
    out.append(tap_ref["o2"])

    for i in range(2):
        tap_ref = die << taper
        tap_ref.connect("o1", mua_matrix[0][i]["o4"])
        out.append(tap_ref["o2"])

    gf.routing.route_bundle(
        die,
        out[:3],
        aux[:3],
        bend=aux_bend,
        cross_section=xs_w,
        separation=4,
        sort_ports=True,
        start_straight_length=75.61,
    )
    gf.routing.route_bundle(
        die,
        out[3:],
        aux[3:],
        bend=aux_bend,
        cross_section=xs_w,
        separation=4,
        sort_ports=True,
        start_straight_length=30,
    )
    out.clear()

    for i in range(1):
        vt_ref = die << loop_sin_si_transition
        vt_ref.connect("o2", lw_ec_matrix[0][8 + i]["o1"])
        tap_ref = die << taper
        tap_ref.connect("o1", vt_ref["o1"])
        out.append(tap_ref["o2"])

    for i in range(2):
        vt_ref = die << loop_sin_si_transition
        vt_ref.connect("o2", lw_ec_matrix[0][9 + i]["o1"])
        st_ref = die << gf.c.straight(1, cross_section=xs)
        st_ref.connect("o1", vt_ref["o1"])
        psr_ref = die << psr
        psr_ref.connect("o2", st_ref["o2"], mirror=True)
        abs_ref = die << absorber
        abs_ref.connect("o1", psr_ref["o1"])
        ac_ref1 = die << ac
        ac_ref1.connect("o1", psr_ref["o3"], mirror=True)
        tap_ref = die << taper
        tap_ref.connect("o1", ac_ref1["o2"])
        out.append(tap_ref["o2"])
        ac_ref2 = die << ac
        ac_ref2.connect("o1", psr_ref["o4"])
        tap_ref = die << taper
        tap_ref.connect("o1", ac_ref2["o2"])
        out.append(tap_ref["o2"])

    gf.routing.route_bundle(
        die,
        out,
        aux2,
        bend=aux_bend,
        cross_section=xs_w,
        separation=4,
        sort_ports=True,
        start_straight_length=100,
    )

    # Right side
    out = []
    inp = []
    search_area = (4697, 12052.86, 6034, 12541.63)
    up_ec_matrix = v7b.build_matrix(die, "ec_main*", area=search_area)
    search_area = (4761, -12539.66, 6100, -12048.73)
    lw_ec_matrix = v7b.build_matrix(die, "ec_main*", area=search_area)
    search_area = (6419.39, 9989.37, 6702.20, 10388.40)
    mua_matrix = v7b.build_matrix(die, "pucmua*", area=search_area)

    for i in range(2):
        vt_ref1 = die << loop_sin_si_transition
        vt_ref1.connect("o2", up_ec_matrix[0][7 + i * 2]["o1"])
        vt_ref2 = die << loop_sin_si_transition
        vt_ref2.connect("o2", up_ec_matrix[0][8 + i * 2]["o1"])

        gf.routing.route_single(
            die,
            vt_ref1["o1"],
            vt_ref2["o1"],
            cross_section=xs,
            bend=bend_r5,
            auto_taper=False,
        )

    for i in range(2):
        vt_ref1 = die << loop_sin_si_transition
        vt_ref1.connect("o2", lw_ec_matrix[0][7 + i * 2]["o1"])
        vt_ref2 = die << loop_sin_si_transition
        vt_ref2.connect("o2", lw_ec_matrix[0][8 + i * 2]["o1"])

        gf.routing.route_single(
            die,
            vt_ref1["o1"],
            vt_ref2["o1"],
            cross_section=xs,
            bend=bend_r5,
            auto_taper=False,
        )

    vt_ref = die << loop_sin_si_transition
    vt_ref.connect("o2", up_ec_matrix[0][0]["o1"])
    st_ref = die << gf.c.straight(1, cross_section=xs)
    st_ref.connect("o1", vt_ref["o1"])
    psr_ref = die << psr
    psr_ref.connect("o2", st_ref["o2"], mirror=True)
    ac_ref1 = die << ac
    ac_ref1.connect("o1", psr_ref["o3"], mirror=True)
    ac_ref2 = die << ac
    ac_ref2.connect("o1", psr_ref["o4"])
    abs_ref = die << absorber
    abs_ref.connect("o1", psr_ref["o1"])
    out.extend((ac_ref1["o2"], ac_ref2["o2"]))

    for i in range(2):
        st_ref = die << gf.c.straight(0, cross_section=xs)
        st_ref.connect("o1", mua_matrix[0][i]["o2"])
        inp.append(st_ref["o2"])

    gf.routing.route_bundle(
        die,
        out,
        inp,
        taper=taper,
        bend=bend_r5,
        min_straight_taper=1,
        cross_section="strip",
        separation=4.53,
        start_straight_length=167.85,
    )
    out.clear()

    aux = []
    aux2 = []
    for i in range(5):
        st_ref = die << gf.c.straight(10, cross_section=xs_w)
        st_ref.rotate(-90)
        st_ref.move((st_ref.x, st_ref.y), (11618 + 4.93 * i, 9780))
        aux.append(st_ref["o1"])
        aux2.append(st_ref["o2"])

    for i in range(2):
        tap_ref = die << taper
        tap_ref.connect("o1", mua_matrix[0][i]["o4"])
        out.append(tap_ref["o2"])

    vt_ref = die << loop_sin_si_transition
    vt_ref.connect("o2", up_ec_matrix[0][1]["o1"])
    st_ref = die << gf.c.straight(1, cross_section=xs)
    st_ref.connect("o1", vt_ref["o1"])
    psr_ref = die << psr
    psr_ref.connect("o2", st_ref["o2"], mirror=True)
    abs_ref = die << absorber
    abs_ref.connect("o1", psr_ref["o1"])
    ac_ref1 = die << ac
    ac_ref1.connect("o1", psr_ref["o3"], mirror=True)
    tap_ref = die << taper
    tap_ref.connect("o1", ac_ref1["o2"])
    out.append(tap_ref["o2"])
    ac_ref2 = die << ac
    ac_ref2.connect("o1", psr_ref["o4"])
    tap_ref = die << taper
    tap_ref.connect("o1", ac_ref2["o2"])
    out.append(tap_ref["o2"])

    for i in range(1):
        vt_ref = die << loop_sin_si_transition
        vt_ref.connect("o2", up_ec_matrix[0][2 + i]["o1"])
        tap_ref = die << taper
        tap_ref.connect("o1", vt_ref["o1"])
        out.append(tap_ref["o2"])

    gf.routing.route_bundle(
        die,
        out[:2],
        aux[:2],
        bend=aux_bend,
        cross_section=xs_w,
        separation=4,
        sort_ports=True,
        start_straight_length=40,
    )
    gf.routing.route_bundle(
        die,
        out[2:],
        aux[2:],
        bend=aux_bend,
        cross_section=xs_w,
        separation=4,
        sort_ports=True,
        start_straight_length=133.46,
    )
    out.clear()

    for i in range(1):
        vt_ref = die << loop_sin_si_transition
        vt_ref.connect("o2", lw_ec_matrix[0][2 - i]["o1"])
        tap_ref = die << taper
        tap_ref.connect("o1", vt_ref["o1"])
        out.append(tap_ref["o2"])

    for i in range(2):
        vt_ref = die << loop_sin_si_transition
        vt_ref.connect("o2", lw_ec_matrix[0][1 - i]["o1"])
        st_ref = die << gf.c.straight(1, cross_section=xs)
        st_ref.connect("o1", vt_ref["o1"])
        psr_ref = die << psr
        psr_ref.connect("o2", st_ref["o2"], mirror=True)
        ac_ref1 = die << ac
        ac_ref1.connect("o1", psr_ref["o3"], mirror=True)
        ac_ref2 = die << ac
        ac_ref2.connect("o1", psr_ref["o4"])
        abs_ref = die << absorber
        abs_ref.connect("o1", psr_ref["o1"])
        tap_ref = die << taper
        tap_ref.connect("o1", ac_ref2["o2"])
        out.append(tap_ref["o2"])
        tap_ref = die << taper
        tap_ref.connect("o1", ac_ref1["o2"])
        out.append(tap_ref["o2"])

    gf.routing.route_bundle(
        die,
        out,
        aux2,
        bend=aux_bend,
        cross_section=xs_w,
        separation=4,
        sort_ports=True,
        start_straight_length=75,
    )
