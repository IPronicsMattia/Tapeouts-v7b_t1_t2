import math
import sys
import warnings

import gdsfactory as gf
import iprlayout_tower as ipr
from gdsfactory.get_factories import get_cells

from v7b.pdk import (
    bend_modified_hermite,
    phase_shifter_cassette,
    spaced_bend,
    v7b_puc,
)

ipr.crossings_matrix.RANDOM_VALUES = [
    0.0,
    -0.023,
    -0.13,
    0.018,
    0.026,
    -0.07,
    -0.159,
    0.084,
    -0.117,
    0.036,
    -0.078,
    0.017,
    -0.021,
    0.124,
    -0.146,
    0.094,
    0.019,
    0.111,
    0.131,
    -0.039,
    -0.158,
    0.135,
    0.024,
    -0.126,
    0.104,
    0.088,
    -0.111,
    -0.098,
    0.127,
    0.11,
    0.002,
    -0.046,
    0.152,
    -0.081,
    -0.042,
    -0.086,
    0.095,
    0.072,
    0.045,
    0.081,
    -0.001,
    -0.089,
    0.012,
    -0.061,
    0.089,
    -0.163,
    0.003,
    0.059,
    0.126,
    -0.025,
    -0.095,
    0.022,
    -0.112,
    0.07,
    -0.119,
    0.079,
    -0.069,
    0.099,
    -0.127,
    0.009,
    -0.002,
    -0.053,
    -0.157,
]


