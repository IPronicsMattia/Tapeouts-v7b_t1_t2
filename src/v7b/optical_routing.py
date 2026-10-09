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
    xs_n = gf.get_cross_section("nitride2", width=2)

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
    # EC IN & OUT TRIANGLES     #
    #############################
    for jdx in range(2):
        # Select the EC depending on the case
        ec_to_be_used = ec_in if jdx == 0 else ec_out
        ec_port = 11 if jdx == 0 else 84
        ec_space = anwg_si_transition.xsize + 5
        extra = 2  # space due to crossing

        triangle_right_ref = die << ipr.crossing_3D_matrix(
            **matrix_kwargs,
            n_start_columns=1,
            n_crossings=35,
        )

        triangle_left_ref = die << ipr.crossing_3D_matrix(
            **matrix_kwargs,
            n_start_columns=36,
            n_crossings=36,
        )

        # Rotation and position are symmetric depeding on the case
        if jdx == 0:
            triangle_left_ref.rotate(180)
            triangle_left_ref.ymax = ec_to_be_used[0][ec_port].y - ec_space
        else:
            triangle_left_ref.ymin = ec_to_be_used[0][ec_port].y + ec_space
        triangle_left_ref.movex(
            triangle_left_ref["o107"].x, ec_to_be_used[0][ec_port].x
        )

        if jdx == 0:
            triangle_right_ref.rotate(180)
            triangle_right_ref.xmin = triangle_left_ref.xmax + 127 * 3 - extra
            triangle_right_ref.ymin = triangle_left_ref.ymin
        else:
            triangle_right_ref.xmax = triangle_left_ref.xmin - 127 * 3 + extra
            triangle_right_ref.ymax = triangle_left_ref.ymax

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

            # Condition changes because it changes where you find the central gap
            if jdx == 0:
                idx1 = 83 - i
                idx2 = 84 - i
            else:
                idx1 = 12 + i
                idx2 = 11 + i
            ec_sin_output.append(ec_to_be_used[0][idx1])
            ec_si_output.append(ec_to_be_used[1][idx2])

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

            # Condition changes because it changes where you find the central gap
            if jdx == 0:
                if i == 0:
                    idx1 = 46 - i
                    idx2 = 49
                else:
                    idx1 = 46 - i
                    idx2 = 47 - i
            else:
                if i == 0:
                    idx1 = 49 + i
                    idx2 = 46
                else:
                    idx1 = 49 + i
                    idx2 = 48 + i

            ec_sin_output.append(ec_to_be_used[0][idx1])
            ec_si_output.append(ec_to_be_used[1][idx2])

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
        st_ref.connect("o1", ec_to_be_used[0][95 - ec_port])
        tran_ref = die << anwg_si_transition
        tran_ref.connect("o1", st_ref["o2"])

        cross3d_comp_ref = die << custom_sin_cross_compensation(71, randoms)
        cross3d_comp_ref.connect("o2", tran_ref["o2"])
        tran_ref = die << anwg_si_transition
        tran_ref.connect("o2", cross3d_comp_ref["o1"])

        bot_sin_outputs.insert(0, tran_ref["o1"])

        #############################
        # TE IN & OUT COMPENSTAION  #
        #############################
        # Create the final triangle part of the crossing
        triangle_comp_ref = die << ipr.crossing_3D_matrix(
            **matrix_comp_kwargs,
            n_start_columns=1,
            n_crossings=71,
        )

        # Rotation and position are symmetric depeding on the case
        if jdx == 0:
            triangle_comp_ref.xmax = triangle_left_ref.xmin - 127 + extra
        else:
            triangle_comp_ref.rotate(180)
            triangle_comp_ref.xmin = triangle_left_ref.xmax + 127 + extra
        triangle_comp_ref.movey(
            triangle_comp_ref["o212"].y, triangle_left_ref["o108"].y
        )

        # Prepare the first edge coupler
        bend_ref = die << bend_r5
        bend_ref.connect("o1", ec_to_be_used[1][ec_port], mirror=True)
        bend_ref2 = die << bend_r5
        bend_ref2.connect("o1", bend_ref["o2"])
        tap_ref = die << taper
        tap_ref.connect("o1", bend_ref2["o2"])
        gf.routing.route_single(
            die,
            triangle_comp_ref["o213"],
            tap_ref["o2"],
            cross_section=xs_w,
            bend=aux_bend,
            auto_taper=False,
        )

        # Top and bottom taps
        for i in range(71):
            sin_ext = die << gf.c.rectangle(
                (5, 2), (259, 0), port_type="optical", port_orientations=[0]
            )
            sin_ext.connect("o1", triangle_comp_ref[f"o{284 - i}"])
            sin_ext = die << gf.c.rectangle(
                (5, 2), (259, 0), port_type="optical", port_orientations=[0]
            )
            sin_ext.connect("o1", triangle_comp_ref[f"o{2 + i * 2}"])

        # Connect the two triangles
        for i in range(1, 71):
            gf.routing.route_single(
                die,
                triangle_comp_ref[f"o{142 + i}"],
                triangle_left_ref[f"o{178 - i}"],
                cross_section=xs_w,
                auto_taper=False,
            )

        # Add compensation spiral
        inputs = []  # MUA output after taper
        outputs = [] # Mesh input after taper
        strt_bot_array = [] # Fix bottom part of the compensation
        strt_top_array = [] # Fix top part of the compensation
        for i in range(72):
            # Create straight at top and bottom that will contain the compensation
            strt_top = die << ipr.straight(length=1, cross_section=xs_w)
            strt_bot = die << ipr.straight(length=1, cross_section=xs_w)
            if jdx == 0:
                strt_top.rotate(90)
                strt_bot.rotate(90)
                strt_bot.movex(strt_bot["o1"].x, mua_in[0][71 - i]["o2"].x)
                strt_bot.movey(strt_bot["o1"].y, mua_in[0][71 - i]["o2"].y + 100)
                strt_top.x = strt_bot.x + 44
                strt_top.y = strt_bot.y + 220
            else:
                strt_top.rotate(-90)
                strt_bot.rotate(-90)
                strt_bot.movex(strt_bot["o1"].x, mua_out[1][71 - i]["o4"].x)
                strt_bot.movey(strt_bot["o1"].y, mua_out[1][71 - i]["o4"].y - 100)
                strt_top.x = strt_bot.x - 44
                strt_top.y = strt_bot.y - 220
            strt_bot_array.append(strt_bot)
            strt_top_array.append(strt_top)

            # Place a taper to the MUA
            if jdx == 0:
                tap_ref1 = die << taper
                tap_ref1.connect("o1", mua_in[0][71 - i]["o2"])
                tap_ref2 = die << taper
                tap_ref2.connect("o1", mua_in[0][71 - i]["o4"])
            else:
                tap_ref1 = die << taper
                tap_ref1.connect("o1", mua_out[1][71 - i]["o4"])
                tap_ref2 = die << taper
                tap_ref2.connect("o1", mua_out[1][71 - i]["o2"])

            # Route it MUA and straight
            gf.routing.route_single(
                die, strt_bot["o1"], tap_ref1["o2"], bend=aux_bend, cross_section=xs_w
            )

            # Route it straight and input
            if i == 0:
                out = triangle_left_ref["o178"]
            else:
                out = triangle_comp_ref[f"o{143 - i * 2}"]

            gf.routing.route_single(
                die, strt_top["o2"], out, bend=aux_bend, cross_section=xs_w,
            )

            # Route it to the mesh
            tap_ref_out = die << taper
            if jdx == 0:
                tap_ref_out.connect("o1", meshes[jdx][f"o{i+1}"])
            else:
                tap_ref_out.connect("o1", meshes[jdx][f"o{i+73}"])
            inputs.append(tap_ref_out["o2"])
            outputs.append(tap_ref2["o2"])

        # Route MUA to mesh
        gf.routing.route_bundle(
            die,
            inputs,
            outputs,
            bend=aux_bend, cross_section=xs_w,
            separation=3,
            start_straight_length=1,
        )
        # ((Distance wvg wvg + wvg large width) * 2  - random diff) * n_bends / (n_bends - 1)
        comp = ((3 + 0.93) * 2 - 0.037) * 5 / 4

        # Amount extra do be added at specific location
        extra = 0
        for i in range(72):
            if i == 0:
                # Needed only for the first input
                # 1 edge coupler missing + random_dff
                extra = (127 - 2 + 0.41 - 0.033) * 5 / 4
            elif i == 1:
                # No need extra from the second on
                extra = 0
            elif i == 36:
                # Needed only for the first input after gap
                # 2 central edge coupler missing
                extra = -127 * 2 * 5 / 4
            elif i == 37:
                # Need for all the ec after the gap
                extra -= (127 - 2 + 0.41 - 0.033) * 5 / 4
            elif i == 71:
                # Needed for last input
                # 1 sepration + width
                extra += (90 - 2 + 0.41) * 5 / 4

            # Place the compensation
            rib_comp = die << ipr.spiral_compensation(
                gf.c.straight(115 + comp * i + extra, cross_section=xs_w),
                5,
                0,
                0,
                taper,
                gf.partial(spaced_bend),
            )

            # Connect it
            rib_comp.mirror_x()
            rib_comp.connect("o1", strt_bot_array[71-i]["o2"])

            gf.routing.route_single(
                die,
                strt_top_array[71-i]["o1"],
                rib_comp["o2"],
                bend=aux_bend,
                cross_section=xs_w
            )


    # #############################
    # # TM INPUT COMPENSTAION     #
    # #############################
    # out = []
    # inp = []
    # for i in range(72):
    #     tap_ref = die << taper
    #     tap_ref.connect("o1", mua_in[1][i]["o2"])
    #     st_ref = die << gf.c.straight(60, cross_section=xs_w)
    #     st_ref.connect("o1", tap_ref["o2"])

    #     if i < 36:
    #         extra = 0
    #     else:
    #         extra = 317.5
    #     rib_comp = die << ipr.spiral_compensation(
    #         gf.c.straight(56.25 * i + extra + 5, cross_section=xs_w),
    #         5,
    #         0,
    #         0,
    #         taper,
    #         gf.partial(spaced_bend),
    #     )
    #     rib_comp.connect("o1", st_ref["o2"])
    #     inp.append(rib_comp["o2"])

    #     tap_ref = die << taper
    #     tap_ref.connect("o1", bot_sin_outputs[-1 - i])
    #     out.append(tap_ref["o2"])

    # out.reverse()
    # for k, comp in enumerate(inp[::-1]):
    #     gf.routing.route_bundle(
    #         die,
    #         [out[k]],
    #         [comp],
    #         bend=aux_bend,
    #         cross_section="strip",
    #         route_width=0.93,
    #         start_straight_length=1 + 4 * k,
    #     )

    # #############################
    # # TM OUTPUT COMPENSTAION    #
    # #############################
    # bend_ref = die << bend_r5
    # bend_ref.connect("o1", ec_out[1][79], mirror=True)
    # bend_ref2 = die << bend_r5
    # bend_ref2.connect("o1", bend_ref["o2"])
    # tap_ref = die << taper
    # tap_ref.connect("o1", bend_ref2["o2"])
    # st_ref = die << gf.c.straight(100.921, cross_section=xs_w)
    # st_ref.connect("o1", tap_ref["o2"])
    # tap_ref = die << taper
    # tap_ref.connect("o2", st_ref["o2"])
    # bend_ref = die << bend_r5
    # bend_ref.connect("o2", tap_ref["o1"])
    # tap_ref = die << taper
    # tap_ref.connect("o1", bend_ref["o1"])
    # st_ref = die << gf.c.straight(91.745, cross_section=xs_w)
    # st_ref.connect("o1", tap_ref["o2"])

    # triangle_comp_ref = die << ipr.crossing_3D_matrix(
    #     **matrix_comp_kwargs,
    #     n_start_columns=1,
    #     n_crossings=71,
    # )
    # triangle_comp_ref.rotate(180)
    # triangle_comp_ref.move(
    #     (triangle_comp_ref.xmin, triangle_comp_ref["o213"].y),
    #     (st_ref["o2"].x + 1, st_ref["o1"].y),
    # )

    # for i in range(71):
    #     sin_ext = die << gf.c.rectangle(
    #         (5, 2), (259, 0), port_type="optical", port_orientations=[0]
    #     )
    #     sin_ext.connect("o1", triangle_comp_ref[f"o{284 - i}"])
    #     sin_ext = die << gf.c.rectangle(
    #         (5, 2), (259, 0), port_type="optical", port_orientations=[0]
    #     )
    #     sin_ext.connect("o1", triangle_comp_ref[f"o{2 + i * 2}"])

    # gf.routing.route_single(
    #     die,
    #     triangle_comp_ref["o213"],
    #     st_ref["o2"],
    #     cross_section=xs_w,
    #     auto_taper=False,
    # )
    # for i in range(1, 71):
    #     gf.routing.route_single(
    #         die,
    #         triangle_comp_ref[f"o{213 - i}"],
    #         triangle_right_ref[f"o{107 + i}"],
    #         cross_section=xs_w,
    #         auto_taper=False,
    #     )

    # for i in range(72):
    #     start_st_ref = die << gf.c.straight(1, cross_section=xs_w)
    #     if i == 0:
    #         start_st_ref.connect("o1", triangle_right_ref["o178"])
    #     else:
    #         start_st_ref.connect("o1", triangle_comp_ref[f"o{143 - i * 2}"])
    #     leng = 5 if i != 0 else 42
    #     st_ref = die << gf.c.straight(leng, cross_section=xs_w)
    #     st_ref.connect("o1", start_st_ref["o2"])
    #     tap_ref = die << taper
    #     tap_ref.connect("o2", st_ref["o2"])
    #     bend_ref = die << bend_r5
    #     bend_ref.connect("o1", tap_ref["o1"])
    #     tap_ref = die << taper
    #     tap_ref.connect("o1", bend_ref["o2"])
    #     st_ref = die << gf.c.straight(
    #         (triangle_comp_ref["o142"].y + 20) - tap_ref["o1"].y, cross_section=xs_w
    #     )
    #     st_ref.connect("o1", tap_ref["o2"])

    #     if i < 36:
    #         extra = 0
    #     else:
    #         extra = 317.5
    #     rib_comp = die << ipr.spiral_compensation(
    #         gf.c.straight(36.425 * i + extra + 5 + 13.625, cross_section=xs_w),
    #         7,
    #         0,
    #         0,
    #         taper,
    #         gf.partial(spaced_bend),
    #     )
    #     rib_comp.connect("o1", st_ref["o2"], mirror=True)

    #     # Placing a taper to the MUA output to have in the correct cross-section
    #     tap_ref = die << taper
    #     tap_ref.connect("o1", mua_out[1][i]["o4"])

    #     gf.routing.route_single(
    #         die,
    #         rib_comp["o2"],
    #         tap_ref["o2"],
    #         cross_section=xs_w,
    #         auto_taper=False,
    #         bend=bend_r5,
    #     )

    # #############################
    # # TE OUTPUT COMPENSTAION    #
    # #############################
    # out = []
    # inp = []
    # aux = []
    # for i in range(72):
    #     tap_ref = die << taper
    #     tap_ref.connect("o1", mua_out[0][i+2]["o4"])

    #     st_ref = die << gf.c.straight(60, cross_section=xs_w)
    #     st_ref.connect("o1", tap_ref["o2"])

    #     aux.append(st_ref["o2"])

    #     tap_ref = die << taper
    #     tap_ref.connect("o1", bot_sin_outputs[i])
    #     out.append(tap_ref["o2"])

    # for i in range(72):
    #     if i < 36:
    #         extra = 0
    #     else:
    #         extra = 317.5
    #     rib_comp = die << ipr.spiral_compensation(
    #         gf.c.straight(56.068 * i + extra + 422.196, cross_section=xs_w),
    #         7,
    #         0,
    #         0,
    #         taper,
    #         gf.partial(spaced_bend),
    #     )
    #     rib_comp.connect("o1", aux[-1 - i])
    #     inp.append(rib_comp["o2"])

    # out.reverse()
    # for k, comp in enumerate(inp):
    #     gf.routing.route_bundle(
    #         die,
    #         [out[k]],
    #         [comp],
    #         bend=aux_bend,
    #         cross_section="strip",
    #         route_width=0.93,
    #         start_straight_length=280.03 - 3.93 * k,
    #     )

    # #############################
    # # Core demultiplexer        #
    # #############################
    # muas = []
    # demux_in = []
    # for i in range(72):
    #     muas.append(mua_in[0][71 - i]["o4"])
    #     demux_in.append(meshes[0][f"o{1 + i}"])

    # gf.routing.route_bundle(
    #     die,
    #     demux_in,
    #     muas,
    #     bend=bend_r5,
    #     taper=taper,
    #     min_straight_taper=1,
    #     cross_section="strip",
    #     separation=3.52,
    #     sort_ports=True,
    #     steps=[{"dx": -170, "dy": 50}, {"dy": 1}],
    #     end_straight_length=55,
    # )

    # muas = []
    # demux_in = []
    # for i in range(72):
    #     muas.append(mua_in[1][71 - i]["o4"])
    #     demux_in.append(meshes[1][f"o{1 + i}"])

    # gf.routing.route_bundle(
    #     die,
    #     demux_in,
    #     muas,
    #     bend=bend_r5,
    #     taper=taper,
    #     min_straight_taper=1,
    #     cross_section="strip",
    #     separation=3.59,
    #     sort_ports=True,
    #     steps=[{"dx": -170, "dy": 50}, {"dy": 1}],
    #     end_straight_length=55,
    # )

    # #############################
    # # Core multiplexer          #
    # #############################
    # muas = []
    # mux_in = []
    # for i in range(72):
    #     tran_ref = die << taper
    #     tran_ref.connect("o1", mua_out[0][i+2]["o2"])
    #     muas.append(tran_ref["o2"])
    #     tran_ref = die << taper
    #     tran_ref.connect("o1", meshes[0][f"o{73 + i}"])
    #     mux_in.append(tran_ref["o2"])

    # gf.routing.route_bundle(
    #     die,
    #     mux_in,
    #     muas,
    #     bend=aux_bend,
    #     cross_section="strip",
    #     route_width=0.93,
    #     separation=3,
    #     sort_ports=True,
    #     steps=[
    #         {"dx": 225.815, "dy": -50},
    #         {"dy": -1},  # Unnecessary but the function complains if not placed
    #     ],
    #     end_straight_length=29.484,
    # )

    # muas = []
    # mux_in = []
    # for i in range(72):
    #     tran_ref = die << taper
    #     tran_ref.connect("o1", mua_out[1][i]["o2"])
    #     muas.append(tran_ref["o2"])
    #     tran_ref = die << taper
    #     tran_ref.connect("o1", meshes[1][f"o{73 + i}"])
    #     mux_in.append(tran_ref["o2"])

    # gf.routing.route_bundle(
    #     die,
    #     mux_in,
    #     muas,
    #     bend=aux_bend,
    #     route_width=0.93,
    #     cross_section="strip",
    #     separation=3,
    #     sort_ports=True,
    #     steps=[
    #         {"dx": 225.815, "dy": -50},
    #         {"dy": -1},  # Unnecessary but the function complains if not placed
    #     ],
    #     end_straight_length=29.484,
    # )

    # #############################
    # # Neff & Ng                 #
    # #############################
    # # Silicon 0.41
    # out = []
    # inp = []
    # mzi1 = die << mzi_cell(splitter=splitter, order_mzi_length=9.5054)
    # mzi1.rotate(180)
    # mzi1.move((mzi1.x, mzi1.ymin), (-5556 + 63.5, 11850))
    # inp.extend((mzi1["o1"], mzi1["o2"]))

    # mzi2 = die << mzi_cell(splitter=splitter, order_mzi_length=95.0535)
    # mzi2.rotate(180)
    # mzi2.move((mzi2.x, mzi2.ymin), (-5302 + 63.5, 11850))
    # inp.extend((mzi2["o1"], mzi2["o2"]))

    # for i in range(4):
    #     mzi = mzi1 if i < 2 else mzi2
    #     abs_ref = die << absorber
    #     abs_ref.connect("o1", mzi[f"o{3 + i % 2 }"], mirror=i % 2 == 0)
    #     vt_ref1 = die << loop_sin_si_transition
    #     vt_ref1.connect("o2", ec_in[0][i+4]["o1"])
    #     out.append(vt_ref1["o1"])

    # for i, start in enumerate(out):
    #     gf.routing.route_single(
    #         die,
    #         start,
    #         inp[i],
    #         bend=bend_r5,
    #         cross_section=xs,
    #         auto_taper=False,
    #     )

    # # Silicon 1.0
    # out = []
    # inp = []
    # mzi1 = die << mzi_cell(
    #     splitter=splitter,
    #     order_mzi_length=22.222,
    #     cross_section2=xs_w,
    #     extra_component=taper,
    # )
    # mzi1.rotate(180)
    # mzi1.move((mzi1.x, mzi1.ymin), (5111 + 63.5, 11850))
    # inp.extend((mzi1["o1"], mzi1["o2"]))

    # mzi2 = die << mzi_cell(
    #     splitter=splitter,
    #     order_mzi_length=80,
    #     cross_section2=xs_w,
    #     extra_component=taper,
    # )
    # mzi2.rotate(180)
    # mzi2.move((mzi2.x, mzi2.ymin), (5365 + 63.5, 11850))
    # inp.extend((mzi2["o1"], mzi2["o2"]))

    # for i in range(4):
    #     mzi = mzi1 if i < 2 else mzi2
    #     abs_ref = die << absorber
    #     abs_ref.connect("o1", mzi[f"o{3 + i % 2 }"], mirror=i % 2 == 0)
    #     vt_ref1 = die << loop_sin_si_transition
    #     vt_ref1.connect("o2", ec_in[0][84+i]["o1"])
    #     out.append(vt_ref1["o1"])

    # for i, start in enumerate(out):
    #     gf.routing.route_single(
    #         die,
    #         start,
    #         inp[i],
    #         bend=bend_r5,
    #         cross_section=xs,
    #         auto_taper=False,
    #     )

    # # Silicon Nitride 1.0
    # out = []
    # inp = []
    # mzi1 = die << mzi_cell(
    #     splitter=ipr.mmi(name="mmi_inv_d3", version="30nm"),
    #     order_mzi_length=30.846,
    #     cross_section2=xs_n1,
    #     extra_component=nwg_si_transition,
    # )
    # mzi1.move((mzi1.x, mzi1.ymax), (-5492 + 63.5, -11850))
    # inp.extend((mzi1["o2"], mzi1["o1"]))

    # mzi2 = die << mzi_cell(
    #     splitter=ipr.mmi(name="mmi_inv_d3", version="30nm"),
    #     order_mzi_length=61.693,
    #     cross_section2=xs_n1,
    #     extra_component=nwg_si_transition,
    # )
    # mzi2.move((mzi2.x, mzi2.ymax), (-5238 + 63.5, -11850))
    # inp.extend((mzi2["o2"], mzi2["o1"]))

    # for i in range(4):
    #     mzi = mzi1 if i < 2 else mzi2
    #     abs_ref = die << absorber
    #     abs_ref.connect("o1", mzi[f"o{3 + i % 2 }"], mirror=i % 2 == 0)
    #     vt_ref1 = die << loop_sin_si_transition
    #     vt_ref1.connect("o2", ec_in[0][i]["o1"])
    #     out.append(vt_ref1["o1"])

    # for i, start in enumerate(out):
    #     gf.routing.route_single(
    #         die,
    #         start,
    #         inp[i],
    #         bend=bend_r5,
    #         cross_section=xs,
    #         auto_taper=False,
    #     )

    # # Advanced Silicon Nitride 1.0
    # out = []
    # inp = []
    # mzi1 = die << mzi_cell(
    #     splitter=ipr.mmi(name="mmi_inv_d3", version="30nm"),
    #     order_mzi_length=33.123,
    #     cross_section2=xs_n,
    #     extra_component=anwg_si_transition,
    # )
    # mzi1.move((mzi1.x, mzi1.ymax), (5175 + 63.5, -11800))
    # inp.extend((mzi1["o2"], mzi1["o1"]))

    # mzi2 = die << mzi_cell(
    #     splitter=ipr.mmi(name="mmi_inv_d3", version="30nm"),
    #     order_mzi_length=115.932,
    #     cross_section2=xs_n,
    #     extra_component=anwg_si_transition,
    # )
    # mzi2.move((mzi2.x, mzi2.ymax), (5429 + 63.5, -11800))
    # inp.extend((mzi2["o2"], mzi2["o1"]))

    # for i in range(4):
    #     mzi = mzi1 if i < 2 else mzi2
    #     abs_ref = die << absorber
    #     abs_ref.connect("o1", mzi[f"o{3 + i % 2 }"], mirror=i % 2 == 0)
    #     vt_ref1 = die << loop_sin_si_transition
    #     vt_ref1.connect("o2", ec_in[0][i+80]["o1"])
    #     out.append(vt_ref1["o1"])

    # for i, start in enumerate(out):
    #     gf.routing.route_single(
    #         die,
    #         start,
    #         inp[i],
    #         bend=bend_r5,
    #         cross_section=xs,
    #         auto_taper=False,
    #     )

    # #############################
    # # Loops                     #
    # #############################
    # # Left side
    # out = []
    # inp = []
    # search_area = (-11391.97, 10065.26, -11187.37, 10384.81)
    # up_mua_matrix = v7b.build_matrix(die, "pucmua*", area=search_area)
    # search_area = (-6450, -10370, -6270, -10070)
    # lw_mua_matrix = v7b.build_matrix(die, "pucmua*", area=search_area)

    # for i in range(2):
    #     vt_ref1 = die << loop_sin_si_transition
    #     vt_ref1.connect("o2", ec_in[0][i * 2]["o1"])
    #     vt_ref2 = die << loop_sin_si_transition
    #     vt_ref2.connect("o2", ec_in[0][1 + i * 2]["o1"])

    #     gf.routing.route_single(
    #         die,
    #         vt_ref1["o1"],
    #         vt_ref2["o1"],
    #         cross_section=xs,
    #         bend=bend_r5,
    #         auto_taper=False,
    #     )

    # for i in range(2):
    #     vt_ref1 = die << loop_sin_si_transition
    #     vt_ref1.connect("o2", ec_out[0][i * 2]["o1"])
    #     vt_ref2 = die << loop_sin_si_transition
    #     vt_ref2.connect("o2", ec_out[0][1 + i * 2]["o1"])

    #     gf.routing.route_single(
    #         die,
    #         vt_ref1["o1"],
    #         vt_ref2["o1"],
    #         cross_section=xs,
    #         bend=bend_r5,
    #         auto_taper=False,
    #     )

    # vt_ref = die << loop_sin_si_transition
    # vt_ref.connect("o2", ec_in[0][10]["o1"])
    # st_ref = die << gf.c.straight(1, cross_section=xs)
    # st_ref.connect("o1", vt_ref["o1"])
    # psr_ref = die << psr
    # psr_ref.connect("o2", st_ref["o2"], mirror=True)
    # ac_ref1 = die << ac
    # ac_ref1.connect("o1", psr_ref["o3"], mirror=True)
    # ac_ref2 = die << ac
    # ac_ref2.connect("o1", psr_ref["o4"])
    # abs_ref = die << absorber
    # abs_ref.connect("o1", psr_ref["o1"])
    # out.extend((ac_ref1["o2"], ac_ref2["o2"]))

    # for i in range(2):
    #     st_ref = die << gf.c.straight(0, cross_section=xs)
    #     st_ref.connect("o1", up_mua_matrix[0][i]["o2"])
    #     inp.append(st_ref["o2"])

    # gf.routing.route_bundle(
    #     die,
    #     out,
    #     inp,
    #     taper=taper,
    #     bend=bend_r5,
    #     min_straight_taper=1,
    #     cross_section="strip",
    #     separation=3.52,
    #     start_straight_length=107,
    # )
    # out.clear()

    # # Create auxiliary waveguides on the right side to help routing
    # aux = []
    # aux2 = []
    # for i in range(5):
    #     st_ref = die << gf.c.straight(10, cross_section=xs_w)
    #     st_ref.rotate(-90)
    #     st_ref.move((st_ref.x, st_ref.y), (-11529.406 + 3.93 * i, 9780))

    #     # Top part
    #     aux.append(st_ref["o1"])

    #     # Bot part
    #     aux2.append(st_ref["o2"])

    # # Output of the top EC to be routed
    # for i in range(1):
    #     vt_ref = die << loop_sin_si_transition
    #     vt_ref.connect("o2", ec_in[0][8 + i]["o1"])
    #     tap_ref = die << taper
    #     tap_ref.connect("o1", vt_ref["o1"])
    #     out.append(tap_ref["o2"])

    # vt_ref = die << loop_sin_si_transition
    # vt_ref.connect("o2", ec_in[0][9]["o1"])
    # st_ref = die << gf.c.straight(1, cross_section=xs)
    # st_ref.connect("o1", vt_ref["o1"])
    # psr_ref = die << psr
    # psr_ref.connect("o2", st_ref["o2"], mirror=True)
    # abs_ref = die << absorber
    # abs_ref.connect("o1", psr_ref["o1"])
    # ac_ref1 = die << ac
    # ac_ref1.connect("o1", psr_ref["o3"], mirror=True)
    # tap_ref = die << taper
    # tap_ref.connect("o1", ac_ref1["o2"])
    # out.append(tap_ref["o2"])
    # ac_ref2 = die << ac
    # ac_ref2.connect("o1", psr_ref["o4"])
    # tap_ref = die << taper
    # tap_ref.connect("o1", ac_ref2["o2"])
    # out.append(tap_ref["o2"])

    # # Output of the top MUA to be routed
    # for i in range(2):
    #     tap_ref = die << taper
    #     tap_ref.connect("o1", up_mua_matrix[0][i]["o4"])
    #     out.append(tap_ref["o2"])

    # gf.routing.route_bundle(
    #     die,
    #     out[:3],
    #     aux[:3],
    #     bend=aux_bend,
    #     cross_section=xs_w,
    #     separation=3,
    #     sort_ports=True,
    #     start_straight_length=75.61,
    # )
    # gf.routing.route_bundle(
    #     die,
    #     out[3:],
    #     aux[3:],
    #     bend=aux_bend,
    #     cross_section=xs_w,
    #     separation=3,
    #     sort_ports=True,
    #     start_straight_length=31.47,
    # )

    # # Route from TOP to BOTTOM MUA
    # out = []
    # for idx in range(2):
    #     tap_ref = die << taper
    #     tap_ref.connect("o1", lw_mua_matrix[0][idx]["o2"])
    #     out.append(tap_ref["o2"])

    # gf.routing.route_bundle(
    #     die,
    #     out,
    #     aux2[3:],
    #     bend=aux_bend,
    #     separation=3,
    #     cross_section=xs_w,
    #     start_straight_length=30,
    # )

    # # Update the aux2 for the routed MUA
    # for idx in range(2):
    #     tap_ref = die << taper
    #     tap_ref.connect("o1", lw_mua_matrix[0][idx]["o4"])
    #     aux2[3+idx] = tap_ref["o2"]

    # # Route BOTTOM MUA to EC
    # out = []
    # for i in range(1):
    #     vt_ref = die << loop_sin_si_transition
    #     vt_ref.connect("o2", ec_out[0][8 + i]["o1"])
    #     tap_ref = die << taper
    #     tap_ref.connect("o1", vt_ref["o1"])
    #     out.append(tap_ref["o2"])

    # for i in range(2):
    #     vt_ref = die << loop_sin_si_transition
    #     vt_ref.connect("o2", ec_out[0][9 + i]["o1"])
    #     st_ref = die << gf.c.straight(1, cross_section=xs)
    #     st_ref.connect("o1", vt_ref["o1"])
    #     psr_ref = die << psr
    #     psr_ref.connect("o2", st_ref["o2"], mirror=True)
    #     abs_ref = die << absorber
    #     abs_ref.connect("o1", psr_ref["o1"])
    #     ac_ref1 = die << ac
    #     ac_ref1.connect("o1", psr_ref["o3"], mirror=True)
    #     tap_ref = die << taper
    #     tap_ref.connect("o1", ac_ref1["o2"])
    #     out.append(tap_ref["o2"])
    #     ac_ref2 = die << ac
    #     ac_ref2.connect("o1", psr_ref["o4"])
    #     tap_ref = die << taper
    #     tap_ref.connect("o1", ac_ref2["o2"])
    #     out.append(tap_ref["o2"])

    # gf.routing.route_bundle(
    #     die,
    #     out,
    #     aux2,
    #     bend=aux_bend,
    #     cross_section=xs_w,
    #     separation=3,
    #     sort_ports=True,
    #     start_straight_length=100,
    # )

    # # Right side
    # out = []
    # inp = []
    # search_area = (6419.39, 9989.37, 6702.20, 10388.40)
    # up_mua_matrix = v7b.build_matrix(die, "pucmua*", area=search_area)
    # search_area = (11200, -10370, 11400, -10070)
    # lw_mua_matrix = v7b.build_matrix(die, "pucmua*", area=search_area)

    # for i in range(2):
    #     vt_ref1 = die << loop_sin_si_transition
    #     vt_ref1.connect("o2", ec_in[0][92 + i * 2]["o1"])
    #     vt_ref2 = die << loop_sin_si_transition
    #     vt_ref2.connect("o2", ec_in[0][93 + i * 2]["o1"])

    #     gf.routing.route_single(
    #         die,
    #         vt_ref1["o1"],
    #         vt_ref2["o1"],
    #         cross_section=xs,
    #         bend=bend_r5,
    #         auto_taper=False,
    #     )

    # for i in range(2):
    #     vt_ref1 = die << loop_sin_si_transition
    #     vt_ref1.connect("o2", ec_out[0][92 + i * 2]["o1"])
    #     vt_ref2 = die << loop_sin_si_transition
    #     vt_ref2.connect("o2", ec_out[0][93 + i * 2]["o1"])

    #     gf.routing.route_single(
    #         die,
    #         vt_ref1["o1"],
    #         vt_ref2["o1"],
    #         cross_section=xs,
    #         bend=bend_r5,
    #         auto_taper=False,
    #     )

    # vt_ref = die << loop_sin_si_transition
    # vt_ref.connect("o2", ec_in[85][0]["o1"])
    # st_ref = die << gf.c.straight(1, cross_section=xs)
    # st_ref.connect("o1", vt_ref["o1"])
    # psr_ref = die << psr
    # psr_ref.connect("o2", st_ref["o2"], mirror=True)
    # ac_ref1 = die << ac
    # ac_ref1.connect("o1", psr_ref["o3"], mirror=True)
    # ac_ref2 = die << ac
    # ac_ref2.connect("o1", psr_ref["o4"])
    # abs_ref = die << absorber
    # abs_ref.connect("o1", psr_ref["o1"])
    # out.extend((ac_ref1["o2"], ac_ref2["o2"]))

    # for i in range(2):
    #     st_ref = die << gf.c.straight(0, cross_section=xs)
    #     st_ref.connect("o1", up_mua_matrix[0][i]["o2"])
    #     inp.append(st_ref["o2"])

    # gf.routing.route_bundle(
    #     die,
    #     out,
    #     inp,
    #     taper=taper,
    #     bend=bend_r5,
    #     min_straight_taper=1,
    #     cross_section="strip",
    #     separation=3.52,
    #     start_straight_length=164.85,
    # )
    # out.clear()

    # # Create auxiliary waveguides on the right side to help routing
    # aux = []
    # aux2 = []
    # for i in range(5):
    #     st_ref = die << gf.c.straight(10, cross_section=xs_w)
    #     st_ref.rotate(-90)
    #     st_ref.move((st_ref.x, st_ref.y), (11615.69 + 3.93 * i, 9780))

    #     # Top part
    #     aux.append(st_ref["o1"])

    #     # Bot part
    #     aux2.append(st_ref["o2"])

    # # Output of the top MUA to be routed
    # for i in range(2):
    #     tap_ref = die << taper
    #     tap_ref.connect("o1", up_mua_matrix[0][i]["o4"])
    #     out.append(tap_ref["o2"])

    # # Output of the top EC to be routed
    # vt_ref = die << loop_sin_si_transition
    # vt_ref.connect("o2", ec_in[85][1]["o1"])
    # st_ref = die << gf.c.straight(1, cross_section=xs)
    # st_ref.connect("o1", vt_ref["o1"])
    # psr_ref = die << psr
    # psr_ref.connect("o2", st_ref["o2"], mirror=True)
    # abs_ref = die << absorber
    # abs_ref.connect("o1", psr_ref["o1"])
    # ac_ref1 = die << ac
    # ac_ref1.connect("o1", psr_ref["o3"], mirror=True)
    # tap_ref = die << taper
    # tap_ref.connect("o1", ac_ref1["o2"])
    # out.append(tap_ref["o2"])
    # ac_ref2 = die << ac
    # ac_ref2.connect("o1", psr_ref["o4"])
    # tap_ref = die << taper
    # tap_ref.connect("o1", ac_ref2["o2"])
    # out.append(tap_ref["o2"])

    # for i in range(1):
    #     vt_ref = die << loop_sin_si_transition
    #     vt_ref.connect("o2", ec_in[0][87 + i]["o1"])
    #     tap_ref = die << taper
    #     tap_ref.connect("o1", vt_ref["o1"])
    #     out.append(tap_ref["o2"])

    # gf.routing.route_bundle(
    #     die,
    #     out[:2],
    #     aux[:2],
    #     bend=aux_bend,
    #     cross_section=xs_w,
    #     separation=3,
    #     sort_ports=True,
    #     start_straight_length=40,
    # )
    # gf.routing.route_bundle(
    #     die,
    #     out[2:],
    #     aux[2:],
    #     bend=aux_bend,
    #     cross_section=xs_w,
    #     separation=3,
    #     sort_ports=True,
    #     start_straight_length=133.46,
    # )

    # # Route from TOP to BOTTOM MUA
    # out = []
    # for idx in range(2):
    #     tap_ref = die << taper
    #     tap_ref.connect("o1", lw_mua_matrix[0][idx]["o2"])
    #     out.append(tap_ref["o2"])

    # gf.routing.route_bundle(
    #     die,
    #     out,
    #     aux2[:2],
    #     bend=aux_bend,
    #     separation=3,
    #     cross_section=xs_w,
    #     start_straight_length=21.624,
    # )

    # # Update the aux2 for the routed MUA
    # for idx in range(2):
    #     tap_ref = die << taper
    #     tap_ref.connect("o1", lw_mua_matrix[0][idx]["o4"])
    #     aux2[idx] = tap_ref["o2"]

    # # Route BOTTOM MUA to EC
    # out = []
    # for i in range(1):
    #     vt_ref = die << loop_sin_si_transition
    #     vt_ref.connect("o2", ec_out[0][87 - i]["o1"])
    #     tap_ref = die << taper
    #     tap_ref.connect("o1", vt_ref["o1"])
    #     out.append(tap_ref["o2"])

    # for i in range(2):
    #     vt_ref = die << loop_sin_si_transition
    #     vt_ref.connect("o2", ec_out[0][86 - i]["o1"])
    #     st_ref = die << gf.c.straight(1, cross_section=xs)
    #     st_ref.connect("o1", vt_ref["o1"])
    #     psr_ref = die << psr
    #     psr_ref.connect("o2", st_ref["o2"], mirror=True)
    #     ac_ref1 = die << ac
    #     ac_ref1.connect("o1", psr_ref["o3"], mirror=True)
    #     ac_ref2 = die << ac
    #     ac_ref2.connect("o1", psr_ref["o4"])
    #     abs_ref = die << absorber
    #     abs_ref.connect("o1", psr_ref["o1"])
    #     tap_ref = die << taper
    #     tap_ref.connect("o1", ac_ref2["o2"])
    #     out.append(tap_ref["o2"])
    #     tap_ref = die << taper
    #     tap_ref.connect("o1", ac_ref1["o2"])
    #     out.append(tap_ref["o2"])

    # gf.routing.route_bundle(
    #     die,
    #     out,
    #     aux2,
    #     bend=aux_bend,
    #     cross_section=xs_w,
    #     separation=3,
    #     sort_ports=True,
    #     start_straight_length=75,
    # )
