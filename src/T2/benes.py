import math

import gdsfactory as gf
import iprlayout_tower as ipr
from gdsfactory.typings import ComponentSpec, CrossSectionSpec
from iprlayout_tower.tower_tech import LAYER


@gf.cell
def crossing_anwg_si(
    cross_section_anwg: CrossSectionSpec = "strip",
    cross_section_swg: CrossSectionSpec = "strip",
) -> gf.Component:
    c = gf.Component()
    anwg_width = gf.get_cross_section(cross_section_anwg).width
    si_width = gf.get_cross_section(cross_section_swg).width
    st_anwg = c << gf.c.straight(
        cross_section=cross_section_anwg,
        length=2 + si_width,
    )
    st = c << gf.c.straight(cross_section=cross_section_swg, length=6 + anwg_width)
    st.rotate(90)
    st.movex(st["o1"].x, 1 + si_width / 2.0)
    st.movey(st["o1"].y, st_anwg["o1"].y - anwg_width / 2.0 - 3)
    c.add_port("o1", port=st_anwg["o1"])
    c.add_port("o3", port=st_anwg["o2"])
    c.add_port("o2", port=st["o2"])
    c.add_port("o4", port=st["o1"])
    c.flatten()
    return c


@gf.cell
def crossing_triangle_anwg_si(
    order: int = 3,
    distance_x: float = 10.0,
    distance_y: float = 200.0,
    cross_section_anwg: CrossSectionSpec = "strip",
    cross_section_swg: CrossSectionSpec = "strip",
    vertical_transition: ComponentSpec = "si_anwg_transition",
    vertical_transition_in: bool = True,
    vertical_transition_out: bool = True,
    extra_y_middle: bool = False,
    extra_x: float = 0.0,
) -> gf.Component:
    """Returns a matrix of crossings for each stage of a Benes mesh configuration

    Args:
         order: number of num max of triangle.
         distance_x: distance between si wg.
         distance_y: distance between anwg.
         cross_section: cross section of the waveguide structures.
    """

    c = gf.Component()

    width = gf.get_cross_section(cross_section_swg).width
    crossing = crossing_anwg_si(
        cross_section_anwg=cross_section_anwg, cross_section_swg=cross_section_swg
    )
    vt_last = 0
    # anwg
    for i in range(order - 1):
        if vertical_transition_in:
            vt_in = c << gf.get_component(vertical_transition)
        else:
            vt_in = c << gf.c.straight(
                cross_section=cross_section_anwg,
                length=1,
            )

        if i > 0:
            vt_in.movey(vt_last["o1"].y - distance_y)
            if i == order / 2.0 - 1 and extra_y_middle:
                vt_in.movey(-distance_y * 2)

        vt_last = vt_in
        c.add_port(f"o{2 * i + 2}", port=vt_in["o1"])

        if i < order - 2:
            st = c << gf.c.straight(
                cross_section=cross_section_anwg,
                length=(order - 1) * width
                + (order - 2) * distance_x
                + 2.285
                + extra_x / 2.0
                - crossing.xsize * (i + 1)
                - (distance_x - 2) * i,
            )
            st.connect("o1", vt_in["o2"])
        else:
            st = c << gf.c.straight(
                cross_section=cross_section_anwg, length=0.57 / 2.0 + extra_x / 2.0
            )
            st.connect("o1", vt_in["o2"])
            # st = vt_in

        for j in range(i + 1):
            cross_ref = c << crossing
            cross_ref.connect("o1", st["o2"])
            if j < i:
                st = c << gf.c.straight(
                    cross_section=cross_section_anwg,
                    length=(distance_x - 2),
                )
                st.connect("o1", cross_ref["o3"])

            if j == 0:
                c.add_port(f"o{2 * i + 1}", port=cross_ref["o2"])

            if i < order - 2:
                if i == order / 2.0 - 2 and extra_y_middle:
                    extra = distance_y * 2
                else:
                    extra = 0
                sty = c << gf.c.straight(
                    cross_section=cross_section_swg,
                    length=(distance_y - cross_ref.ysize) + extra,
                )
                sty.connect("o1", cross_ref["o4"])
            else:
                c.add_port(f"o{2 * order - 1 + j}", port=cross_ref["o4"])

        if vertical_transition_out:
            st = c << gf.c.straight(
                cross_section=cross_section_anwg,
                length=0.57 / 2.0 + extra_x / 2.0,
            )
            st.connect("o1", cross_ref["o3"])
            vt_out = c << gf.get_component(vertical_transition)
        else:
            vt_out = c << gf.c.straight(
                cross_section=cross_section_anwg,
                length=1,
            )
        vt_out.connect("o2", st["o2"])
        c.add_port(f"o{(order - 1) * 4 - i}", port=vt_out["o1"])

    return c


@gf.cell
def component_with_straight(component, cross_section):
    c = gf.Component()

    # Add the component
    c << component

    # Add straight to ports
    for port in component.ports:
        strt_length = 0.004
        strt = c << ipr.fast_straight(length=strt_length, cross_section=cross_section)
        strt.connect("o2", port)

        # Add port
        c.add_port(port.name, port=port)

    c.flatten()
    c.info = component.info
    return c