@gf.cell
def inner_mesh_core(
    puc: gf.Component | gf.partial = None,
    crossing: gf.Component | gf.partial = "crossing",
    crossing_taper: gf.Component = "rib_taper",
    routing_taper: gf.Component = "rib_taper",
    bend: gf.Component = "bend_euler_custom_width",
    order: int = 64,
    extra_stages: int = 3,
    puc_y_sep: float = 0,
    cross_section: gf.CrossSection = "strip",
    wide_cross_section: gf.CrossSection = "strip",
    crossing_cross_section: gf.CrossSection = "strip",
    nitride_cross_section: gf.CrossSection = "nitride2",
    puc_start: int | None = None,
    column_number_step: int | None = None,
    puc_start_block9x9: int | None = None,
    block9x9_number_step: int | None = None,
    puc_start_extra_stage: int | None = None,
    drc_friendly: bool = False,
) -> gf.Component:
    c = gf.Component()
    #############################
    # Cross sections            #
    #############################
    xs = gf.get_cross_section(cross_section)
    xs_w = gf.get_cross_section(wide_cross_section)
    xs_n = gf.get_cross_section(nitride_cross_section)
    xs_cr = gf.get_cross_section(crossing_cross_section)

    #############################
    # Definitions               #
    #############################
    sin_triangle_min_order = 18
    puc_out_sin_crossing_sep = 15.892
    puc_si_crossing_sep = 500.767
    block_9x9_y_separation = 26.35

    #############################
    # Components                #
    #############################
    cross3D = ipr.crossing_3D(
        cross_section1=xs_w,
        cross_section2=xs_n,
        length1=1.5,
        length2=0.93,
        angle=90,
    )
    matrix_kwargs = dict(
        cross_section1=xs_w,
        cross_section2=xs_n,
        crossing=cross3D,
        separation1=43.5,  # Between SiN
        separation2=3.2,  # Between Si
        separation_random1=0,
        separation_random2=0.144,
        n_start_columns=1,
    )
    si_sin_transition = ipr.si_anwg_transition(width_out=2)
    bend_45 = bend_modified_hermite(length_access=0, angle=45)
    routing_taper = gf.get_component(routing_taper)

    #############################
    # Construction              #
    #############################
    ext_x = 0
    pucs = []
    columns = []
    sin_triangles = []
    si_triangles = []
    core_blocks = []
    n_columns = int(math.log2((order * 32) / 9) - 4)

    # Left block connecting to the 9x9's
    for i in range(n_columns):
        current_order = math.ceil(order / 2**i)
        if current_order == 36:
            puc_in_sin_crossing_sep = 287
        else:
            puc_in_sin_crossing_sep = 148
        # PUCs column
        for j in range(order):
            if puc_start:
                puc_ref = c << gf.get_component(
                    puc(puc_number=puc_start + j + column_number_step * i)
                )
            else:
                puc_ref = c << gf.get_component(puc)

            puc_ref.move((puc_ref.xmin, puc_ref.y), (ext_x, puc_y_sep * j))
            pucs.append(puc_ref)

        columns.append(pucs.copy())
        pucs.clear()

        # Triangles for the PUCS
        triangles = math.ceil(order / current_order)
        if triangles == 15:
            triangles += 1
        for j in range(triangles):
            # SIN Triangle
            if current_order >= sin_triangle_min_order:
                triangle = c << ipr.crossing_3D_matrix(
                    **matrix_kwargs,
                    n_crossings=current_order - 1,
                )
                triangle.rotate(-90)
                current_port = current_order * 2 - 2
                triangle.move(
                    (
                        triangle[f"o{current_port}"].x,
                        triangle[f"o{(current_order - 1) * 4 - 1}"].y,
                    ),
                    (
                        columns[i][1]["o3"].x
                        + si_sin_transition.xsize
                        + puc_in_sin_crossing_sep,
                        columns[i][current_order * j + 1]["o2"].y,
                    ),
                )
                ext_x = (
                    triangle[f"o{(current_order - 1) * 4}"].x
                    + si_sin_transition.xsize
                    + puc_out_sin_crossing_sep
                )
                sin_triangles.append(triangle)
            # SI Triangle
            else:
                if current_order == 9:
                    aux = 31.066 if drc_friendly else 31.068
                else:
                    aux = 29
                triangle = ipr.crossings_matrix_d(
                    crossing=crossing,
                    order=current_order * 2,
                    distance=aux,
                    cross_section=xs,
                    custom_bend=bend_45,
                )
                if drc_friendly:
                    for port in triangle.ports:
                        orientation = round(port.orientation)
                        if orientation == 0:
                            port.center = (port.center[0] - 0.001, port.center[1])
                        elif orientation == 90:
                            port.center = (port.center[0], port.center[1] - 0.001)
                        elif orientation == 180:
                            port.center = (port.center[0] + 0.001, port.center[1])
                        elif orientation == 270:
                            port.center = (port.center[0], port.center[1] + 0.001)
                triangle = c << triangle
                triangle.dmirror_x()
                center = (
                    columns[i][current_order * j].y
                    - (
                        columns[i][current_order * j].y
                        - columns[i][current_order * (j + 1) - 1].y
                    )
                    / 2
                )
                triangle.move(
                    (
                        triangle.xmin,
                        triangle.y,
                    ),
                    (
                        columns[i][0]["o4"].x + current_order * 4,
                        center,
                    ),
                )
                ext_x = triangle[f"o{current_order * 3 - 2}"].x + puc_si_crossing_sep
                si_triangles.append(triangle)
    # 9x9's block creation
    block = gf.partial(
        block_9x9,
        puc=puc,
        crossing=crossing,
        x_separation=98,
        y_separation=block_9x9_y_separation,
        block_x_separation=378,
        block_y_separation=block_9x9_y_separation,
        routing_taper=routing_taper,
        crossing_taper=crossing_taper,
        routing_bend=bend,
        crossing_cross_section=xs_cr,
        cross_section=xs,
        puc_numbers=None,
        drc_friendly=drc_friendly,
    )
    if puc_start is None:
        block = gf.get_component(block)

    for i in range(order * 2 // 9):
        if puc_start:
            start_values = []
            for j in range(6):
                if j < 3:
                    start_values.append(
                        puc_start_block9x9 + block9x9_number_step * j + 3 * i
                    )
                else:
                    start_values.append(
                        puc_start_block9x9 + block9x9_number_step * j + 3 * i - 3
                    )
            block_ref = c << gf.get_component(block(puc_numbers=start_values))
        else:
            block_ref = c << block

        block_ref.move(
            (block_ref.xmin, block_ref.ymax),
            (
                triangle.xmax + puc_si_crossing_sep,
                columns[0][0].ymax - (block_ref.ysize + block_9x9_y_separation) * i,
            ),
        )
        core_blocks.append(block_ref)
    ext_x = block_ref.xmax

    # Right block connecting to the 9x9's
    if extra_stages != 0:
        current_order = order // 2 ** (extra_stages - 1)

    extra_triangles = []
    extra_pucs = []
    for i in range(extra_stages):
        if current_order == 36:
            puc_in_sin_crossing_sep = 287
        else:
            puc_in_sin_crossing_sep = 374
        for j in range(order // current_order):
            if current_order >= sin_triangle_min_order:
                triangle = c << ipr.crossing_3D_matrix(
                    **matrix_kwargs,
                    n_crossings=current_order - 1,
                )
                triangle.rotate(90)
                triangle.move(
                    (
                        triangle[f"o{(current_order - 1) * 4}"].x,
                        triangle[f"o{(current_order - 1) * 4 - 1}"].y,
                    ),
                    (
                        ext_x + si_sin_transition.xsize + puc_out_sin_crossing_sep,
                        columns[0][current_order * (j + 1) - 2]["o4"].y,
                    ),
                )
            else:
                if current_order == 9:
                    aux = 31.026
                else:
                    aux = 29
                triangle = c << ipr.crossings_matrix_d(
                    crossing=crossing,
                    order=current_order * 2,
                    distance=aux,
                    cross_section=xs,
                    custom_bend=bend_45,
                )
                center = (
                    columns[0][current_order * j].y
                    - (
                        columns[0][current_order * j].y
                        - columns[0][current_order * (j + 1) - 1].y
                    )
                    / 2
                )
                triangle.move(
                    (
                        triangle.xmin,
                        triangle.y,
                    ),
                    (
                        ext_x + puc_si_crossing_sep,
                        center,
                    ),
                )
            extra_triangles.append(triangle)

        if current_order >= sin_triangle_min_order:
            ext_x = triangle[f"o{(current_order - 1) * 2}"].x
        else:
            ext_x = triangle[f"o{(current_order - 1) * 2}"].x + current_order * 4

        for j in range(order):
            if puc_start_extra_stage:
                puc_ref = c << gf.get_component(
                    puc(puc_number=puc_start_extra_stage + j + column_number_step * (i))
                )
            else:
                puc_ref = c << gf.get_component(puc)
            if current_order < sin_triangle_min_order:
                puc_ref.move(
                    (puc_ref.xmin, puc_ref.y),
                    (ext_x + puc_si_crossing_sep, puc_y_sep * j),
                )
            else:
                puc_ref.move(
                    (puc_ref.xmin, puc_ref.y),
                    (
                        si_sin_transition.xsize + ext_x + puc_in_sin_crossing_sep,
                        puc_y_sep * j,
                    ),
                )

            pucs.append(puc_ref)

        extra_pucs.append(pucs.copy())
        pucs.clear()

        ext_x = puc_ref["o4"].x
        current_order *= 2

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="No registered width taper")
        mesh_nitride_routing(
            c,
            order,
            columns,
            extra_pucs,
            sin_triangles,
            extra_triangles,
            core_blocks,
            sin_triangle_min_order,
            si_sin_transition,
            routing_taper,
            bend,
            xs_n,
            xs_w,
            xs,
        )

        mesh_silicon_routing(
            c,
            columns,
            extra_pucs,
            si_triangles,
            extra_triangles,
            core_blocks,
            routing_taper,
            bend,
            order,
            sin_triangle_min_order,
        )

    for i in range(order):
        c.add_port(f"o{1 + i * 2}", port=columns[0][i]["o2"])
        c.add_port(f"o{2 + i * 2}", port=columns[0][i]["o1"])
        if len(extra_pucs):
            c.add_port(
                f"o{order * 2 + 1 + i * 2}", port=extra_pucs[-1][order - 1 - i]["o4"]
            )
            c.add_port(
                f"o{order * 2 + 2 + i * 2}", port=extra_pucs[-1][order - 1 - i]["o3"]
            )

    return c


@gf.cell
def mesh_72x72(
    core: gf.partial,
    puc: gf.partial,
    bend: gf.Component,
    routing_taper: gf.Component,
    cross_section: gf.CrossSection,
    wide_cross_section: gf.CrossSection,
    nitride_cross_section: gf.CrossSection,
    numbered: bool,
) -> gf.Component:
    c = gf.Component()

    #############################
    # Cross sections            #
    #############################
    xs = gf.get_cross_section(cross_section)
    xs_w = gf.get_cross_section(wide_cross_section)
    xs_n = gf.get_cross_section(nitride_cross_section)

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
    matrix_kwargs = dict(
        cross_section1=xs_w,
        cross_section2=xs_n,
        crossing=cross3D,
        separation2=3.2,  # Between Si
        separation_random1=0,
        separation_random2=0.144,
        n_start_columns=1,
    )

    absorber = ipr.rib_absorber(cross_section=xs)
    photodetector = gf.partial(
        ipr.lateral_pd,
        ge_length=14,
        ge_width=3,
        dop_plusplus_ge_separation=0.3,
        metal2_via_n=3,
        forward_pin=True,
        cross_section=xs,
    )
    si_sin_transition = ipr.si_anwg_transition(width_out=2)
    aux_bend = ipr.bend_with_taper(bend, routing_taper)
    if not numbered:
        puc = gf.get_component(puc)
        core = gf.get_component(core)
        photodetector = gf.get_component(photodetector)

    #############################
    # Helpers                   #
    #############################
    _steps_rb_kw = dict(
        cross_section="strip",
        bend=aux_bend,
        route_width=0.93,
        sort_ports=True,
        steps=[
            {"dy": -600, "dx": 549.869},
            {"dy": -1000},
        ],
        start_straight_length=90,
    )
    _rb_kw = dict(
        bend=bend,
        taper=routing_taper,
        min_straight_taper=1,
        route_width=0.41,
        cross_section="strip",
    )
    _aux_rb_kw = dict(
        cross_section="strip",
        bend=aux_bend,
        route_width=0.93,
        sort_ports=True,
    )

    def _rb(frm, to, separation=None, rb_kw=_rb_kw):
        kw = {
            **rb_kw,
            **({"separation": separation} if separation is not None else {}),
        }
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="No registered width taper")
            gf.routing.route_bundle(c, frm, to, **kw)

    def _route_each(outputs, inputs):
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="No registered width taper")
            for k, comp in enumerate(outputs):
                gf.routing.route_bundle(c, [comp], [inputs[k]], **_rb_kw)

    def _triangle_inputs(tri, mirror):
        ports = []
        for j in range(71):
            st = c << gf.c.straight(1, cross_section=xs_w)
            st.connect("o1", tri[f"o{1 + 2 * j}"])
            tran = c << routing_taper
            tran.connect("o2", st["o2"])
            bnd = c << bend
            bnd.connect("o1", tran["o1"], mirror=mirror)
            ports.append(bnd["o2"])
            st = c << gf.c.straight(1, cross_section=xs_n)
            st.connect("o1", tri[f"o{2 + 2 * j}"])
            tran = c << si_sin_transition
            tran.connect("o2", st["o2"])
            ports.append(tran["o1"])
        return ports

    def _triangle_si_outputs(tri):
        ports = []
        for j in range(71):
            st = c << gf.c.straight(1, cross_section=xs_w)
            st.connect("o1", tri[f"o{143 + j}"])
            ports.append(st["o2"])
        return ports

    def _triangle_sin_outputs(tri):
        ports = []
        for j in range(71):
            st = c << gf.c.straight(1, cross_section=xs_n)
            st.connect("o1", tri[f"o{214 + j}"])
            tran = c << si_sin_transition
            tran.connect("o2", st["o2"])
            ports.append(tran["o1"])
        return ports

    #############################
    # Construction              #
    #############################
    # Inner Cores
    cores = []
    for i in range(6):
        if numbered:
            core_ref = c << gf.get_component(
                core(
                    puc_start=360 + 36 * i,
                    puc_start_block9x9=1008 + 24 * i,
                    puc_start_extra_stage=1872 + 36 * i,
                )
            )
        else:
            core_ref = c << core
        core_ref.move(
            (core_ref.x, core_ref.ymax),
            (0, -(core_ref.ysize + 26.35) * i),
        )
        cores.append(core_ref)

    # 3rd level DEMUX
    demux = []
    demux_to_core = 1133
    demux_to_triangle = 698
    for i in range(6):
        pucs = []
        for j in range(36):
            if numbered:
                puc_ref = c << gf.get_component(puc(puc_number=i * 36 + j + 144))
            else:
                puc_ref = c << puc
            puc_ref.move(
                (puc_ref.xmax, puc_ref["o2"].y),
                (cores[i].xmin - demux_to_core, cores[i][f"o{1 + 2 * j}"].y),
            )
            pucs.append(puc_ref)
            abs_ref = c << absorber
            abs_ref.connect("o1", puc_ref["o1"], mirror=True)
        demux.append(pucs.copy())

    for i in range(3):
        triangle_ref = c << ipr.crossing_3D_matrix(
            **matrix_kwargs,
            separation1=43.5,
            n_crossings=71,
        )
        triangle_ref.rotate(-90)
        triangle_ref.dmove(
            (triangle_ref.xmin, triangle_ref["o283"].y),
            (demux[i * 2][0]["o4"].x + demux_to_triangle, cores[i * 2]["o3"].y),
        )
        inputs = _triangle_inputs(triangle_ref, False)
        outputs = []
        for j in range(2):
            for k in range(36):
                if not (j == 0 and k == 0):
                    outputs.append(demux[j + i * 2][k]["o3"])
                if not (j % 2 == 1 and k == 35):
                    outputs.append(demux[j + i * 2][k]["o4"])
        _rb(outputs, inputs, separation=3.52)

        si_outs = _triangle_si_outputs(triangle_ref)
        core_inputs = []
        for j in range(71):
            tap_ref = c << routing_taper
            tap_ref.connect("o1", cores[i * 2 + 1][f"o{j + 1}"])
            core_inputs.append(tap_ref["o2"])
        core_inputs.reverse()
        _rb(si_outs, core_inputs, separation=3.52, rb_kw=_aux_rb_kw)

        sin_outs = _triangle_sin_outputs(triangle_ref)
        core_inputs = [cores[i * 2][f"o{j + 2}"] for j in range(71)]
        core_inputs.reverse()
        _route_each(sin_outs, core_inputs)

        _rb([demux[i * 2][0]["o3"]], [cores[i * 2]["o1"]], separation=3.52)
        _rb([demux[1 + i * 2][-1]["o4"]], [cores[1 + i * 2]["o72"]], separation=3.52)

    # 2nd Level DEMUX
    demux_to_core = 558
    demux_to_triangle = 134.5
    outputs = []
    for i in range(2):
        pucs = []
        for j in range(36):
            if numbered:
                puc_ref = c << gf.get_component(puc(puc_number=i * 36 + j + 72))
            else:
                puc_ref = c << puc
            puc_ref.move(
                (puc_ref.xmax, puc_ref["o2"].y),
                (demux[0][0].xmin - demux_to_core, cores[i][f"o{1 + 2 * j}"].y),
            )
            abs_ref = c << absorber
            abs_ref.connect("o1", puc_ref["o1"], mirror=True)

            if not (i in [0, 2] and j == 0):
                outputs.append(puc_ref["o3"])
            if not (i % 2 == 1 and j == 35):
                outputs.append(puc_ref["o4"])
            pucs.append(puc_ref)
        demux.append(pucs.copy())
    for i in range(1):
        triangle_ref = c << ipr.crossing_3D_matrix(
            **matrix_kwargs,
            separation1=88.5,
            n_crossings=71,
        )
        triangle_ref.rotate(-90)
        triangle_ref.dmove(
            (triangle_ref.xmin, triangle_ref["o284"].y),
            (demux[-2 + 2 * i][0]["o4"].x + demux_to_triangle, cores[i * 2]["o3"].y),
        )

        _rb([demux[-2 + 2 * i][0]["o3"]], [demux[0 + 2 * i][0]["o2"]], separation=3.52)

        inputs = _triangle_inputs(triangle_ref, False)
        _route_each(outputs[142 * i : 142 * (i + 1)], inputs)

        si_outs = _triangle_si_outputs(triangle_ref)
        inputs = []
        for j in range(2):
            for k in range(36):
                tap_ref = c << routing_taper
                tap_ref.connect("o1", demux[2 + j][k]["o2"])
                inputs.append(tap_ref["o2"])
        inputs.reverse()
        tap_ref = c << routing_taper
        tap_ref.connect("o1", demux[-1][-1]["o4"])
        st_ref = c << gf.c.straight(105.823, cross_section=wide_cross_section)
        st_ref.connect("o1", tap_ref["o2"])
        tap_ref = c << routing_taper
        tap_ref.connect("o2", st_ref["o2"])
        bend_ref = c << bend
        bend_ref.connect("o1", tap_ref["o1"], mirror=True)
        tap_ref = c << routing_taper
        tap_ref.connect("o1", bend_ref["o2"])

        si_outs.insert(0, tap_ref["o2"])
        _rb(si_outs, inputs, separation=3.52, rb_kw=_aux_rb_kw)

        sin_outs = _triangle_sin_outputs(triangle_ref)
        inputs = []
        for j in range(2):
            for k in range(36):
                if not (j == 0 and k == 0):
                    inputs.append(demux[j][k]["o2"])
        inputs.reverse()
        _route_each(sin_outs, inputs)

    # 1st Level DEMUX
    demux_to_core = 558
    demux_to_triangle = 134.5
    outputs = []
    for i in range(2):
        pucs = []
        for j in range(36):
            if numbered:
                puc_ref = c << gf.get_component(puc(puc_number=i * 36 + j))
            else:
                puc_ref = c << puc
            puc_ref.move(
                (puc_ref.xmax, puc_ref["o2"].y),
                (demux[-2][0].xmin - demux_to_core, cores[i][f"o{1 + 2 * j}"].y),
            )
            abs_ref = c << absorber
            abs_ref.connect("o1", puc_ref["o2"])

            if not (i == 0 and j == 0):
                outputs.append(puc_ref["o3"])
            if not (i % 2 == 1 and j == 35):
                outputs.append(puc_ref["o4"])
            pucs.append(puc_ref)
        demux.append(pucs.copy())

    triangle_ref = c << ipr.crossing_3D_matrix(
        **matrix_kwargs,
        separation1=88.5,
        n_crossings=71,
    )
    triangle_ref.rotate(-90)
    triangle_ref.dmove(
        (triangle_ref.xmin, triangle_ref["o284"].y),
        (demux[-1][0]["o4"].x + demux_to_triangle, cores[0]["o3"].y),
    )

    _rb([demux[-2][0]["o3"]], [demux[-4][0]["o2"]], separation=3.52)

    inputs = _triangle_inputs(triangle_ref, False)
    _route_each(outputs, inputs)

    si_outs = _triangle_si_outputs(triangle_ref)
    inputs = []
    tap_ref = c << routing_taper
    tap_ref.connect("o1", demux[-1][-1]["o4"])
    st_ref = c << gf.c.straight(105.823, cross_section=wide_cross_section)
    st_ref.connect("o1", tap_ref["o2"])
    tap_ref = c << routing_taper
    tap_ref.connect("o2", st_ref["o2"])
    bend_ref = c << bend
    bend_ref.connect("o2", tap_ref["o1"])
    tap_ref = c << routing_taper
    tap_ref.connect("o1", bend_ref["o1"])

    si_outs.append(tap_ref["o2"])

    for i in range(2):
        for j in range(36):
            tap_ref = c << routing_taper
            tap_ref.connect("o1", demux[4 + i][j]["o2"])
            inputs.append(tap_ref["o2"])
    _rb(si_outs, inputs, separation=3, rb_kw=_steps_rb_kw)

    sin_outs = _triangle_sin_outputs(triangle_ref)
    inputs = []
    for i in range(2):
        for j in range(36):
            if not (i == 0 and j == 0):
                inputs.append(demux[6 + i][j]["o2"])
    inputs.reverse()
    _route_each(sin_outs, inputs)

    # 3rd level MUX
    mux = []
    mux_to_core = 1143
    mux_to_triangle = 700
    for i in range(6):
        pucs = []
        for j in range(36):
            if numbered:
                puc_ref = c << gf.get_component(puc(puc_number=i * 36 + j + 2304))
            else:
                puc_ref = c << puc
            puc_ref.move(
                (puc_ref.xmin, puc_ref["o2"].y),
                (cores[i].xmax + mux_to_core, cores[i][f"o{1 + 2 * j}"].y),
            )
            pucs.append(puc_ref)
            abs_ref = c << absorber
            abs_ref.connect("o1", puc_ref["o3"], mirror=True)

        mux.append(pucs.copy())

    for i in range(3):
        triangle_ref = c << ipr.crossing_3D_matrix(
            **matrix_kwargs,
            separation1=43.5,
            n_crossings=71,
        )
        triangle_ref.rotate(90)
        triangle_ref.dmove(
            (triangle_ref.xmax, triangle_ref["o283"].y),
            (mux[i * 2 + 1][0]["o1"].x - mux_to_triangle, cores[i * 2 + 1]["o75"].y),
        )

        inputs = _triangle_inputs(triangle_ref, False)
        outputs = []
        for j in range(2):
            for k in range(36):
                if not (j == 0 and k == 0):
                    outputs.append(mux[j + i * 2][k]["o2"])
                if not (j % 2 == 1 and k == 35):
                    outputs.append(mux[j + i * 2][k]["o1"])
        inputs.reverse()
        _rb(outputs, inputs, separation=3.52)

        si_outs = _triangle_si_outputs(triangle_ref)
        core_inputs = []
        for j in range(71):
            tap_ref = c << routing_taper
            tap_ref.connect("o1", cores[i * 2][f"o{j + 73}"])
            core_inputs.append(tap_ref["o2"])
        core_inputs.reverse()
        _rb(si_outs, core_inputs, separation=3.52, rb_kw=_aux_rb_kw)

        sin_outs = _triangle_sin_outputs(triangle_ref)
        core_inputs = [cores[i * 2 + 1][f"o{144 - j}"] for j in range(71)]
        _route_each(sin_outs, core_inputs)

        _rb([mux[i * 2][0]["o2"]], [cores[i * 2]["o144"]], separation=3.52)
        _rb([mux[1 + i * 2][-1]["o1"]], [cores[1 + i * 2]["o73"]], separation=3.52)

    # 2nd Level MUX
    mux_to_core = 558
    mux_to_triangle = 134.5
    outputs = []
    for i in range(2):
        pucs = []
        for j in range(36):
            if numbered:
                puc_ref = c << gf.get_component(puc(puc_number=i * 36 + j + 2520))
            else:
                puc_ref = c << puc
            puc_ref.move(
                (puc_ref.xmin, puc_ref["o2"].y),
                (mux[2][0].xmax + mux_to_core, cores[2 + i][f"o{1 + 2 * j}"].y),
            )
            abs_ref = c << absorber
            abs_ref.connect("o1", puc_ref["o3"], mirror=True)

            if not (i in [0, 2] and j == 0):
                outputs.append(puc_ref["o2"])
            if not (i % 2 == 1 and j == 35):
                outputs.append(puc_ref["o1"])
            pucs.append(puc_ref)
        mux.append(pucs.copy())

    for i in range(1):
        triangle_ref = c << ipr.crossing_3D_matrix(
            **matrix_kwargs,
            separation1=88.5,
            n_crossings=71,
        )
        triangle_ref.rotate(90)
        triangle_ref.dmove(
            (triangle_ref.xmax, triangle_ref["o283"].y),
            (mux[-1][0]["o1"].x - mux_to_triangle, cores[3 + 2 * i]["o77"].y),
        )

        _rb([mux[3 + 2 * i][-1]["o4"]], [mux[-1 + 2 * i][-1]["o1"]], separation=3.52)

        inputs = _triangle_inputs(triangle_ref, False)
        inputs.reverse()
        _route_each(outputs[142 * i : 142 * (i + 1)], inputs)

        si_outs = _triangle_si_outputs(triangle_ref)
        inputs = []

        tap_ref = c << routing_taper
        tap_ref.connect("o1", mux[-2 + i * 2][0]["o2"])
        st_ref = c << gf.c.straight(105.823, cross_section=wide_cross_section)
        st_ref.connect("o1", tap_ref["o2"])
        tap_ref = c << routing_taper
        tap_ref.connect("o2", st_ref["o2"])
        bend_ref = c << bend
        bend_ref.connect("o2", tap_ref["o1"])
        tap_ref = c << routing_taper
        tap_ref.connect("o1", bend_ref["o1"])
        si_outs.insert(0, tap_ref["o2"])

        for j in range(2):
            for k in range(36):
                tap_ref = c << routing_taper
                tap_ref.connect("o1", mux[j][k]["o4"])
                inputs.append(tap_ref["o2"])
        _rb(si_outs, inputs, separation=3.52, rb_kw=_aux_rb_kw)

        sin_outs = _triangle_sin_outputs(triangle_ref)
        inputs = []
        for j in range(2):
            for k in range(36):
                if not (j == 1 and k == 35):
                    inputs.append(mux[2 + i * 2 + j][k]["o4"])
        _route_each(sin_outs, inputs)

    # 1st Level MUX
    mux_to_core = 558
    mux_to_triangle = 134.5
    outputs = []
    for i in range(2):
        pucs = []
        for j in range(36):
            if numbered:
                puc_ref = c << gf.get_component(puc(puc_number=i * 36 + j + 2592))
            else:
                puc_ref = c << puc
            puc_ref.move(
                (puc_ref.xmin, puc_ref["o2"].y),
                (mux[6][0].xmax + mux_to_core, cores[i + 4][f"o{1 + 2 * j}"].y),
            )

            abs_ref = c << absorber
            abs_ref.connect("o1", puc_ref["o4"])

            if not (i == 0 and j == 0):
                outputs.append(puc_ref["o2"])
            if not (i % 2 == 1 and j == 35):
                outputs.append(puc_ref["o1"])
            pucs.append(puc_ref)
        mux.append(pucs.copy())

    triangle_ref = c << ipr.crossing_3D_matrix(
        **matrix_kwargs,
        separation1=88.5,
        n_crossings=71,
    )
    triangle_ref.rotate(90)
    triangle_ref.dmove(
        (triangle_ref.xmax, triangle_ref["o283"].y),
        (mux[-1][0]["o1"].x - mux_to_triangle, cores[5]["o77"].y),
    )

    _rb([mux[5][-1]["o4"]], [mux[-1][-1]["o1"]], separation=3.52)

    inputs = _triangle_inputs(triangle_ref, False)
    inputs.reverse()
    _route_each(outputs, inputs)

    si_outs = _triangle_si_outputs(triangle_ref)
    inputs = []

    tap_ref = c << routing_taper
    tap_ref.connect("o1", mux[-2][0]["o2"])
    st_ref = c << gf.c.straight(105.823, cross_section=wide_cross_section)
    st_ref.connect("o1", tap_ref["o2"])
    tap_ref = c << routing_taper
    tap_ref.connect("o2", st_ref["o2"])
    bend_ref = c << bend
    bend_ref.connect("o2", tap_ref["o1"])
    tap_ref = c << routing_taper
    tap_ref.connect("o1", bend_ref["o1"])
    si_outs.insert(0, tap_ref["o2"])

    for i in range(2):
        for j in range(36):
            tap_ref = c << routing_taper
            tap_ref.connect("o1", mux[-4 + i][j]["o4"])
            inputs.append(tap_ref["o2"])

    _rb(si_outs, inputs, separation=3.52, rb_kw=_aux_rb_kw)

    sin_outs = _triangle_sin_outputs(triangle_ref)
    inputs = []
    for i in range(2):
        for j in range(36):
            if not (i == 1 and j == 35):
                inputs.append(mux[4 + i][j]["o4"])
    _route_each(sin_outs, inputs)

    for i in range(36):
        c.add_port(f"o{1 + i}", port=demux[-2][i]["o1"])
        c.add_port(f"o{37 + i}", port=demux[-1][i]["o1"])
        c.add_port(f"o{144 - i}", port=mux[-2][i]["o3"])
        c.add_port(f"o{108 - i}", port=mux[-1][i]["o3"])

    return c


