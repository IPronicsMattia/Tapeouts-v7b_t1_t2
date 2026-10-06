import gdsfactory as gf
import iprlayout_tower as ipr

import v7b
from v7b.mesh import inner_mesh_core, mesh_72x72
from v7b.pdk import (
    ipronics_logo,
    phase_shifter_cassette,
    spaced_bend,
    v7b_cells,
    v7b_logo,
    v7b_puc,
)

DRC_FRIENDLY = False
# ipr.crossing()
# ## IMPORTANT: IF DRC_FRIENDLY IS TRUE THE FOLLOWING LINES MUST BE ADDED
# ## TO CROSSINGS.PY def add_ports IN IPRLAYOUT BEFORE RETURNING THE COMPONENT
# for port in c.ports:
#     orientation = round(port.orientation)
#     if orientation == 0:
#         port.center = (port.center[0] - 0.001, port.center[1])
#     elif orientation == 90:
#         port.center = (port.center[0], port.center[1] - 0.001)
#     elif orientation == 180:
#         port.center = (port.center[0] + 0.001, port.center[1])
#     elif orientation == 270:
#         port.center = (port.center[0], port.center[1] + 0.001)


def component_placement(
    die: gf.Component,
    meshes: list,
    mua_in: list,
    mua_out: list,
    ec_in: list,
    ec_out: list,
    numbered: bool,
) -> None:
    """This function places the components in the DIE"""

    die = gf.get_component(die)
    generic_pdk = gf.get_active_pdk()
    generic_cells = generic_pdk.cells

    pdk = ipr.get_pdk()
    pdk.activate()
    cells = pdk.cells
    cells.update(v7b_cells)
    cells.update(generic_cells)
    pdk.cells = cells

    #############################
    # Cross sections            #
    #############################
    xs = gf.get_cross_section("strip", width=0.41, radius_min=3.0)
    xs_w = gf.get_cross_section("strip", width=0.93)
    xs_c = gf.get_cross_section("strip", width=1.56)
    xs_n = gf.get_cross_section("nitride2", width=2)

    #############################
    # Components                #
    #############################
    ec_component = ipr.anwg_ec_oband()
    sin_si_transition = ipr.si_anwg_transition(
        name_si_nwg_transition="VT1_PI_D0_100",
        name_nwg_anwg_transition="VT2_POLINS_D_02",
        width_out=0.7,
    )
    psr = ipr.si_psr_tw()
    absorber = ipr.rib_absorber(cross_section=xs)
    thermistor = ipr.serie_thermistor(
        wg_layer=(171, 0), active_layer=(6, 0), width=3.1, active_layer_square=True
    )
    if numbered:
        photodetector = gf.partial(
            ipr.lateral_pd,
            ge_length=14,
            ge_width=3,
            dop_plusplus_ge_separation=0.3,
            metal2_via_n=3,
            forward_pin=True,
            cross_section=xs,
        )
    else:
        photodetector = gf.get_component(
            ipr.lateral_pd(
                ge_length=14,
                ge_width=3,
                dop_plusplus_ge_separation=0.3,
                metal2_via_n=3,
                forward_pin=True,
                cross_section=xs,
            )
        )

    bend_r5 = spaced_bend()

    taper_410_930 = ipr.rib_taper(width1=0.41, width2=0.93, cross_section=xs)
    taper_410_1560 = ipr.rib_taper(width1=0.41, width2=1.56, cross_section=xs)

    crossing = gf.partial(ipr.crossing, name="polaris", version="60nm")

    splitter = ipr.mmi(name="mmi_inv_d3", version="30nm")
    ac = ipr.bend_bezier_s_custom_width(layer_RIB=xs.layer)
    taper = ipr.rib_taper(
        length=2.5, width1=0.41, width2=0.46, cross_section=xs, npoints=100
    )
    taper1 = ipr.rib_taper(
        length=10, width1=0.41, width2=0.41, cross_section=xs, npoints=100
    )
    taper2 = ipr.rib_taper(
        length=10, width1=0.41, width2=0.46, cross_section=xs, npoints=100
    )

    bend_puc = ipr.bend_euler_custom_width(
        cross_section=xs,
        width_in=0.41,
        width_out=0.41,
        width_center=0.438,
        radius=3,
        p=0.342,
        m=1.1875,
    )

    phase_shifter = phase_shifter_cassette(
        loops=5,
        bend=bend_puc,
        taper=taper,
        taper1=taper1,
        taper2=taper2,
        width_center=0.41,
        width_var=0.05,
        width_all=0.41,
        spacing=0.75,
        inverted_ports=True,
        wv_length=90,
        right_out_leng=1.91,
        htr_width=4,
    )

    puc = gf.partial(
        v7b_puc,
        phase_shifter=phase_shifter,
        splitter=splitter,
        cross_section=xs,
        arm_separation=25,
        ac=ac,
        bend=bend_puc,
        puc_number=0,
    )

    core = gf.partial(
        inner_mesh_core,
        puc=puc,
        crossing=crossing,
        crossing_taper=taper_410_1560,
        routing_taper=taper_410_930,
        bend=bend_r5,
        order=36,
        extra_stages=2,
        puc_y_sep=-90,
        cross_section=xs,
        wide_cross_section=xs_w,
        crossing_cross_section=xs_c,
        nitride_cross_section=xs_n,
        column_number_step=216,
        block9x9_number_step=144,
        drc_friendly=DRC_FRIENDLY,
    )

    mesh = mesh_72x72(core, puc, bend_r5, taper_410_930, xs, xs_w, xs_n, numbered)

    #############################
    # Edge Couplers             #
    #############################
    ec_ref = die << gf.c.edge_coupler_array(
        pitch=-127, n=88, edge_coupler=ec_component, text=None
    )
    ec_ref.rotate(-90)
    ec_ref.mirror_x()
    ec_ref.movex(ec_ref.x, -31.75)
    ec_ref.movey(ec_ref.ymax, die.ymax - 75)

    ec_ref2 = die << gf.c.edge_coupler_array(
        pitch=-127, n=88, edge_coupler=ec_component, text=None
    )
    ec_ref2.rotate(90)
    ec_ref2.movex(ec_ref2.x, 31.75)
    ec_ref2.movey(ec_ref2.ymin, die.ymin + 75)

    #############################
    # Extra ECs                 #
    #############################
    # NOTE that ECs should be included in upper sections but are included here due to
    # review requests since adding them up in the code will be too time consuming now
    # due to dependencies in the posterior routing

    ec_ref_aux = die << gf.c.edge_coupler_array(
        pitch=-127, n=4, edge_coupler=ec_component, text=None
    )
    ec_ref_aux.rotate(-90)
    ec_ref_aux.mirror_x()
    ec_ref_aux.movex(ec_ref_aux.xmax, ec_ref.xmin - 63)
    ec_ref_aux.movey(ec_ref_aux.ymax, die.ymax - 75)

    ec_ref_aux = die << gf.c.edge_coupler_array(
        pitch=-127, n=4, edge_coupler=ec_component, text=None
    )
    ec_ref_aux.rotate(-90)
    ec_ref_aux.mirror_x()
    ec_ref_aux.movex(ec_ref_aux.xmin, ec_ref.xmax + 63)
    ec_ref_aux.movey(ec_ref_aux.ymax, die.ymax - 75)

    ec_ref2_aux = die << gf.c.edge_coupler_array(
        pitch=-127, n=4, edge_coupler=ec_component, text=None
    )
    ec_ref2_aux.rotate(90)
    ec_ref2_aux.movex(ec_ref2_aux.xmax, ec_ref2.xmin - 63)
    ec_ref2_aux.movey(ec_ref2_aux.ymin, die.ymin + 75)

    ec_ref2_aux = die << gf.c.edge_coupler_array(
        pitch=-127, n=4, edge_coupler=ec_component, text=None
    )
    ec_ref2_aux.rotate(90)
    ec_ref2_aux.movex(ec_ref2_aux.xmin, ec_ref2.xmax + 63)
    ec_ref2_aux.movey(ec_ref2_aux.ymin, die.ymin + 75)

    #############################
    # VT + PSR                  #
    #############################
    excluded = {
        "o1",
        "o2",
        "o3",
        "o4",
        "o5",
        "o6",
        "o7",
        "o44",
        "o45",
        "o82",
        "o83",
        "o84",
        "o85",
        "o86",
        "o87",
        "o88",
    }

    upper_te = []
    upper_tm = []

    for port in ec_ref.ports:
        if port.name not in excluded:
            vt_ref = die << sin_si_transition
            vt_ref.connect("o2", port)
            st_ref = die << gf.c.straight(1, cross_section=xs)
            st_ref.connect("o1", vt_ref["o1"])
            psr_ref = die << psr
            psr_ref.connect("o2", st_ref["o2"], mirror=True)
            abs_ref = die << absorber
            abs_ref.connect("o1", psr_ref["o1"])

            ac_ref = die << ac
            ac_ref.connect("o1", psr_ref["o3"], mirror=True)
            upper_te.append(ac_ref["o2"])

            ac_ref = die << ac
            ac_ref.connect("o1", psr_ref["o4"])
            upper_tm.append(ac_ref["o2"])

    ec_in.extend((upper_tm, upper_te))

    lower_te = []
    lower_tm = []

    for port in ec_ref2.ports:
        if port.name not in excluded:
            vt_ref = die << sin_si_transition
            vt_ref.connect("o2", port)
            st_ref = die << gf.c.straight(1, cross_section=xs)
            st_ref.connect("o1", vt_ref["o1"])
            psr_ref = die << psr
            psr_ref.connect("o2", st_ref["o2"], mirror=True)
            abs_ref = die << absorber
            abs_ref.connect("o1", psr_ref["o1"])

            ac_ref = die << ac
            ac_ref.connect("o1", psr_ref["o4"])
            lower_tm.append(ac_ref["o2"])

            ac_ref = die << ac
            ac_ref.connect("o1", psr_ref["o3"], mirror=True)
            lower_te.append(ac_ref["o2"])

    ec_out.extend((lower_tm, lower_te))

    vt_ref1 = die << sin_si_transition
    vt_ref1.connect("o2", ec_ref["o44"])
    vt_ref2 = die << sin_si_transition
    vt_ref2.connect("o2", ec_ref["o45"])
    gf.routing.route_single(
        die,
        vt_ref1["o1"],
        vt_ref2["o1"],
        cross_section=xs,
        bend=bend_r5,
        auto_taper=False,
    )

    vt_ref1 = die << sin_si_transition
    vt_ref1.connect("o2", ec_ref2["o44"])
    vt_ref2 = die << sin_si_transition
    vt_ref2.connect("o2", ec_ref2["o45"])
    gf.routing.route_single(
        die,
        vt_ref1["o1"],
        vt_ref2["o1"],
        cross_section=xs,
        bend=bend_r5,
        auto_taper=False,
    )

    #############################
    # Cores                     #
    #############################
    x_separation = die.xmin + (die.xsize - mesh.xsize * 2) / 2
    inner_spacing = -235.62
    for i in range(2):
        mesh_ref = die << mesh
        mesh_ref.move(
            (mesh_ref.xmin, mesh_ref.y),
            (x_separation + i * mesh_ref.xsize - inner_spacing / 2, 0),
        )
        if i == 0:
            mesh_ref.movex(-3.18)
        else:
            mesh_ref.movex(73.725)
        meshes.append(mesh_ref)
        inner_spacing *= -1
    print("\nCreated Meshes\n")

    #############################
    # MUA IN                    #
    #############################
    temps = []
    for i in range(74):
        if i < 2:
            # 73 => TE & 74 => TM
            puc_ref = die << gf.get_component(
                puc(puc_number=f"mua{"73" if i == 0 else "74"}")
            )
        else:
            if numbered:
                puc_ref = die << gf.get_component(puc(puc_number=f"mua{1 + i - 2}"))
            else:
                puc_ref = die << gf.get_component(puc(puc_number="mua0"))

        puc_ref.rotate(-90)
        puc_ref.move(
            (puc_ref.x, puc_ref["o1"].y),
            (
                ec_ref["o8"].x - 6671.9 + 90 * i,
                ec_ref["o1"].y - 1790,
            ),
        )
        if i > 1:
            temps.append(puc_ref)

        st_ref = die << gf.c.straight(5, cross_section=xs)
        st_ref.connect("o1", puc_ref["o1"])
        bend_ref = die << bend_r5
        bend_ref.connect("o1", st_ref["o2"])
        st_ref = die << gf.c.straight(5, cross_section=xs)
        st_ref.connect("o1", bend_ref["o2"])
        bend_ref = die << bend_r5
        bend_ref.connect("o1", st_ref["o2"], mirror=True)
        st_ref = die << gf.c.straight(5, cross_section=xs)
        st_ref.connect("o1", bend_ref["o2"])
        if numbered:
            # 73 => TE & 74 => TM
            if i < 2:
                pd_aux = gf.get_component(
                    photodetector(custom_name=f"pucmua{"73" if i == 0 else "74"}")
                )
            else:
                pd_aux = gf.get_component(
                    photodetector(custom_name=f"pucmua{1 + i - 2}")
                )
        else:
            pd_aux = photodetector
        pd_ref = die << pd_aux
        pd_ref.connect("o1", st_ref["o2"])

        st_ref = die << gf.c.straight(5, cross_section=xs)
        st_ref.connect("o1", puc_ref["o3"])
        bend_ref = die << bend_r5
        bend_ref.connect("o1", st_ref["o2"])
        st_ref = die << gf.c.straight(5, cross_section=xs)
        st_ref.connect("o1", bend_ref["o2"])
        bend_ref = die << bend_r5
        bend_ref.connect("o1", st_ref["o2"], mirror=True)
        st_ref = die << gf.c.straight(5, cross_section=xs)
        st_ref.connect("o1", bend_ref["o2"])
        if numbered:
            # 73 => TE & 74 => TM
            if i < 2:
                pd_aux = gf.get_component(
                    photodetector(custom_name=f"pucmua{"73" if i == 0 else "74"}")
                )
            else:
                pd_aux = gf.get_component(
                    photodetector(custom_name=f"pucmua{1 + i - 2}")
                )
        else:
            pd_aux = photodetector
        pd_ref = die << pd_aux
        pd_ref.connect("o1", st_ref["o2"])

    mua_in.append(temps.copy())
    temps.clear()

    for i in range(74):
        # 73 => TE & 74 => TM
        if i > 71:
            puc_ref = die << gf.get_component(
                puc(puc_number=f"mua{"73" if i == 72 else "74"}")
            )
        else:
            if numbered:
                puc_ref = die << gf.get_component(puc(puc_number=f"mua{1 + i}"))
            else:
                puc_ref = die << gf.get_component(puc(puc_number="mua0"))
        puc_ref.rotate(-90)
        puc_ref.move(
            (puc_ref.x, puc_ref["o1"].y),
            (
                ec_ref["o82"].x - 4730.092 + 90 * i,
                ec_ref["o1"].y - 1790,
            ),
        )
        if i < 72:
            temps.append(puc_ref)
        st_ref = die << gf.c.straight(5, cross_section=xs)
        st_ref.connect("o1", puc_ref["o1"])
        bend_ref = die << bend_r5
        bend_ref.connect("o1", st_ref["o2"])
        st_ref = die << gf.c.straight(5, cross_section=xs)
        st_ref.connect("o1", bend_ref["o2"])
        bend_ref = die << bend_r5
        bend_ref.connect("o1", st_ref["o2"], mirror=True)
        st_ref = die << gf.c.straight(5, cross_section=xs)
        st_ref.connect("o1", bend_ref["o2"])
        if numbered:
            # 73 => TE & 74 => TM
            if i > 71:
                pd_aux = gf.get_component(
                    photodetector(custom_name=f"pucmua{"73" if i == 72 else "74"}")
                )
            else:
                pd_aux = gf.get_component(photodetector(custom_name=f"pucmua{1 + i}"))
        else:
            pd_aux = photodetector
        pd_ref = die << pd_aux
        pd_ref.connect("o1", st_ref["o2"])

        st_ref = die << gf.c.straight(5, cross_section=xs)
        st_ref.connect("o1", puc_ref["o3"])
        bend_ref = die << bend_r5
        bend_ref.connect("o1", st_ref["o2"])
        st_ref = die << gf.c.straight(5, cross_section=xs)
        st_ref.connect("o1", bend_ref["o2"])
        bend_ref = die << bend_r5
        bend_ref.connect("o1", st_ref["o2"], mirror=True)
        st_ref = die << gf.c.straight(5, cross_section=xs)
        st_ref.connect("o1", bend_ref["o2"])
        if numbered:
            # 73 => TE & 74 => TM
            if i > 71:
                pd_aux = gf.get_component(
                    photodetector(custom_name=f"pucmua{"73" if i == 72 else "74"}")
                )
            else:
                pd_aux = gf.get_component(photodetector(custom_name=f"pucmua{1 + i}"))
        else:
            pd_aux = photodetector
        pd_ref = die << pd_aux
        pd_ref.connect("o1", st_ref["o2"])

    mua_in.append(temps.copy())

    print("\nCreated MUA IN\n")

    ###################
    # Output MUA      #
    ###################
    for jdx in range(2):
        temps = []
        for i in range(74):
            if jdx == 0: # LEFT
                if i > 1:
                    puc_number = 75 + i - 2 if numbered else 0
                else:
                    puc_number = 147 + i
            else: # RIGHT
                if i < 72:
                    puc_number = 75 + i if numbered else 0
                else:
                    puc_number = 147 - 72 + i

            puc_ref = die << gf.get_component(puc(puc_number=f"mua{puc_number}"))

            # Place the PUCs
            puc_ref.rotate(-90)

            if jdx == 0: # LEFT
                puc_ref.move(
                    (puc_ref.x, puc_ref["o1"].y),
                    (
                        ec_ref2["o8"].x - 1800.583 + 90 * i,
                        ec_ref2["o1"].y + 1970.2,
                    ),
                )
            else: # RIGHT
                puc_ref.move(
                    (puc_ref.x, puc_ref["o1"].y),
                    (
                        ec_ref2["o82"].x - 25.1 + 90 * i,
                        ec_ref2["o1"].y + 1970.2,
                    ),
                )

            temps.append(puc_ref)

            # Place the PDs
            st_ref = die << gf.c.straight(5, cross_section=xs)
            st_ref.connect("o1", puc_ref["o1"])
            bend_ref = die << bend_r5
            bend_ref.connect("o1", st_ref["o2"])
            st_ref = die << gf.c.straight(5, cross_section=xs)
            st_ref.connect("o1", bend_ref["o2"])
            bend_ref = die << bend_r5
            bend_ref.connect("o1", st_ref["o2"], mirror=True)
            st_ref = die << gf.c.straight(5, cross_section=xs)
            st_ref.connect("o1", bend_ref["o2"])
            if numbered:
                pd_aux = gf.get_component(photodetector(custom_name=f"pucmua{puc_number}"))
            else:
                pd_aux = photodetector
            pd_ref = die << pd_aux
            pd_ref.connect("o1", st_ref["o2"])

            st_ref = die << gf.c.straight(5, cross_section=xs)
            st_ref.connect("o1", puc_ref["o3"])
            bend_ref = die << bend_r5
            bend_ref.connect("o1", st_ref["o2"])
            st_ref = die << gf.c.straight(5, cross_section=xs)
            st_ref.connect("o1", bend_ref["o2"])
            bend_ref = die << bend_r5
            bend_ref.connect("o1", st_ref["o2"], mirror=True)
            st_ref = die << gf.c.straight(5, cross_section=xs)
            st_ref.connect("o1", bend_ref["o2"])
            if numbered:
                pd_aux = gf.get_component(photodetector(custom_name=f"pucmua{puc_number}"))
            else:
                pd_aux = photodetector
            pd_ref = die << pd_aux
            pd_ref.connect("o1", st_ref["o2"])

        mua_out.append(temps.copy())
        temps.clear()

    print("\nCreated MUA OUT\n")

    #############################
    # EC Trenches               #
    #############################
    center = die.x
    upper_trench_ref = die << gf.c.rectangle((24800, 65), (190, 0), None, None)
    upper_trench_ref.move(
        (upper_trench_ref.x, upper_trench_ref.ymax), (center, die.ymax - 10)
    )

    lower_trench_ref = die << gf.c.rectangle((24800, 65), (190, 0), None, None)
    lower_trench_ref.move(
        (lower_trench_ref.x, lower_trench_ref.ymin), (center, die.ymin + 10)
    )

    #############################
    # Ring Trenches             #
    #############################
    v7b.border_rectangles(
        die=die,
        layer=(190, 0),
        size=(500, 40),
        border_separation=650,
        separation=20,
        keepout_layers=[
            (259, 0),
        ],
        keepout_distance=100,
        extra_keepout=[
            (-7397.40, 11000, 7328.97, 12500.00),
            (-7325.82, -12559.55, 7400.55, -11000),
        ],
        die_bbox=(-12350, -12500, 12350, 12500),
        end_fill="fill",
        align="center",
    )

    print("\nCreated border guard trenches\n")

    #############################
    # Logos                     #
    #############################
    ipr_logo_ref = die << ipronics_logo()
    ipr_logo_ref.move(
        (ipr_logo_ref.xmin, ipr_logo_ref.ymax), (die.xmin + 4920 - 508, die.ymax - 300)
    )
    ipr_logo_ref = die << ipronics_logo()
    ipr_logo_ref.rotate(180)
    ipr_logo_ref.move(
        (ipr_logo_ref.xmax, ipr_logo_ref.ymin), (die.xmax - 4920 + 508, die.ymin + 300)
    )
    v7b_logo_ref = die << v7b_logo()
    v7b_logo_ref.move(
        (v7b_logo_ref.xmax, v7b_logo_ref.ymax), (die.xmax - 5300 + 508, die.ymax - 230)
    )
    v7b_logo_ref = die << v7b_logo()
    v7b_logo_ref.rotate(180)
    v7b_logo_ref.move(
        (v7b_logo_ref.xmin, v7b_logo_ref.ymin), (die.xmin + 5225 - 508, die.ymin + 275)
    )

    print("\nCreated logos\n")

    #############################
    # Orientation Markers       #
    #############################
    # EC's
    for x, y in [
        (-5683.25 - 508, 12300),
        (5619.75 + 508, 12300),
        (-5619.75 - 508, -12300),
        (5683.25 + 508, -12300),
    ]:
        circle_ref = die << gf.c.circle(50, layer=(28, 0))
        circle_ref.move((circle_ref.x, circle_ref.y), (x, y))

    # Chip
    for x, y in [
        (12425, 12425),
        (12425, -12425),
        (-12425, -12425),
    ]:
        circle_ref = die << gf.c.circle(25, layer=(28, 0))
        circle_ref.move((circle_ref.x, circle_ref.y), (x, y))

    W, H, cut = 50.0, 50.0, 40.0
    c = gf.Component("rounded_triangle")
    c.add_polygon([(0, 0), (W, 0), (W, H - cut), (W - cut, H), (0, H)], layer=(28, 0))
    marker_ref = die << c
    marker_ref.rotate(-90)
    marker_ref.move((marker_ref.x, marker_ref.y), (-12425, 12425))

    print("\nCreated orientation markers\n")

    #############################
    # Thermistors               #
    #############################
    locations = [
        (-11447.13900, 11501.32500),
        (-10727.13900, -18.67500),
        (-11267.13900, -10638.67500),
        (-1187.13900, 10601.32500),
        (252.86100, -18.67500),
        (792.86100, -10098.67500),
        (10872.86100, 11501.32500),
        (11412.86100, 161.32500),
        (11412.86100, -10638.67500),
    ]
    for location in locations:
        th_ref = die << thermistor
        th_ref.rotate(90)
        th_ref.move((th_ref.x, th_ref.y), (location[0] - 32.25, location[1] - 80))

    print("\nCreated Thermistors\n")

    #############################
    # Labels                    #
    #############################
    for i in range(96):
        text_ref = die << gf.c.text(f"EC_{i+1}", 30, layer=(28, 0))
        text_ref.rotate(-90)
        text_ref.move((text_ref.x, text_ref.y), (-6000.75 + 127 * i, 12177))

        text_ref = die << gf.c.text(f"EC_{i+1}", 30, layer=(28, 0))
        text_ref.rotate(-90)
        text_ref.move((text_ref.x, text_ref.y), (-5937.25 + 127 * i, -12177))

    print("\nCreated Labels\n")