@gf.cell(check_instances=False)
def crossings_matrix_d(
    crossing: gf.partial = "crossing",
    order: int = 8,
    distance: float = 100.0,
    cross_section: CrossSectionSpec = "strip",
) -> gf.Component:
    """Returns a matrix of crossings for each stage of a Benes mesh configuration

    Args:
         order: order of the mesh.
         distance_x: distance between crossings in x axis.
         cross_section: cross section of the waveguide structures.
         width: waveguide width.
    """

    c = gf.Component()
    crossing_component = gf.get_component(crossing)
    crossing_component = component_with_straight(
        crossing_component, cross_section=gf.get_cross_section("strip", width=1.56)
    )
    bend_component = ipr.bend_euler_custom_width(
        radius=5, p=0.755, angle=45, cross_section=cross_section
    )
    cross_section = gf.get_cross_section(cross_section)
    width_str = crossing_component["o1"].width

    # Instanciate all the crossings that will form the Benes mesh
    total_num_cross = int(order**2 / 8 - order / 4)
    crossings = [0] * total_num_cross
    cols = int(order / 2 - 1)  # Number of columns of crossings
    size_row = 1  # Number of crossings per column
    cont_cross = 0
    id_crossing = 0

    # generete the crossings
    for i in range(cols):
        for j in range(size_row):
            if width_str != gf.get_cross_section(cross_section).width:
                crossing_kwargs = {
                    "bbmul": crossing_component,
                    "bbadd": ipr.rib_taper(
                        m_RIB=1.95,
                        width_RIB_in=1.56,
                        width_RIB_out=0.41,
                        length=9.8,
                        cross_section="strip",
                    ),
                }
                if order == 4:
                    crossing_kwargs["bbmul_list"] = ["o1", "o2", "o3", "o4"]
                else:
                    if j == 0 and i == 0:
                        crossing_kwargs["bbmul_list"] = ["o1", "o2"]
                    elif j == 0 and i != cols - 1 and i != 0:
                        crossing_kwargs["bbmul_list"] = ["o1"]
                    elif j == size_row - 1 and i < cols - 1 and i != 0:
                        crossing_kwargs["bbmul_list"] = ["o2"]
                    elif i == cols - 1:
                        if j == 0:
                            crossing_kwargs["bbmul_list"] = ["o1", "o3", "o4"]
                        elif j == size_row - 1:
                            crossing_kwargs["bbmul_list"] = ["o2", "o3", "o4"]
                        else:
                            crossing_kwargs["bbmul_list"] = ["o3", "o4"]
                    else:
                        crossing_kwargs["bbmul_list"] = None

                if crossing_kwargs["bbmul_list"] is not None:
                    crossing_c = ipr.bb_mul_bb(**crossing_kwargs)
                else:
                    crossing_c = crossing_component

                crossings[id_crossing] = c << crossing_c
            else:
                crossings[id_crossing] = c << crossing_component

            id_crossing = id_crossing + 1
        size_row = size_row + 1

    crossing_ref = []
    distx_array = []
    port_ins = []
    port_outs = []
    size_row = 1
    cont_cross = 0
    rda = ipr.random_number_array(mean=1, n_elements=cols, variation=0.141)

    # move the crossings
    for i in range(cols):
        for k in range(size_row):
            crossings[cont_cross].rotate(45)
            if k == 0:  # first row (lower one)
                if i == 0:
                    distx = 0
                else:
                    distx = distance / 2.0 + rda[i]
                crossings[cont_cross].movey(-(sum(distx_array) + distx))
                crossings[cont_cross].movex(sum(distx_array) + distx)
                crossing_ref.insert(0, crossings[cont_cross])
                distx_array.insert(0, distx)
            else:
                if k == 1 and i == 1:
                    difference_transition = (
                        crossings[cont_cross].ports["o1"].x - crossings[0].ports["o1"].x
                    )  # calculate difference in x and y with the transition and not
                crossings[cont_cross].movey(
                    crossings[cont_cross].ports["o1"].y,
                    crossing_ref[k].ports["o1"].y
                    + difference_transition
                    + sum(distx_array[len(distx_array) - 1 - k : -1]),
                )
                crossings[cont_cross].movex(
                    crossings[cont_cross].ports["o1"].x,
                    crossing_ref[k].ports["o1"].x
                    + difference_transition
                    + sum(distx_array[len(distx_array) - 1 - k : -1]),
                )

            if i < cols - 1:
                port_ins.append(crossings[cont_cross].ports["o4"])
                port_outs.append(crossings[cont_cross + size_row].ports["o2"])
                port_ins.append(crossings[cont_cross].ports["o3"])
                port_outs.append(crossings[cont_cross + size_row + 1].ports["o1"])
                if k == 0:
                    b = c << component_with_straight(
                        component=bend_component, cross_section=cross_section
                    )
                    b.connect("o1", crossings[cont_cross].ports["o1"])
                    c.add_port(
                        name=f"o{round((order - 2) * 1.5 + 1 + i)}",
                        center=(b["o2"].x, b["o2"].y),
                        orientation=b["o2"].orientation,
                        layer=gf.get_cross_section(cross_section).layer,
                        width=b["o2"].width,
                    )

                    if i == 0:
                        b = c << component_with_straight(
                            component=bend_component, cross_section=cross_section
                        )
                        b.mirror_x()
                        b.connect("o1", crossings[cont_cross].ports["o2"])
                        c.add_port(
                            name=f"o{round((order - 2) * 1.5) - i}",
                            center=(b["o2"].x, b["o2"].y),
                            orientation=b["o2"].orientation,
                            layer=gf.get_cross_section(cross_section).layer,
                            width=b["o2"].width,
                        )

                elif k == size_row - 1:
                    b = c << component_with_straight(
                        component=bend_component, cross_section=cross_section
                    )
                    b.mirror_x()
                    b.connect("o1", crossings[cont_cross].ports["o2"])
                    c.add_port(
                        name=f"o{round((order - 2) * 1.5) - i}",
                        center=(b["o2"].x, b["o2"].y),
                        orientation=b["o2"].orientation,
                        layer=gf.get_cross_section(cross_section).layer,
                        width=b["o2"].width,
                    )

            else:
                b = c << component_with_straight(
                    component=bend_component, cross_section=cross_section
                )
                b.mirror_x()
                b.connect("o1", crossings[cont_cross].ports["o3"])
                c.add_port(
                    name=f"o{2 * k + 2}",
                    center=(b["o2"].x, b["o2"].y),
                    orientation=b["o2"].orientation,
                    layer=gf.get_cross_section(cross_section).layer,
                    width=b["o2"].width,
                )
                b = c << component_with_straight(
                    component=bend_component, cross_section=cross_section
                )
                b.connect("o1", crossings[cont_cross].ports["o4"])
                c.add_port(
                    name=f"o{2 * k + 1}",
                    center=(b["o2"].x, b["o2"].y),
                    orientation=b["o2"].orientation,
                    layer=gf.get_cross_section(cross_section).layer,
                    width=b["o2"].width,
                )
                if order == 4:
                    b = c << component_with_straight(
                        component=bend_component, cross_section=cross_section
                    )
                    b.connect("o1", crossings[cont_cross].ports["o2"])
                    c.add_port(f"o{round((order - 2) * 1.5) - i}", port=b["o2"])
                if k == 0:
                    b = c << component_with_straight(
                        component=bend_component, cross_section=cross_section
                    )
                    if order == 4:
                        b.mirror_y()
                    b.connect("o1", crossings[cont_cross].ports["o1"])
                    c.add_port(
                        name=f"o{round((order - 2) * 1.5 + 1 + i)}",
                        center=(b["o2"].x, b["o2"].y),
                        orientation=b["o2"].orientation,
                        layer=gf.get_cross_section(cross_section).layer,
                        width=b["o2"].width,
                    )
                elif k == size_row - 1:
                    b = c << component_with_straight(
                        component=bend_component, cross_section=cross_section
                    )
                    b.mirror_x()
                    b.connect("o1", crossings[cont_cross].ports["o2"])
                    c.add_port(
                        name=f"o{round((order - 2) * 1.5) - i}",
                        center=(b["o2"].x, b["o2"].y),
                        orientation=b["o2"].orientation,
                        layer=gf.get_cross_section(cross_section).layer,
                        width=b["o2"].width,
                    )

            cont_cross = cont_cross + 1

        size_row = size_row + 1

    # routing between crossings
    sections = []
    for layer in crossing_component.info["layers"]:
        port_names = (None, None)
        if gf.get_layer_name(layer) == "swg":
            width = width_str
            port_names = ("o1", "o2")
            sections.append(
                gf.Section(
                    width=width,
                    offset=0,
                    layer=layer,
                    name=gf.get_layer_name(layer),
                    port_names=port_names,
                )
            )

    cs = gf.CrossSection(sections=sections)
    size_row = 1
    cont_cross = 0
    ls = []
    for _ in range(cols - 1):
        for k in range(size_row):
            extra1 = 0.000  # add error
            extra2 = 0.000
            dx = abs(
                crossings[cont_cross].ports["o3"].x
                - crossings[cont_cross + size_row + 1].ports["o1"].x
            )
            dy = abs(
                crossings[cont_cross].ports["o3"].y
                - crossings[cont_cross + size_row + 1].ports["o1"].y
            )
            dist_crossings_ports = math.sqrt(dx**2 + dy**2)
            st = c << gf.c.straight(
                length=dist_crossings_ports + extra1,
                cross_section=cs,
            )
            st.connect("o1", crossings[cont_cross].ports["o3"])

            dx = abs(
                crossings[cont_cross].ports["o4"].x
                - crossings[cont_cross + size_row].ports["o2"].x
            )
            dy = abs(
                crossings[cont_cross].ports["o4"].y
                - crossings[cont_cross + size_row].ports["o2"].y
            )
            dist_crossings_ports = math.sqrt(dx**2 + dy**2)
            st = c << gf.c.straight(
                length=dist_crossings_ports + extra2,
                cross_section=cs,
            )
            st.connect("o1", crossings[cont_cross].ports["o4"])
            if k == 0:
                ls.append(round(dist_crossings_ports + extra2, 3))
            cont_cross = cont_cross + 1
        size_row = size_row + 1
    return c