def mesh_nitride_routing(
    c: gf.Component,
    order: int,
    pucs: list,
    extra_pucs: list,
    triangles: list,
    extra_triangles: list,
    core_blocks: list,
    sin_triangle_min_order: int,
    sin_transition: gf.Component,
    routing_taper: gf.Component,
    routing_bend: gf.Component,
    nitride_cross_section: gf.CrossSection,
    wide_cross_section: gf.CrossSection,
    cross_section: gf.CrossSection,
):
    def _rb(frm, to, separation=None):
        kw = dict(
            bend=routing_bend,
            taper=routing_taper,
            min_straight_taper=1,
            route_width=0.41,
            cross_section="strip",
        )
        if separation is not None:
            kw["separation"] = separation
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="No registered width taper")
            gf.routing.route_bundle(c, frm, to, **kw)

    aux_bend = ipr.bend_with_taper(routing_bend, routing_taper)

    # Left block: pucs[i] ↔ triangles ↔ pucs[i+1]
    repetitions = int(math.log2((order * 2) // sin_triangle_min_order))
    current_order = order
    current_triangle = 0

    for i in range(repetitions):
        n_triangles = order // current_order

        for j in range(n_triangles):
            triangle_in = []
            triangle_si_out = []
            triangle_sin_out = []
            row = current_order * j

            for k in range((current_order - 1) * 2):
                port_idx = 1 + 2 * k if k < current_order - 1 else current_order + k
                st_ref = c << gf.c.straight(1, cross_section=wide_cross_section)
                st_ref.connect("o1", triangles[current_triangle][f"o{port_idx}"])
                if k < current_order - 1:
                    tap_ref = c << routing_taper
                    tap_ref.connect("o2", st_ref["o2"])
                    bend_ref = c << routing_bend
                    bend_ref.connect("o1", tap_ref["o1"])
                    triangle_in.append(bend_ref["o2"])
                else:
                    triangle_si_out.append(st_ref["o2"])

                port_idx = (
                    2 + 2 * k if k < current_order - 1 else current_order * 2 + k - 1
                )
                st_ref = c << gf.c.straight(1, width=2, cross_section="nitride2")
                st_ref.connect("o1", triangles[current_triangle][f"o{port_idx}"])
                tran_ref = c << sin_transition
                tran_ref.connect("o2", st_ref["o2"])
                if k < current_order - 1:
                    triangle_in.append(tran_ref["o1"])
                else:
                    triangle_sin_out.append(tran_ref["o1"])

            current_triangle += 1

            _rb([pucs[i][row]["o3"]], [pucs[i + 1][row]["o2"]])
            _rb(
                [pucs[i][row + current_order - 1]["o4"]],
                [pucs[i + 1][row + current_order - 1]["o1"]],
            )

            puc_out = []
            for k in range(current_order):
                if k != 0:
                    puc_out.append(pucs[i][k + row]["o3"])
                if k != current_order - 1:
                    puc_out.append(pucs[i][k + row]["o4"])
            _rb(puc_out, triangle_in, separation=3.52)

            puc_in = []
            for k in range(current_order // 2):
                if k != 0:
                    puc_in.append(pucs[i + 1][k + row]["o2"])
                puc_in.append(pucs[i + 1][k + row]["o1"])
            puc_in.reverse()
            for k, comp in enumerate(puc_in):
                gf.routing.route_single(
                    c,
                    comp,
                    triangle_sin_out[k],
                    bend=routing_bend,
                    cross_section=cross_section,
                )

            puc_in = []
            for k in range(current_order // 2):
                tap_ref = c << routing_taper
                tap_ref.connect("o1", pucs[i + 1][k + row + current_order // 2]["o2"])
                puc_in.append(tap_ref["o2"])
                if k != current_order // 2 - 1:
                    tap_ref = c << routing_taper
                    tap_ref.connect(
                        "o1", pucs[i + 1][k + row + current_order // 2]["o1"]
                    )
                    puc_in.append(tap_ref["o2"])
            puc_in.reverse()

            gf.routing.route_bundle(
                c,
                puc_in,
                triangle_si_out,
                bend=aux_bend,
                route_width=0.93,
                cross_section="strip",
                separation=3,
            )

        current_order //= 2

    if not extra_pucs:
        return

    local_extra_pucs = extra_pucs.copy()
    current_order = order // 2 ** (len(extra_pucs) - 1)
    n_triangles = order // current_order
    current_triangle = 0

    aux = [
        core_blocks[i][f"o{10 + j}"] for i in range(len(core_blocks)) for j in range(9)
    ]
    local_extra_pucs.insert(0, aux)

    # Right block: local_extra_pucs[i] ↔ extra_triangles ↔ local_extra_pucs[i+1]
    for i in range(len(local_extra_pucs)):
        for j in range(n_triangles):
            if current_order >= sin_triangle_min_order:
                tri = extra_triangles[current_triangle]
                row = current_order * j

                # Si inputs to triangle
                tri_in_si = []
                for k in range(current_order - 1):
                    st_ref = c << gf.c.straight(1, cross_section=wide_cross_section)
                    st_ref.connect("o1", tri[f"o{(current_order - 1) * 2 + 1 + k}"])
                    tri_in_si.append(st_ref["o2"])

                if i == 0:
                    for k in range(current_order - 1):
                        tap_ref = c << routing_taper
                        tap_ref.connect("o1", local_extra_pucs[0][k + 1 + row * 2])
                        gf.routing.route_bundle(
                            c,
                            [tap_ref["o2"]],
                            [tri_in_si[k]],
                            bend=aux_bend,
                            route_width=0.93,
                            cross_section="strip",
                            separation=3,
                        )
                else:
                    puc_out = []
                    for k in range(current_order // 2):
                        if k != 0:
                            tap_ref = c << routing_taper
                            tap_ref.connect("o1", local_extra_pucs[i][k + row]["o3"])
                            puc_out.append(tap_ref["o2"])
                        tap_ref = c << routing_taper
                        tap_ref.connect("o1", local_extra_pucs[i][k + row]["o4"])
                        puc_out.append(tap_ref["o2"])
                    gf.routing.route_bundle(
                        c,
                        puc_out,
                        tri_in_si,
                        bend=aux_bend,
                        route_width=0.93,
                        cross_section="strip",
                        separation=3,
                    )

                # SiN inputs to triangle
                tri_in_sin = []
                for k in range(current_order - 1):
                    st_ref = c << gf.c.straight(1, cross_section=nitride_cross_section)
                    st_ref.connect("o1", tri[f"o{(current_order - 1) * 3 + 1 + k}"])
                    tran_ref = c << sin_transition
                    tran_ref.connect("o2", st_ref["o2"])
                    tri_in_sin.append(tran_ref["o1"])

                if i == 0:
                    for k in range(current_order - 1):
                        _rb(
                            [tri_in_sin[k]],
                            [local_extra_pucs[0][k + current_order + row * 2]],
                            separation=3,
                        )
                else:
                    puc_out = []
                    for k in range(current_order // 2):
                        puc_out.append(
                            local_extra_pucs[i][k + current_order // 2 + row]["o3"]
                        )
                        if k != current_order // 2 - 1:
                            puc_out.append(
                                local_extra_pucs[i][k + current_order // 2 + row]["o4"]
                            )
                    for k, comp in enumerate(puc_out):
                        gf.routing.route_single(
                            c,
                            comp,
                            tri_in_sin[k],
                            bend=routing_bend,
                            cross_section=cross_section,
                        )

                # Triangle outputs to next PUC column
                tri_out = []
                for k in range((current_order - 1) * 2):
                    port_name = f"o{(current_order - 1) * 2 - k}"
                    if k % 2 != 0:
                        if k == (current_order - 1) * 2 - 1:
                            st_ref = c << gf.c.straight(
                                22.44, cross_section=wide_cross_section
                            )
                        else:
                            st_ref = c << gf.c.straight(
                                1, cross_section=wide_cross_section
                            )
                        st_ref.connect("o1", tri[port_name])
                        tran_ref = c << routing_taper
                        tran_ref.connect("o2", st_ref["o2"])
                        bend_ref = c << routing_bend
                        bend_ref.connect("o1", tran_ref["o1"])
                        tri_out.append(bend_ref["o2"])
                    else:
                        st_ref = c << gf.c.straight(
                            1, cross_section=nitride_cross_section
                        )
                        st_ref.connect("o1", tri[port_name])
                        tran_ref = c << sin_transition
                        tran_ref.connect("o2", st_ref["o2"])
                        tri_out.append(tran_ref["o1"])

                puc_in = []
                for k in range(current_order):
                    if k != 0:
                        puc_in.append(local_extra_pucs[i + 1][k + row]["o2"])
                    if k != current_order - 1:
                        puc_in.append(local_extra_pucs[i + 1][k + row]["o1"])
                _rb(tri_out, puc_in, separation=3.52)

                # Edge (top/bottom) connections bypassing the triangle
                if i == 0:
                    _rb(
                        [local_extra_pucs[0][row * 2]],
                        [local_extra_pucs[1][row]["o2"]],
                        separation=3,
                    )
                    _rb(
                        [local_extra_pucs[1][(j + 1) * current_order - 1]["o1"]],
                        [local_extra_pucs[0][(j + 1) * current_order * 2 - 1]],
                        separation=3,
                    )
                else:
                    _rb(
                        [local_extra_pucs[i][row]["o3"]],
                        [local_extra_pucs[i + 1][row]["o2"]],
                        separation=3,
                    )
                    _rb(
                        [local_extra_pucs[i][(j + 1) * current_order - 1]["o4"]],
                        [local_extra_pucs[i + 1][(j + 1) * current_order - 1]["o1"]],
                        separation=3,
                    )

                current_triangle += 1
            else:
                current_triangle += 1

        current_order *= 2
        n_triangles //= 2


def mesh_silicon_routing(
    c: gf.Component,
    pucs: list,
    extra_pucs: list,
    triangles: list,
    extra_triangles: list,
    core_blocks: list,
    routing_taper: gf.Component,
    routing_bend: gf.Component,
    order: int,
    sin_triangle_min_order: int,
):
    current_triangle = 0
    current_block = 0
    n_columns = len(pucs)
    current_order = sin_triangle_min_order // 2
    n_triangles = order // current_order
    starting_col = int(math.log2(n_triangles))

    def _rb(frm, to, separation=None):
        kwargs = {} if separation is None else {"separation": separation}
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="No registered width taper")
            gf.routing.route_bundle(
                c,
                frm,
                to,
                bend=routing_bend,
                taper=routing_taper,
                min_straight_taper=1,
                route_width=0.41,
                cross_section="strip",
                **kwargs,
            )

    for i in range(starting_col, n_columns):
        for j in range(n_triangles):
            row = current_order * j
            n_tri = (current_order - 1) * 2
            tri = triangles[current_triangle]

            pucs_out = []
            for k in range(current_order):
                puc = pucs[i][k + row]
                if k != 0:
                    pucs_out.append(puc["o3"])
                if k != current_order - 1:
                    pucs_out.append(puc["o4"])

            tri_in = [tri[f"o{n_tri - k}"] for k in range(n_tri)]
            _rb(pucs_out, tri_in, separation=3.52)

            tri_out = [tri[f"o{k + n_tri + 1}"] for k in range(n_tri)]

            if i != n_columns - 1:
                pucs_in = []
                for k in range(current_order):
                    puc_next = pucs[i + 1][k + row]
                    if k != 0:
                        pucs_in.append(puc_next["o2"])
                    if k != current_order - 1:
                        pucs_in.append(puc_next["o1"])
                _rb([pucs[i][row]["o3"]], [pucs[i + 1][row]["o2"]])
                _rb(
                    [pucs[i][row + current_order - 1]["o4"]],
                    [pucs[i + 1][row + current_order - 1]["o1"]],
                )
            else:
                pucs_in = [
                    core_blocks[current_block][f"o{8 - k}"] for k in range(8)
                ] + [core_blocks[current_block + 1][f"o{17 - k}"] for k in range(8, 16)]
                _rb([pucs[i][row]["o3"]], [core_blocks[current_block]["o9"]])
                _rb(
                    [pucs[i][row + current_order - 1]["o4"]],
                    [core_blocks[current_block + 1]["o1"]],
                )
                current_block += 2

            for a, b in zip(tri_out, pucs_in):
                _rb([a], [b])

            current_triangle += 1

        n_triangles *= 2
        current_order //= 2

    if not extra_pucs:
        return

    aux = [
        core_blocks[i][f"o{10 + j}"] for i in range(len(core_blocks)) for j in range(9)
    ]
    extra_pucs.insert(0, aux)

    n_triangles = int(2 ** (len(extra_pucs) - 2))
    current_order = order // n_triangles
    current_triangle = 0

    for i in range((sin_triangle_min_order // current_order) // 2):
        for j in range(n_triangles):
            row = current_order * j
            n_tri = (current_order - 1) * 2
            tri = extra_triangles[current_triangle]
            tri_in = [tri[f"o{n_tri + k + 1}"] for k in range(n_tri)]

            if i == 0:
                pucs_out = [extra_pucs[0][k + 1 + row * 2] for k in range(n_tri)]
                _rb([extra_pucs[0][row * 2]], [extra_pucs[1][row]["o2"]])
                _rb(
                    [extra_pucs[1][row + current_order - 1]["o1"]],
                    [extra_pucs[0][row * 2 + current_order * 2 - 1]],
                )
            else:
                pucs_out = []
                for k in range(current_order):
                    puc = extra_pucs[i][k + row]
                    if k != 0:
                        pucs_out.append(puc["o3"])
                    if k != current_order - 1:
                        pucs_out.append(puc["o4"])
                _rb([extra_pucs[i][row]["o3"]], [extra_pucs[i + 1][row]["o2"]])
                _rb(
                    [extra_pucs[i + 1][row + current_order - 1]["o1"]],
                    [extra_pucs[i][row + current_order - 1]["o4"]],
                )

            for a, b in zip(tri_in, pucs_out):
                _rb([a], [b])

            pucs_in = []
            for k in range(current_order):
                puc_next = extra_pucs[i + 1][k + row]
                if k != 0:
                    pucs_in.append(puc_next["o2"])
                if k != current_order - 1:
                    pucs_in.append(puc_next["o1"])

            tri_out = [tri[f"o{n_tri - k}"] for k in range(n_tri)]
            _rb(pucs_in, tri_out, separation=3.52)

            current_triangle += 1

        n_triangles //= 2
        current_order *= 2


@gf.cell
def block_3x3(
    puc: gf.partial,
    x_separation: float,
    y_separation: float,
    routing_taper: gf.Component,
    routing_bend: gf.Component,
    cross_section: gf.CrossSection,
    puc_numbers: list | None,
) -> gf.Component:
    c = gf.Component()

    # PUC creation
    if puc_numbers is None:
        puc = gf.get_component(puc)
        puc_left = c << puc
        puc_right = c << puc
        puc_center = c << puc
    else:
        puc1 = gf.get_component(puc(puc_number=puc_numbers[0]))
        puc_left = c << puc1
        puc2 = gf.get_component(puc(puc_number=puc_numbers[1]))
        puc_right = c << puc2
        puc3 = gf.get_component(puc(puc_number=puc_numbers[2]))
        puc_center = c << puc3

    # PUC movement
    puc_right.movex(puc_right["o2"].x, puc_left["o3"].x + x_separation)
    center = (puc_right.x - puc_left.x) / 2
    puc_center.move((0, puc_center.ymax), (center, puc_left.ymin - y_separation))

    # Connection between top PUCs
    gf.routing.route_bundle(
        c,
        [puc_left["o3"]],
        [puc_right["o2"]],
        bend=routing_bend,
        taper=routing_taper,
        min_straight_taper=1,
        cross_section="strip",
    )

    # Connections between bottom and top PUCs
    spacing = (puc_center["e2"].y - puc_center["o2"].y) + y_separation / 2
    for port_from, port_to, dx in [
        (puc_center["o2"], puc_left["o4"], -1),
        (puc_center["o3"], puc_right["o1"], 1),
    ]:
        gf.routing.route_bundle(
            c,
            [port_from],
            [port_to],
            bend=routing_bend,
            taper=routing_taper,
            min_straight_taper=1,
            cross_section="strip",
            route_width=cross_section.width,
            steps=[{"dx": dx, "dy": spacing}, {"dx": -dx}],
        )

    # Optical Ports
    for name, puc_ref, port in [
        ("o1", puc_center, "o1"),
        ("o2", puc_left, "o1"),
        ("o3", puc_left, "o2"),
        ("o4", puc_right, "o3"),
        ("o5", puc_right, "o4"),
        ("o6", puc_center, "o4"),
    ]:
        c.add_port(name, port=puc_ref[port])

    # Electric ports
    for i, puc_ref in enumerate([puc_left, puc_center, puc_right]):
        for j in range(1, 5):
            c.add_port(f"e{i * 4 + j}", port=puc_ref[f"e{j}"])

    return c


@gf.cell
def block_9x9(
    puc: gf.partial,
    crossing: gf.Component,
    x_separation: float,
    y_separation: float,
    block_x_separation: float,
    block_y_separation: float,
    routing_taper: gf.Component,
    crossing_taper: gf.Component,
    routing_bend: gf.Component,
    crossing_cross_section: gf.CrossSection,
    cross_section: gf.CrossSection,
    puc_numbers: list | None,
    drc_friendly: bool = False,
) -> gf.Component:
    c = gf.Component()

    base_block = gf.partial(
        block_3x3,
        puc=puc,
        x_separation=x_separation,
        y_separation=y_separation,
        routing_taper=routing_taper,
        routing_bend=routing_bend,
        cross_section=cross_section,
        puc_numbers=None,
    )
    if puc_numbers is None:
        base_block = gf.get_component(base_block)

    blocks = []
    for i in range(6):
        if puc_numbers is None:
            block_ref = c << base_block
        else:
            if i < 3:
                base_block_c = gf.get_component(
                    base_block(
                        puc_numbers=[
                            puc_numbers[0] + i,
                            puc_numbers[2] + i,
                            puc_numbers[1] + i,
                        ]
                    )
                )
            else:
                base_block_c = gf.get_component(
                    base_block(
                        puc_numbers=[
                            puc_numbers[3] + i,
                            puc_numbers[5] + i,
                            puc_numbers[4] + i,
                        ]
                    )
                )
            block_ref = c << base_block_c
        if i < 3:
            block_ref.move((0, 0), (0, -block_ref.ysize * i - block_y_separation * i))
        else:
            block_ref.movex(0, block_ref.xsize + block_x_separation)
            block_ref.movey(
                0, -(block_ref.ysize * (i - 3)) - block_y_separation * (i - 3)
            )

        blocks.append(block_ref)

    if drc_friendly:
        top_cross = c << top_crossing_9x9(
            crossing,
            crossing_taper,
            15,
            [15.398, 36.054, 1.999],
            crossing_cross_section,
            drc_friendly,
        )
    else:
        top_cross = c << top_crossing_9x9(
            crossing,
            crossing_taper,
            15,
            [15.401, 36.049, 2],
            crossing_cross_section,
            drc_friendly,
        )

    top_cross.move(
        (top_cross.x, top_cross["o2"].y),
        (
            blocks[0]["o5"].x
            + ((blocks[3]["o2"].x - blocks[0]["o5"].x) - top_cross.xsize) / 2
            + top_cross.xsize / 2,
            blocks[1]["o5"].y,
        ),
    )

    if drc_friendly:
        bot_cross = c << bottom_crossing_9x9(
            crossing,
            crossing_taper,
            1,
            [2.001, 4.853, 46.598, 6.898],
            crossing_cross_section,
            drc_friendly,
        )
    else:
        bot_cross = c << bottom_crossing_9x9(
            crossing,
            crossing_taper,
            1,
            [2, 4.852, 46.597, 6.898],
            crossing_cross_section,
            drc_friendly,
        )
    bot_cross.move(
        (bot_cross.x, bot_cross["o1"].y),
        (
            top_cross.x,
            blocks[2]["o5"].y,
        ),
    )

    for input, output in [
        (blocks[0]["o4"], blocks[3]["o3"]),
        (blocks[5]["o1"], blocks[2]["o6"]),
        (blocks[0]["o5"], top_cross["o5"]),
        (blocks[0]["o6"], top_cross["o4"]),
        (blocks[1]["o4"], top_cross["o3"]),
        (blocks[3]["o2"], top_cross["o6"]),
        (blocks[3]["o1"], top_cross["o7"]),
        (blocks[4]["o3"], top_cross["o8"]),
        (blocks[1]["o6"], bot_cross["o3"]),
        (blocks[4]["o1"], bot_cross["o6"]),
        (blocks[2]["o4"], bot_cross["o2"]),
        (blocks[5]["o3"], bot_cross["o7"]),
        (blocks[2]["o5"], bot_cross["o1"]),
        (blocks[5]["o2"], bot_cross["o8"]),
    ]:
        gf.routing.route_bundle(
            c,
            [output],
            [input],
            cross_section="strip",
            min_straight_taper=1,
            taper=routing_taper,
            bend=routing_bend,
            route_width=0.41,
        )

    for input, output in [
        (top_cross["o1"], bot_cross["o4"]),
        (top_cross["o10"], bot_cross["o5"]),
    ]:
        st_ref = c << gf.c.straight(
            input.y - output.y - routing_bend.ysize * 2 - crossing_taper.xsize,
            cross_section=crossing_cross_section,
        )
        st_ref.connect("o1", input)
        tap_ref = c << crossing_taper
        tap_ref.connect("o2", st_ref["o2"])
        gf.routing.route_bundle(
            c,
            [output],
            [tap_ref["o1"]],
            bend=routing_bend,
            cross_section=cross_section,
        )

    for input, output in [
        (blocks[1]["o5"], top_cross["o2"]),
        (blocks[4]["o2"], top_cross["o9"]),
    ]:
        tap_ref = c << crossing_taper
        tap_ref.connect("o1", input)
        gf.routing.route_bundle(
            c,
            [tap_ref["o2"]],
            [output],
            cross_section=crossing_cross_section,
            bend=routing_bend,
        )

    for i in range(3):
        for j in range(1, 4):
            c.add_port(f"o{j + 3 * i}", port=blocks[2 - i][f"o{j}"])
            c.add_port(f"o{j + 9 + 3 * i}", port=blocks[3 + i][f"o{j + 3}"])

    return c


@gf.cell(check_instances=False)
def bottom_crossing_9x9(
    crossing: gf.Component,
    taper: gf.Component,
    intra_spacing: float,
    output_spacing: list,
    cross_section: gf.Component,
    drc_friendly: bool = False,
) -> gf.Component:
    c = gf.Component()

    crossing = gf.get_component(crossing)

    ul_crossing = c << crossing
    ur_crossing = c << crossing
    ll_crossing = c << crossing
    lr_crossing = c << crossing

    ll_crossing.rotate(45)
    for i in range(2):
        st_ref = c << gf.c.straight(intra_spacing, cross_section=cross_section)
        st_ref.connect("o1", ll_crossing[f"o{2 + i}"])
        if i == 0:
            ul_crossing.connect("o4", st_ref["o2"])
        else:
            lr_crossing.connect("o1", st_ref["o2"])
    st_ref = c << gf.c.straight(intra_spacing, cross_section=cross_section)
    st_ref.connect("o1", ul_crossing["o3"])
    ur_crossing.connect("o1", st_ref["o2"])
    st_ref = c << gf.c.straight(intra_spacing, cross_section=cross_section)
    st_ref.connect("o1", ur_crossing["o4"])

    bend_45 = bend_modified_hermite(length_access=0)

    crossing_outs = [
        (ll_crossing["o1"], ll_crossing["o4"]),
        (ul_crossing["o1"], lr_crossing["o4"]),
        (ul_crossing["o2"], lr_crossing["o3"]),
        (ur_crossing["o2"], ur_crossing["o3"]),
    ]
    for i in range(4):
        st_ref = c << gf.c.straight(output_spacing[i], cross_section=cross_section)
        st_ref.connect("o1", crossing_outs[i][0])
        tap_ref = c << taper
        tap_ref.connect("o2", st_ref["o2"])
        if i == 0 and drc_friendly:
            tap_ref.move((0.001, 0.001))
        bnd_ref = c << bend_45
        bnd_ref.connect("o1", tap_ref["o1"], mirror=False if i == 2 else True)
        c.add_port(f"o{i + 1}", port=bnd_ref["o2"])

        st_ref = c << gf.c.straight(output_spacing[i], cross_section=cross_section)
        st_ref.connect("o1", crossing_outs[i][1])
        tap_ref = c << taper
        tap_ref.connect("o2", st_ref["o2"])
        if i == 0 and drc_friendly:
            tap_ref.move((-0.001, 0.001))
        bnd_ref = c << bend_45
        bnd_ref.connect("o1", tap_ref["o1"], mirror=True if i == 2 else False)
        c.add_port(f"o{8 - i}", port=bnd_ref["o2"])

    if drc_friendly:
        for port in c.ports:
            orientation = round(port.orientation)
            if orientation == 0:
                port.center = (port.center[0] - 0.001, port.center[1])
            elif orientation == 90:
                port.center = (port.center[0], port.center[1] - 0.001)
            elif orientation == 180:
                port.center = (port.center[0] + 0.001, port.center[1])

    return c


@gf.cell(check_instances=False)
def top_crossing_9x9(
    crossing: gf.Component,
    taper: gf.Component,
    intra_spacing: float,
    output_spacing: list,
    cross_section: gf.Component,
    drc_friendly: bool = False,
) -> gf.Component:
    c = gf.Component()

    crossing = gf.get_component(crossing)

    ul_crossing = c << crossing
    ur_crossing = c << crossing
    ct_crossing = c << crossing

    ul_crossing.rotate(45)

    st_ref = c << gf.c.straight(intra_spacing, cross_section=cross_section)
    st_ref.connect("o1", ul_crossing["o3"])

    ct_crossing.connect("o1", st_ref["o2"])
    ct_crossing.move((-0.0006, -0.0006))

    st_ref = c << gf.c.straight(intra_spacing, cross_section=cross_section)
    st_ref.connect("o1", ct_crossing["o4"])

    ur_crossing.connect("o1", st_ref["o2"])
    ur_crossing.move((-0.0006, 0.0006))

    bend_45 = bend_modified_hermite(length_access=0)

    tap_ref = c << taper
    tap_ref.connect("o2", ur_crossing["o4"])
    tap_ref.move((0.0006, 0.0006))
    bnd_ref = c << bend_45
    bnd_ref.connect("o1", tap_ref["o1"])
    tap_ref1 = c << taper
    tap_ref1.connect("o1", bnd_ref["o2"])
    if drc_friendly:
        tap_ref1.movey(0.001)

    tap_ref = c << taper
    tap_ref.connect("o2", ul_crossing["o4"])
    tap_ref.move((-0.0006, 0.0006))
    bnd_ref = c << bend_45
    bnd_ref.connect("o1", tap_ref["o1"], mirror=True)
    tap_ref2 = c << taper
    tap_ref2.connect("o1", bnd_ref["o2"])
    if drc_friendly:
        tap_ref2.movey(0.001)

    ll_crossing = c << crossing
    lr_crossing = c << crossing

    lr_crossing.connect("o2", tap_ref1["o2"])
    ll_crossing.connect("o2", tap_ref2["o2"])

    gf.routing.route_single(
        c,
        ll_crossing["o3"],
        lr_crossing["o1"],
        cross_section=cross_section,
    )

    c.add_port("o1", port=ll_crossing["o4"])
    c.add_port("o2", port=ll_crossing["o1"])
    c.add_port("o9", port=lr_crossing["o3"])
    c.add_port("o10", port=lr_crossing["o4"])

    for port_name, spacing_idx, src_ref, src_port, mirror in [
        ("o3", 0, ul_crossing, "o1", True),
        ("o4", 1, ul_crossing, "o2", False),
        ("o5", 2, ct_crossing, "o2", True),
        ("o6", 2, ct_crossing, "o3", False),
        ("o7", 1, ur_crossing, "o2", True),
        ("o8", 0, ur_crossing, "o3", False),
    ]:
        st = c << gf.c.straight(
            output_spacing[spacing_idx], cross_section=cross_section
        )
        st.connect("o1", src_ref[src_port])
        tap = c << taper
        tap.connect("o2", st["o2"])
        if port_name in ["o4"] and drc_friendly:
            tap.move((0.001, -0.001))
        elif port_name in ["o3"] and drc_friendly:
            tap.move((0.001, 0.001))
        elif port_name in ["o8"] and drc_friendly:
            tap.move((-0.001, 0.001))
        elif port_name in ["o7"] and drc_friendly:
            tap.move((-0.001, -0.001))
        bnd = c << bend_45
        bnd.connect("o1", tap["o1"], mirror=mirror)
        c.add_port(port_name, port=bnd["o2"])

    if drc_friendly:
        for port in c.ports:
            orientation = round(port.orientation)
            if port.width != 1.5:
                if orientation == 0:
                    port.center = (port.center[0] - 0.001, port.center[1])
                elif orientation == 90:
                    port.center = (port.center[0], port.center[1] - 0.001)
                elif orientation == 180:
                    port.center = (port.center[0] + 0.001, port.center[1])

    return c


v7b_cells = get_cells(sys.modules[__name__])


if __name__ == "__main__":
    ipr.get_pdk().activate()

    xs = gf.get_cross_section("strip", width=0.41, radius_min=3.0)
    xs_w = gf.get_cross_section("strip", width=0.93)
    xs_c = gf.get_cross_section("strip", width=1.56)
    xs_n = gf.get_cross_section("nitride2", width=2)

    bend_r5 = bend_r5 = spaced_bend()
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
        drc_friendly=False,
    )

    gf.get_component(core).show()