@gf.cell(check_instances=False)
def dilated_benes(
    order: int = 8,
    extra_stages: int = 0,
    crossing: gf.partial = "crossing",
    puc: ComponentSpec = "puc",
    cross_section: CrossSectionSpec = "strip",
    bend: gf.partial = "bend_euler_custom_width",
    taper: gf.partial = "rib_taper",
    distance_y: float = 200.0,
    distance_cross: float = 20.0,
    optical_routing_spacing: float = 10.0,  # Spacing (um) for the optical routing
    labels: bool = False,
    transition_output: bool = True,
    nn: int = 0,
    core: int = 1,
    size_x_cross_matrix_array: list | None = None,
    th: int = 64,
) -> gf.Component:
    """Returns a flat general purpose hexagonal waveguide mesh arrangement

    Args:
         mesh_order: size of the mesh.
         crossing: crossing to use.
         puc: puc to use.
         cross_section: cross section of the waveguide structures.
         width: waveguide width.
         label: True add labels to pucs.

    """
    c = gf.Component()
    num_rows = int(order)
    num_columns = int(math.log2(order))
    num_pucs = num_rows * (num_columns + 1) + extra_stages * num_rows
    pucs = [0] * num_pucs
    width = gf.get_cross_section(cross_section).width
    bend = gf.get_component(bend)
    taper = gf.get_component(taper)
    radius = abs(bend["o2"].y - bend["o1"].y)
    # Instanciate all the pucs that will form the Benes mesh
    for n in range(num_pucs):
        if labels:
            init = num_pucs * core + nn
            pucs[n] = c << gf.get_component(
                gf.partial(
                    puc,
                    labels=labels,
                    puc_number=init + n,
                )
            )
        else:
            pucs[n] = c << gf.get_component(
                gf.partial(
                    puc,
                    labels=labels,
                )
            )

    puc_count = 0  # Puc counter
    ref = 0  # Reference for placing the columns of PUCs
    order_aux = order * 2  # Auxiliar value for the order of the crossing matrices
    size_x_cross_matrix = []  # Size (x dimension) of the crossing matrices
    size_x_cross_matrix_aux = [0] * num_columns
    # Move the columns of PUCs to give space for the crossing sections
    for x in range(num_columns + 1 + extra_stages):
        # Define the space between PUCs in the stages (depending on the width of
        # crossings sections)
        if x < num_columns:
            if x != 0:
                order_aux = order_aux / 2
            else:
                order_aux = order_aux

            if order_aux > th:
                cross_section_anwg = gf.get_cross_section(
                    "strip", width=2, layer=LAYER.anwg
                )
                cross_section_swg = gf.get_cross_section(
                    "strip", width=0.93, layer=LAYER.swg
                )
                cross_matrix_aux = crossing_triangle_anwg_si(
                    order=int(order_aux / 2.0),
                    distance_x=5.57,
                    distance_y=distance_y / 2.0,
                    cross_section_anwg=cross_section_anwg,
                    cross_section_swg=cross_section_swg,
                    vertical_transition=ipr.si_anwg_transition(width_out=2.0),
                )
            else:
                cross_matrix_aux = crossings_matrix_d(
                    crossing=crossing,
                    order=order_aux,
                    distance=distance_cross,
                    cross_section=cross_section,
                )  # Puts a dummy crossing matrix to compute the size

            if size_x_cross_matrix_array is None:
                if order_aux > th:
                    size_x_cross_matrix.append(cross_matrix_aux.xsize)
                    size_x_cross_matrix[x] = round(
                        size_x_cross_matrix[x]
                        + gf.get_component(puc).xsize
                        + (
                            optical_routing_spacing
                            + gf.get_cross_section(cross_section).width
                        )
                        * (order_aux - 4)
                        + 4 * radius
                        + 2,
                        3,
                    )

                else:
                    size_x_cross_matrix.append(
                        abs(
                            cross_matrix_aux.ports[
                                "o" + str(int((order_aux - 2.0) * 1.5))
                            ].x
                            - cross_matrix_aux.ports["o1"].x
                        )
                    )
                    size_x_cross_matrix[x] = round(
                        size_x_cross_matrix[x]
                        + gf.get_component(puc).xsize
                        + ((order_aux - 2) / 2)
                        * (
                            optical_routing_spacing
                            + gf.get_cross_section(cross_section).width
                        )
                        + 4 * (radius + 1),
                        3,
                    )
                size_x_cross_matrix_aux[x] = size_x_cross_matrix[x]

            else:
                size_x_cross_matrix = size_x_cross_matrix_array
                if order_aux > th:
                    size_x_cross_matrix_aux[x] = round(
                        cross_matrix_aux.xsize
                        + gf.get_component(puc).xsize
                        + (
                            optical_routing_spacing
                            + gf.get_cross_section(cross_section).width
                        )
                        * (order_aux - 4)
                        + 4 * radius
                        + 2,
                        3,
                    )

                else:
                    size_x_cross_matrix_aux[x] = round(
                        abs(
                            cross_matrix_aux.ports[
                                "o" + str(int((order_aux - 2.0) * 1.5))
                            ].x
                            - cross_matrix_aux.ports["o1"].x
                        )
                        + gf.get_component(puc).xsize
                        + ((order_aux - 2) / 2)
                        * (
                            optical_routing_spacing
                            + gf.get_cross_section(cross_section).width
                        )
                        + 4 * (radius + 1),
                        3,
                    )

        # Move the PUCs using the computed space for the crossing matrices
        if x < num_columns + 1:
            for j in range(num_rows):
                if x == 0:
                    pucs[puc_count].move([ref, -distance_y * j])
                else:
                    pucs[puc_count].movey(-distance_y * j)
                    pucs[puc_count].movex(
                        pucs[puc_count].ports["o1"].x,
                        ref + size_x_cross_matrix[x - 1],
                    )

                if j == num_rows - 1:
                    ref = pucs[puc_count].ports["o1"].x
                puc_count = puc_count + 1

        else:
            s = x - (num_columns + 1)
            for j in range(num_rows):
                pucs[puc_count].movey(-distance_y * j)
                pucs[puc_count].movex(
                    pucs[puc_count].ports["o1"].x,
                    ref + size_x_cross_matrix[extra_stages - s - 1],
                )
                if j == num_rows - 1:
                    ref = pucs[puc_count].ports["o1"].x
                puc_count = puc_count + 1

    # print("size_x_cross_matrix", size_x_cross_matrix)
    # Put the crossings (from the outside sections to the inner sections)
    # Compute the number of stages (i.e., starting in the middle column of PUCs,
    # how many crossing sections are)
    stages = num_columns

    order_cross_matrix = order * 2
    order_cross_matrices = []
    actual_col = 0

    for s in range(stages):
        # Creates all the crossing matrices of each stage and stores them in
        # "cross_matrices"
        cross_matrices = [0] * 2 ** (s)
        order_cross_matrices.append(order_cross_matrix)
        cross_matrix_mirror_array = []
        for k in range(len(cross_matrices)):
            if order_cross_matrices[s] > th:
                cross_section_anwg = gf.get_cross_section(
                    "strip", width=2, layer=LAYER.anwg
                )
                cross_section_swg = gf.get_cross_section(
                    "strip", width=0.93, layer=LAYER.swg
                )
                cross_matrices[k] = c << crossing_triangle_anwg_si(
                    order=int(order_cross_matrix / 2.0),
                    distance_x=5.57,
                    distance_y=distance_y / 2.0,
                    cross_section_anwg=cross_section_anwg,
                    cross_section_swg=cross_section_swg,
                    vertical_transition=ipr.si_anwg_transition(width_out=2.0),
                )  # Left crossing
            else:
                cross_matrices[k] = c << crossings_matrix_d(
                    crossing=crossing,
                    order=order_cross_matrix,
                    distance=distance_cross,
                    cross_section=cross_section,
                )  # Left crossing
                cross_matrices[k].mirror_x()
                cross_matrices[k].mirror_y()

        # Y-size of the crossings structure (to center them in the full mesh)
        size_y_cross_matrix = (
            cross_matrices[0].ports["o1"].y
            - cross_matrices[0].ports["o" + str(int(order_cross_matrix - 2))].y
        )
        -(cross_matrices[0].ports["o1"].y - cross_matrices[0].ports["o2"].y) / 2

        move_x = 0
        move_y = 0

        for m in range(int(len(cross_matrices))):
            # Reference of the top puc of the stage "s" to center the crossing matrix
            ref1 = int((num_rows * s) + m * num_rows / 2**s)
            # Reference of the bottom puc of the stage "s" to center the crossing matrix
            ref2 = int((num_rows * s) + m * num_rows / 2**s + num_rows / 2**s - 1)
            # print("ref1 ", ref1)
            # print("ref2 ", ref2)
            if order_cross_matrices[s] > th:
                move_x = (
                    pucs[actual_col * num_rows].ports["o3"].x
                    + (
                        optical_routing_spacing
                        + gf.get_cross_section(cross_section).width
                    )
                    * (order_cross_matrix - 4)
                    + 2 * (radius)
                    + 1
                    + (size_x_cross_matrix[s] - size_x_cross_matrix_aux[s]) / 2.0
                )
                # Center the crossing sublayouts that are on the left of the mesh
                # Center in Y-axis
                cross_matrices[m].movey(
                    cross_matrices[m].ports["o2"].y,
                    pucs[ref1 + 1].ports["o3"].y + distance_y / 2.0,
                )

            else:
                move_x = (
                    pucs[actual_col * num_rows].ports["o3"].x
                    - cross_matrices[m].ports["o1"].x
                    + ((order_cross_matrix - 2) / 2)
                    * (
                        optical_routing_spacing
                        + gf.get_cross_section(cross_section).width
                    )
                    + 2 * (radius + 1)
                    + (size_x_cross_matrix[s] - size_x_cross_matrix_aux[s]) / 2.0
                )

                move_y = round(
                    (
                        abs(pucs[ref1].ports["o3"].y - pucs[ref2].ports["o4"].y)
                        - size_y_cross_matrix
                    )
                    / 2
                )

                # Center the crossing sublayouts that are on the left of the mesh
                # Center in Y-axis
                cross_matrices[m].movey(
                    cross_matrices[m].ports["o1"].y, pucs[ref1].ports["o3"].y - move_y
                )
            # Center in X-axis
            cross_matrices[m].movex(move_x)
            if s == stages - 1:
                cross_matrices[m].movex(-3.25)

            if s < extra_stages:
                cross_matrix_mirror = c << cross_matrices[m].cell
                # Center the crossing sublayouts that are on the right of the mesh
                # (mirrored) Center in Y-axis
                # cross_matrix_mirror.mirror_x()
                if order_cross_matrices[s] > th:
                    cross_matrix_mirror.mirror_x()
                    cross_matrix_mirror.mirror_y()
                    cross_matrix_mirror.movey(
                        cross_matrix_mirror.ports["o2"].y,
                        pucs[ref2 - 1].ports["o1"].y - distance_y / 2.0,
                    )
                    # Center in X-axis
                    move_x = (
                        (
                            optical_routing_spacing
                            + gf.get_cross_section(cross_section).width
                        )
                        * (order_cross_matrix - 4)
                        + 2 * (radius)
                        + 1
                        + (size_x_cross_matrix[s] - size_x_cross_matrix_aux[s]) / 2.0
                    )

                    cross_matrix_mirror.movex(
                        cross_matrix_mirror["o2"].x,
                        pucs[
                            (num_columns * num_rows + extra_stages * num_rows)
                            - (actual_col * num_rows)
                            + 1
                        ]
                        .ports["o2"]
                        .x
                        - move_x,
                    )
                    cross_matrix_mirror_array.append(cross_matrix_mirror)
                else:
                    cross_matrix_mirror.mirror_y()
                    cross_matrix_mirror.movey(
                        cross_matrix_mirror.ports["o1"].y,
                        pucs[ref1].ports["o3"].y - move_y,
                    )
                    # Center in X-axis
                    move_x = (
                        ((order_cross_matrix - 2) / 2)
                        * (
                            optical_routing_spacing
                            + gf.get_cross_section(cross_section).width
                        )
                        + 2 * (radius + 1)
                        + (size_x_cross_matrix[s] - size_x_cross_matrix_aux[s]) / 2.0
                    )

                    cross_matrix_mirror.movex(
                        cross_matrix_mirror["o1"].x,
                        pucs[
                            (num_columns * num_rows + extra_stages * num_rows)
                            - (actual_col * num_rows)
                        ]
                        .ports["o1"]
                        .x
                        - move_x,
                    )
                    cross_matrix_mirror_array.append(cross_matrix_mirror)

        # For every crossing matrix in one stage, creates all the optical connections
        for n in range(int(len(cross_matrices))):
            # Reference of the top puc of the stage "s" to center the crossing matrix
            ref1 = int((num_rows * s) + n * num_rows / 2**s)
            # Reference of the bottom puc of the stage "s" to center the crossing matrix
            ref2 = int((num_rows * s) + n * num_rows / 2**s + num_rows / 2**s - 1)

            # Reference of the top/bottom puc of the stage "s" to center the crossing matrix
            ref3 = int(
                (num_columns * num_rows + (extra_stages + 1) * num_rows - 1) - ref2
            )
            ref4 = int(
                (num_columns * num_rows + (extra_stages + 1) * num_rows - 1) - ref1
            )

            # for connecting the left ports of the crossing matrix to the
            # row of PUCs
            cross_in_counter = 1
            ports_in_left = [0] * (ref2 - ref1) * 2
            ports_out_left = [0] * (ref2 - ref1) * 2

            ports_in_right_2 = [0] * (ref2 - ref1) * 2
            ports_out_right_2 = [0] * (ref2 - ref1) * 2
            # Number of the port ("o" + #) for connecting the right ports of the
            # crossing matrix to the row of PUCs
            cross_out_counter = (ref2 - ref1) * 4
            ports_in_right = [0] * (ref2 - ref1) * 2
            ports_out_right = [0] * (ref2 - ref1) * 2

            ports_in_left_2 = [0] * (ref2 - ref1) * 2
            ports_out_left_2 = [0] * (ref2 - ref1) * 2

            dif_refs = ref2 - ref1
            for i in range(dif_refs + 1):
                if i == 0:
                    ports_in_left[i] = pucs[ref1].ports["o4"]
                    ports_out_left[i] = cross_matrices[n].ports["o1"]
                    cross_in_counter = cross_in_counter + 1

                    ports_in_right[i] = pucs[ref1 + i + num_rows].ports["o1"]
                    ports_out_right[i] = cross_matrices[n].ports[
                        "o" + str(int(cross_out_counter))
                    ]

                    cross_out_counter = cross_out_counter - 1

                elif i == (dif_refs):
                    ports_in_left[2 * i - 1] = pucs[ref1 + i].ports["o3"]
                    ports_out_left[2 * i - 1] = cross_matrices[n].ports[
                        "o" + str(int(cross_in_counter))
                    ]

                    ports_in_right[2 * i - 1] = pucs[ref1 + i + num_rows].ports["o2"]
                    ports_out_right[2 * i - 1] = cross_matrices[n].ports[
                        "o" + str(int(cross_out_counter))
                    ]

                else:
                    ports_in_left[2 * i - 1] = pucs[ref1 + i].ports["o3"]
                    ports_in_left[2 * i] = pucs[ref1 + i].ports["o4"]

                    ports_out_left[2 * i - 1] = cross_matrices[n].ports[
                        "o" + str(int(cross_in_counter))
                    ]
                    ports_out_left[2 * i] = cross_matrices[n].ports[
                        "o" + str(int(cross_in_counter + 1))
                    ]

                    cross_in_counter = cross_in_counter + 2

                    ports_in_right[2 * i - 1] = pucs[ref1 + i + num_rows].ports["o2"]
                    ports_in_right[2 * i] = pucs[ref1 + i + num_rows].ports["o1"]

                    ports_out_right[2 * i - 1] = cross_matrices[n].ports[
                        "o" + str(int(cross_out_counter))
                    ]
                    ports_out_right[2 * i] = cross_matrices[n].ports[
                        "o" + str(int(cross_out_counter - 1))
                    ]

                    cross_out_counter = cross_out_counter - 2

            # Creates the routes of the left side of the crossing (left side of
            # the mesh)
            for nn in range(len(ports_in_left)):
                if order_cross_matrices[s] <= th:
                    if nn < len(ports_in_left) / 2:
                        length = (len(ports_in_left) / 2 - 1 - nn) * (
                            optical_routing_spacing + width
                        )
                    else:
                        length = (optical_routing_spacing + width) * (
                            nn - len(ports_in_left) / 2
                        )
                    end_length = 0
                else:
                    length = (
                        (optical_routing_spacing + width) * (nn - 1) if nn > 0 else 0
                    )
                    end_length = 10 if nn % 2 == 0 else 1
                ipr.get_route_wide(
                    c,
                    ports_in_left[nn],
                    ports_out_left[nn],
                    cross_section=gf.get_cross_section(cross_section),
                    bend=bend,
                    taper=taper,
                    auto_taper=False,
                    start_straight_length=length,
                    allow_width_mismatch=True,
                    end_straight_length=end_length,
                )

            # Creates the routes of the right side of the crossing (left side of
            # the mesh)
            for nn in range(len(ports_in_right)):
                if order_cross_matrices[s] <= th:
                    if nn < len(ports_in_right) / 2:
                        length = (len(ports_in_right) / 2 - 1 - nn) * (
                            optical_routing_spacing + width
                        )
                    else:
                        length = (optical_routing_spacing + width) * (
                            nn - len(ports_in_right) / 2
                        )
                else:
                    length = 0
                ipr.get_route_wide(
                    c,
                    ports_in_right[nn],
                    ports_out_right[nn],
                    cross_section=cross_section,
                    bend=bend,
                    taper=taper,
                    auto_taper=False,
                    start_straight_length=length,
                    allow_width_mismatch=True,
                )
            if s < extra_stages:
                if order_cross_matrices[s] <= th:
                    cross_in_counter = 1
                    cross_out_counter = (ref2 - ref1) * 4
                else:
                    cross_in_counter = (ref2 - ref1) * 2
                    cross_out_counter = (ref2 - ref1) * 2 + 1

                for i in range(dif_refs + 1):
                    if i == 0:
                        ports_in_right_2[i] = pucs[ref3].ports["o1"]
                        ports_in_left_2[i] = pucs[ref3 - i - num_rows].ports["o4"]
                        if order_cross_matrices[s] <= th:
                            ports_out_right_2[i] = cross_matrix_mirror_array[
                                len(cross_matrix_mirror_array) - 1 - n
                            ].ports["o1"]
                            ports_out_left_2[i] = cross_matrix_mirror_array[
                                len(cross_matrix_mirror_array) - 1 - n
                            ].ports["o" + str(int(cross_out_counter))]

                            cross_in_counter = cross_in_counter + 1
                            cross_out_counter = cross_out_counter - 1
                        else:
                            ports_out_right_2[i] = cross_matrix_mirror_array[
                                len(cross_matrix_mirror_array) - 1 - n
                            ].ports["o" + str(int(cross_in_counter))]
                            ports_out_left_2[i] = cross_matrix_mirror_array[
                                len(cross_matrix_mirror_array) - 1 - n
                            ].ports["o" + str(int(cross_out_counter))]
                            cross_in_counter = cross_in_counter - 1
                            cross_out_counter = cross_out_counter + 1

                    elif i == (dif_refs):
                        ports_in_right_2[2 * i - 1] = pucs[ref3 + i].ports["o2"]
                        if order_cross_matrices[s] <= th:
                            ports_out_right_2[2 * i - 1] = cross_matrix_mirror_array[
                                len(cross_matrix_mirror_array) - 1 - n
                            ].ports["o" + str(int(cross_in_counter))]
                        else:
                            ports_out_right_2[2 * i - 1] = cross_matrix_mirror_array[
                                len(cross_matrix_mirror_array) - 1 - n
                            ].ports["o1"]

                        ports_in_left_2[2 * i - 1] = pucs[ref3 + i - num_rows].ports[
                            "o3"
                        ]
                        ports_out_left_2[2 * i - 1] = cross_matrix_mirror_array[
                            len(cross_matrix_mirror_array) - 1 - n
                        ].ports["o" + str(int(cross_out_counter))]

                    else:
                        ports_in_right_2[2 * i - 1] = pucs[ref3 + i].ports["o2"]
                        ports_in_right_2[2 * i] = pucs[ref3 + i].ports["o1"]

                        ports_in_left_2[2 * i - 1] = pucs[ref3 + i - num_rows].ports[
                            "o3"
                        ]
                        ports_in_left_2[2 * i] = pucs[ref3 + i - num_rows].ports["o4"]

                        if order_cross_matrices[s] <= th:
                            ports_out_right_2[2 * i - 1] = cross_matrix_mirror_array[
                                len(cross_matrix_mirror_array) - 1 - n
                            ].ports["o" + str(int(cross_in_counter))]
                            ports_out_right_2[2 * i] = cross_matrix_mirror_array[
                                len(cross_matrix_mirror_array) - 1 - n
                            ].ports["o" + str(int(cross_in_counter + 1))]

                            ports_out_left_2[2 * i - 1] = cross_matrix_mirror_array[
                                len(cross_matrix_mirror_array) - 1 - n
                            ].ports["o" + str(int(cross_out_counter))]
                            ports_out_left_2[2 * i] = cross_matrix_mirror_array[
                                len(cross_matrix_mirror_array) - 1 - n
                            ].ports["o" + str(int(cross_out_counter - 1))]

                            cross_in_counter = cross_in_counter + 2
                            cross_out_counter = cross_out_counter - 2
                        else:
                            ports_out_right_2[2 * i - 1] = cross_matrix_mirror_array[
                                len(cross_matrix_mirror_array) - 1 - n
                            ].ports["o" + str(int(cross_in_counter))]
                            ports_out_right_2[2 * i] = cross_matrix_mirror_array[
                                len(cross_matrix_mirror_array) - 1 - n
                            ].ports["o" + str(int(cross_in_counter - 1))]

                            ports_out_left_2[2 * i - 1] = cross_matrix_mirror_array[
                                len(cross_matrix_mirror_array) - 1 - n
                            ].ports["o" + str(int(cross_out_counter))]
                            ports_out_left_2[2 * i] = cross_matrix_mirror_array[
                                len(cross_matrix_mirror_array) - 1 - n
                            ].ports["o" + str(int(cross_out_counter + 1))]
                            cross_in_counter = cross_in_counter - 2
                            cross_out_counter = cross_out_counter + 2

                # Creates the routes of the right side of the crossing (right side
                # of the mesh)
                for nn in range(len(ports_in_right_2)):
                    if order_cross_matrices[s] <= th:
                        if nn < len(ports_in_right_2) / 2:
                            length = (len(ports_in_right_2) / 2 - 1 - nn) * (
                                optical_routing_spacing + width
                            )
                        else:
                            length = (optical_routing_spacing + width) * (
                                nn - len(ports_in_right_2) / 2
                            )
                        end_length = 0
                    else:
                        length = (
                            (len(ports_in_right_2) - 2 - nn)
                            * (optical_routing_spacing + width)
                            if nn < len(ports_in_right_2) - 1
                            else 0
                        )
                        end_length = 10 if nn % 2 == 1 and nn > 0 else 1

                    ipr.get_route_wide(
                        c,
                        ports_in_right_2[nn],
                        ports_out_right_2[nn],
                        cross_section=cross_section,
                        start_straight_length=length,
                        bend=bend,
                        taper=taper,
                        allow_width_mismatch=True,
                        end_straight_length=end_length,
                    )

                # Creates the routes of the left side of the crossing (right side of
                # the mesh)
                for nn in range(len(ports_in_left_2)):
                    if order_cross_matrices[s] <= th:
                        if nn < len(ports_in_left_2) / 2:
                            length = (len(ports_in_left_2) / 2 - 1 - nn) * (
                                optical_routing_spacing + width
                            )
                        else:
                            length = (optical_routing_spacing + width) * (
                                nn - len(ports_in_left_2) / 2
                            )
                    else:
                        length = 0
                    ipr.get_route_wide(
                        c,
                        ports_in_left_2[nn],
                        ports_out_left_2[nn],
                        cross_section=cross_section,
                        start_straight_length=length,
                        bend=bend,
                        taper=taper,
                        allow_width_mismatch=True,
                    )

            # Straight connections of the PUCs (left side of the mesh)
            port_puc_left = [0] * 2
            port_puc_right = [0] * 2
            port_puc_left[0] = pucs[ref1].ports["o3"]
            port_puc_right[0] = pucs[ref1 + num_rows].ports["o2"]

            port_puc_left[1] = pucs[ref2].ports["o4"]
            port_puc_right[1] = pucs[ref2 + num_rows].ports["o1"]
            # Creates the routes of the top and bottom straight connections of PUCs
            for nn in range(2):
                ipr.get_route_wide(
                    c,
                    port_puc_left[nn],
                    port_puc_right[nn],
                    cross_section=cross_section,
                    bend=bend,
                    taper=taper,
                    allow_width_mismatch=True,
                )

            if s < extra_stages:
                # Straight connections of the PUCs (right section of the mesh)
                port_puc_left_2 = [0] * 2
                port_puc_right_2 = [0] * 2
                port_puc_left_2[0] = pucs[ref3 - num_rows].ports["o3"]
                port_puc_right_2[0] = pucs[ref3].ports["o2"]

                port_puc_left_2[1] = pucs[ref4 - num_rows].ports["o4"]
                port_puc_right_2[1] = pucs[ref4].ports["o1"]
                # Creates the routes of the top and bottom straight connections of PUCs
                for nn in range(2):
                    ipr.get_route_wide(
                        c,
                        port_puc_left_2[nn],
                        port_puc_right_2[nn],
                        cross_section=cross_section,
                        bend=bend,
                        taper=taper,
                        allow_width_mismatch=True,
                    )

        order_cross_matrix = order_cross_matrix / 2.0
        actual_col = actual_col + 1

    # MESH PORT ASSIGNMENT

    # Optical

    # Only first and last row PUCs are external connections of the mesh
    num_port = 1
    for o in range(num_rows):
        c.add_port(f"o{num_port}", port=pucs[o].ports["o2"])
        c.add_port(f"o{num_port + 1}", port=pucs[o].ports["o1"])
        c.add_port(
            f"o{2 * num_rows + num_port}",
            port=pucs[num_pucs - num_rows + o].ports["o3"],
        )
        c.add_port(
            f"o{2 * num_rows + num_port + 1}",
            port=pucs[num_pucs - num_rows + o].ports["o4"],
        )
        num_port = num_port + 2

    # Electrical

    for i in range(num_pucs):
        c.add_port(
            f"puc{i}_top_e1",
            port=pucs[i].ports["e1"],
        )
        c.add_port(
            f"puc{i}_top_e2",
            port=pucs[i].ports["e2"],
        )
        c.add_port(
            f"puc{i}_bot_e4",
            port=pucs[i].ports["e4"],
        )
        c.add_port(
            f"puc{i}_bot_e3",
            port=pucs[i].ports["e3"],
        )

    return c
