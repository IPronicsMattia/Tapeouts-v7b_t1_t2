import math

import gdsfactory as gf
import numpy as np
from gdsfactory.typings import CrossSectionSpec, LayerSpec
from iprlayout_tower import rib_taper  # type: ignore
from iprlayout_tower.tower_tech import LAYER  # type: ignore
from scipy.interpolate import CubicSpline


def make_even_third_decimal(x: float) -> float:
    scaled = round(x * 1000)
    if scaled % 2 != 0:
        scaled += 1
    return scaled / 1000


def _correct_taper_endpoints(width_in, width_out, length, m, npoints, grid=0.002):
    """
    Pre-compensate rib_taper's endpoint discretization:
    w[i] = w_out + (w_in - w_out)*(1 - i/n)^m,  n = int(npoints*length).

    Returns grid-snapped (w_in_corr, w_out_corr) chosen so the *actual*
    endpoint sample lands as close as possible to the requested width.
    """
    n = int(npoints * length)
    if n <= 1 or width_in == width_out:
        return width_in, width_out
    k = (1.0 / n) ** m

    def snap_floor(w):
        return math.floor(w / grid) * grid

    def snap_ceil(w):
        return math.ceil(w / grid) * grid

    if width_out > width_in:
        # widening: last sample = w_out_corr + (width_in - w_out_corr)*k, want = width_out
        exact = (width_out - width_in * k) / (1.0 - k)
        candidates = {snap_floor(exact), snap_ceil(exact), width_out}
        best = min(
            candidates,
            key=lambda w: abs((w + (width_in - w) * k) - width_out),
        )
        return width_in, best
    else:
        # narrowing: first sample (after flip) = w_in_corr + (width_out - w_in_corr)*k, want = width_in
        exact = (width_in - width_out * k) / (1.0 - k)
        candidates = {snap_floor(exact), snap_ceil(exact), width_in}
        best = min(
            candidates,
            key=lambda w: abs((w + (width_out - w) * k) - width_in),
        )
        return best, width_out


@gf.cell
def anwg_spiral(
    win: float = 0.402,
    wtip: float = 0.12,
    a: float = 2.05,
    b: float = 0.12,
    layer: LayerSpec = "WG",
    activate_dummy: bool = False,
) -> gf.Component:
    """Returns a spiral.
    Radius (r) of the spiral is: r = a * exp(b * angle)

    Args:
        win (float): width at the input.
        wtip (float): final width of the spiral.
        a (float): parameter to define the radius function.
        b (float): parameter to define the radius function.
        layer (LayerSpec): layer used for the spiral. Defaults to cross_section.layer.
        activate_dummy (bool): decide if placing scatter dummy in spiral.
    """
    # Create component
    c = gf.Component()

    # Get information
    layer = gf.get_layer(layer)
    res_bent = 500

    # Calculate points of the spiral
    arr_angle = np.linspace(np.pi / 2, np.pi / 2 - 5 * np.pi, res_bent)
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

    # Use the point for define the polygon
    c.add_polygon(polygon_points, layer=layer)

    # Add ports
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

    # Calculate minimum spacing
    f_out = CubicSpline(np.flip(arr_angle), np.flip(r_outer))
    f_in = CubicSpline(np.flip(arr_angle), np.flip(r_inner))

    arr_angle_in = np.linspace(np.pi / 2, np.pi / 2 - 3 * np.pi, res_bent)
    arr_angle_out = np.linspace(np.pi / 2 - 2 * np.pi, np.pi / 2 - 5 * np.pi, res_bent)

    spacing = f_in(arr_angle_in) - f_out(arr_angle_out)

    c.info["min_spacing"] = np.round(spacing.min(), 3)
    c.flatten()

    # Add metal dummy if requested
    if activate_dummy:
        m1 = c << gf.c.regular_polygon(side_length=1, sides=4, layer=LAYER.metal1)
        m2 = c << gf.c.regular_polygon(side_length=1, sides=4, layer=LAYER.metal2)
        m3 = c << gf.c.regular_polygon(side_length=3, sides=4, layer=LAYER.metal3)

        m1.center = (spiral_pts_x_outer[-1], spiral_pts_x_outer[-1])
        m2.center = m1.center
        m3.center = m1.center
    return c


@gf.cell
def anwg_absorber(
    win: float = 0.41,
    wout: float = 0.402,
    taper_length: float = 0.6,
    a: float = 2.05,
    b: float = 0.12,
    length_aux_st: float = 1.0,
    cross_section: CrossSectionSpec = "nitride2",
    activate_dummy: bool = False,
) -> gf.Component:
    """Returns a spiral.
    Radius (r) of the spiral is: r = a * exp(b * angle)

    Args:
        win (float): width at the input of the absorber.
        wout (float): width at the input of the spiral.
        a (float): parameter to define the radius function.
        b (float): parameter to define the radius function.
        layer (LayerSpec): layer used for the spiral. Defaults to cross_section.layer.
        activate_dummy (bool): decide if placing scatter dummy in spiral.
    """
    # Create component
    c = gf.Component()

    # Get information
    layer = gf.get_cross_section(cross_section).layer
    wtip = 0.15

    # Create spiral
    spiral = c << anwg_spiral(
        win=wout,
        wtip=wtip,
        a=a,
        b=b,
        layer=layer,
        activate_dummy=activate_dummy,
    )

    # Create input taper
    taper = c << gf.components.taper(
        width1=win, width2=wout, length=taper_length, layer=layer
    )

    # Create a small straight at input
    aux_st = c << gf.components.straight(
        width=win, length=length_aux_st, cross_section=cross_section
    )

    # Connect all blocks
    taper.connect("o2", spiral.ports["o1"])
    aux_st.connect("o2", taper.ports["o1"])

    # Add ports
    c.add_port("o1", port=aux_st.ports["o1"])
    c.info["min_spacing"] = spiral.cell.info["min_spacing"]

    c.flatten()

    # Add Taper marking
    rect = c << gf.c.rectangle(size=(c.dxsize, c.dysize), layer=LAYER.m_wgcnct)
    rect.xmin = c.xmin
    rect.ymin = c.ymin
    return c


@gf.cell
def taper_sin2(
    width_in: float = 0.2,
    width_out: float = 0.7,
    length: float = 5,
    length_access: float = 3,
    m_taper: float = 2.225,
    n_points: float = 100,
    cross_sections: list = [  # noqa: B006
        "strip",
        "nitride",
        "nitride2",
        "hat_nitride",
        "hat_nitride2",
    ],  # noqa: B006
    cross_section: str = "nitride2",
    layers: list = [LAYER.swg, LAYER.nwg, LAYER.anwg],  # noqa: B006
    sim: bool = True,
    access: bool = True,
):
    width_in = make_even_third_decimal(width_in)
    width_out = make_even_third_decimal(width_out)

    if cross_section == cross_sections[0]:
        layer = layers[0]
    elif cross_section == cross_sections[1]:
        layer = layers[1]
        cross_section_hat = gf.cross_section.cross_section(
            width=width_out,
            layer=LAYER.HAT_NWG,
        )
    elif cross_section == cross_sections[2]:
        layer = layers[2]
        cross_section_hat = gf.cross_section.cross_section(
            width=width_out,
            layer=LAYER.HAT_AN,
        )

    w_in_corr, w_out_corr = _correct_taper_endpoints(
        width_in=width_in,
        width_out=width_out,
        length=length,
        m=m_taper,
        npoints=n_points,
    )
    # NOTE: no make_even_third_decimal here — helper output is already grid-snapped

    c = gf.Component()
    c << rib_taper(
        width_RIB_in=w_in_corr,
        width_RIB_out=w_out_corr,
        length=length,
        m_RIB=m_taper,
        cross_section=cross_section,
        npoints=n_points,
    )

    xs_trans = gf.cross_section.cross_section(layer=(118, 120))
    c << rib_taper(
        width_RIB_in=w_in_corr,
        width_RIB_out=w_out_corr,
        length=length,
        m_RIB=m_taper,
        cross_section=xs_trans,
        npoints=n_points,
    )

    if access:
        wg_access_in = c << gf.components.straight(
            length=length_access, cross_section=cross_section, width=width_in
        )
        wg_access_in.dmovex(-length_access)
        wg_access_out = c << gf.components.straight(
            length=length_access, cross_section=cross_section, width=width_out
        )
        wg_access_out.dmovex(length)

    c.add_port(
        name="o1",
        orientation=180,
        center=(0, 0),
        layer=layer,
        width=width_in,
    )

    c.add_port(
        name="o2",
        orientation=0,
        center=(length, 0),
        layer=layer,
        width=width_out,
    )

    if sim:
        c << rib_taper(
            width_RIB_in=w_in_corr,
            width_RIB_out=w_out_corr,
            length=length,
            m_RIB=m_taper,
            cross_section=cross_section_hat,
            npoints=n_points,
        )

        if access:
            wg_access_in_hat = c << gf.components.straight(
                length=length_access, cross_section=cross_section_hat, width=width_in
            )
            wg_access_in_hat.dmovex(-length_access)
            wg_access_out_hat = c << gf.components.straight(
                length=length_access, cross_section=cross_section_hat, width=width_out
            )
            wg_access_out_hat.dmovex(length)

    return c


def taper_width_at(x, width_start, width_end, length, m):
    """Width at local position x (0 <= x <= length), valid when width_end >= width_start."""
    if length <= 0:
        return width_end
    t = min(max(x / length, 0.0), 1.0)
    return width_end - (width_end - width_start) * (1 - t) ** m


def taper_width_at_any(x, w_start, w_end, length, m):
    """Width at local x for rising or falling segments (rib_taper flips falling profiles)."""
    if w_end >= w_start:
        return taper_width_at(x, w_start, w_end, length, m)
    else:
        return taper_width_at(length - x, w_end, w_start, length, m)


def max_run_below_width(segments, w_thresh=0.25, dz=0.1):
    """
    segments: list of (length, w_start, w_end, m) traversed in order.
    Returns the longest contiguous length (um) where width < w_thresh.
    """
    run = 0.0
    max_run = 0.0
    for L, w0, w1, m in segments:
        if L <= 0:
            continue
        n = max(int(L / dz), 2)
        step = L / n
        for i in range(n):
            x = (i + 0.5) * step
            if taper_width_at_any(x, w0, w1, L, m) < w_thresh:
                run += step
                if run > max_run:
                    max_run = run
            else:
                run = 0.0
    return max_run


@gf.cell
def ec_sin2_strip_single(
    trench_width: float = 20,
    trench_gap: float = 10,
    length_input: float = 1,
    width_in: float = 0.15,
    dwidth_in: float = 0.1,
    width_out: float = 0.7,
    length_total: float = 250,
    length_1: float = 100,
    length_access: float = 3,
    m_1: float = 0.5,
    m_2: float = 2.5,
    n_points: float = 250,
    length_taper_out: float = 20,
    width_out_taper_out: float = 1.492,
    m_taper_out: float = 0.569565,
    n_points_taper_out: int = 100,
    cross_sections: list = [  # noqa: B006
        "strip",
        "nitride",
        "nitride2",
        "hat_nitride",
        "hat_nitride2",
    ],  # noqa: B006
    cross_section: str = "nitride2",
    layers: list = [LAYER.swg, LAYER.nwg, LAYER.anwg],  # noqa: B006
    sim: bool = False,
    access: bool = True,
):
    dwidth_in = make_even_third_decimal(dwidth_in)
    width_in = make_even_third_decimal(width_in)
    width_out = make_even_third_decimal(width_out)
    width_center = make_even_third_decimal(width_in + dwidth_in)
    width_out_taper_out = make_even_third_decimal(width_out_taper_out)
    trench_width = make_even_third_decimal(trench_width)

    if cross_section == cross_sections[0]:
        layer = layers[0]
    elif cross_section == cross_sections[1]:
        layer = layers[1]
        layer_hat = LAYER.HAT_NWG
        cross_section_hat = gf.cross_section.cross_section(
            width=width_out_taper_out,
            layer=layer_hat,
        )
    elif cross_section == cross_sections[2]:
        layer = layers[2]
        layer_hat = LAYER.HAT_AN
        cross_section_hat = gf.cross_section.cross_section(
            width=width_out_taper_out,
            layer=layer_hat,
        )

    cross_section_trench = gf.cross_section.cross_section(
        width=trench_width,
        layer=LAYER.scrbo,
    )

    length_rat = length_1 / length_total
    length_2 = length_total - length_1

    # --- constraint: width must be >= 0.25 by x = 100 ---
    x_check = 100.0
    x_local = x_check - length_input

    if x_local <= 0:
        width_at_check = width_in
    elif x_local <= length_1:
        width_at_check = taper_width_at(x_local, width_in, width_center, length_1, m_1)
    else:
        width_at_check = taper_width_at(
            x_local - length_1, width_center, width_out, length_2, m_2
        )

    min_width_required = 0.25
    if width_at_check < min_width_required:
        raise ValueError(
            f"Width at x={x_check} is {width_at_check:.4f}, below required minimum "
            f"of {min_width_required}. Adjust width_in, dwidth_in, length_1, m_1, or m_2."
        )

    n_points_1 = int(length_rat * n_points)
    n_points_2 = n_points - n_points_1

    c = gf.Component()

    taper_1 = c << taper_sin2(
        width_in=width_in,
        width_out=width_center,
        length=length_1,
        m_taper=m_1,
        n_points=n_points_1,
        cross_sections=cross_sections,
        cross_section=cross_section,
        layers=layers,
        sim=sim,
        access=False,
    )
    taper_1.dmovex(length_input)

    taper_2 = c << taper_sin2(
        width_in=width_center,
        width_out=width_out,
        length=length_2,
        m_taper=m_2,
        n_points=n_points_2,
        cross_sections=cross_sections,
        cross_section=cross_section,
        layers=layers,
        sim=sim,
        access=False,
    )
    taper_2.dmovex(taper_1.dxmax)

    taper_3 = c << taper_sin2(
        width_in=width_out,
        width_out=width_out_taper_out,
        length=length_taper_out,
        m_taper=m_taper_out,
        n_points=n_points_taper_out,
        cross_sections=cross_sections,
        cross_section=cross_section,
        layers=layers,
        sim=sim,
        access=False,
    )
    taper_3.dmovex(taper_2.dxmax)

    trench_top = c << gf.components.straight(
        length=length_total + length_input,
        cross_section=cross_section_trench,
        width=trench_width,
    )
    trench_top.dmovey((trench_gap + trench_width) / 2)
    trench_bot = c << gf.components.straight(
        length=length_total + length_input,
        cross_section=cross_section_trench,
        width=trench_width,
    )
    trench_bot.dmovey(-(trench_gap + trench_width) / 2)

    c.add_port(
        name="oaux1",
        orientation=180,
        center=(0, 0),
        layer=layer,
        width=width_in,
    )

    port_o2_x = taper_3.dxmax

    if sim:
        access = True
        length_access = 4

    if access:
        wg_access_out = c << gf.components.straight(
            length=length_access, cross_section=cross_section, width=width_out_taper_out
        )
        wg_access_out.dmovex(taper_3.dxmax)
        port_o2_x = wg_access_out.dxmax

    if sim:
        wg_access_out_hat = c << gf.components.straight(
            length=length_access,
            cross_section=cross_section_hat,
            width=width_out_taper_out,
        )
        wg_access_out_hat.dmovex(taper_3.dxmax)

    c.add_port(
        name="o1",
        orientation=0,
        center=(port_o2_x, 0),
        layer=layer,
        width=width_out_taper_out,
    )

    c.flatten()

    return c


@gf.cell
def ec_sin2_strip_trident(
    trench_width: float = 20,
    trench_gap: float = 10,
    length_input: float = 1,
    # --- center waveguide ---
    width_in: float = 0.15,
    dwidth_in: float = 0.1,
    width_out: float = 0.7,
    length_total: float = 250,
    length_1_rat: float = 0.25,
    m_1: float = 0.5,
    m_2: float = 2.5,
    n_points: float = 500,
    length_taper_out: float = 20,
    width_out_taper_out: float = 1.492,
    m_taper_out: float = 0.569565,
    n_points_taper_out: int = 100,
    # --- side waveguides (identical pair) ---
    width_in_side: float = 0.15,
    dwidth_in_side: float = 0.08,
    width_out_side: float = 0.5,
    length_1_side_rat: float = 0.32,
    m_1_side: float = 0.5,
    m_2_side: float = 2.5,
    n_points_side: float = 250,
    wg_spacing: float = 2.0,
    length_access_side: float = 5,
    # --- common ---
    length_access: float = 3,
    cross_sections: list = [  # noqa: B006
        "strip",
        "nitride",
        "nitride2",
        "hat_nitride",
        "hat_nitride2",
    ],  # noqa: B006
    cross_section: str = "nitride2",
    layers: list = [LAYER.swg, LAYER.nwg, LAYER.anwg],  # noqa: B006
    sim: bool = True,
    access: bool = True,
):
    # center widths
    dwidth_in = make_even_third_decimal(dwidth_in)
    width_in = make_even_third_decimal(width_in)
    width_out = make_even_third_decimal(width_out)
    width_center = make_even_third_decimal(width_in + dwidth_in)
    width_out_taper_out = make_even_third_decimal(width_out_taper_out)
    # side widths
    dwidth_in_side = make_even_third_decimal(dwidth_in_side)
    width_in_side = make_even_third_decimal(width_in_side)
    width_out_side = make_even_third_decimal(width_out_side)
    width_center_side = make_even_third_decimal(width_in_side + dwidth_in_side)
    # common
    trench_width = make_even_third_decimal(trench_width)
    wg_spacing = make_even_third_decimal(wg_spacing)
    length_1 = length_1_rat * length_total
    length_1_side = length_1_side_rat * length_total
    # centerline offset of the side waveguides:
    # edge-to-edge gap wg_spacing between center edge (width_in/2) and side edge (width_in_side/2)
    y_offset = wg_spacing + width_in / 2 + width_in_side / 2

    if cross_section == cross_sections[0]:
        layer = layers[0]
    elif cross_section == cross_sections[1]:
        layer = layers[1]
        layer_hat = LAYER.HAT_NWG
        cross_section_hat = gf.cross_section.cross_section(
            width=width_out_taper_out,
            layer=layer_hat,
        )
        cross_section_hat_side = gf.cross_section.cross_section(
            width=width_out_side,
            layer=layer_hat,
        )
    elif cross_section == cross_sections[2]:
        layer = layers[2]
        layer_hat = LAYER.HAT_AN
        cross_section_hat = gf.cross_section.cross_section(
            width=width_out_taper_out,
            layer=layer_hat,
        )
        cross_section_hat_side = gf.cross_section.cross_section(
            width=width_out_side,
            layer=layer_hat,
        )
    cross_section_trench = gf.cross_section.cross_section(
        width=trench_width,
        layer=LAYER.scrbo,
    )
    length_2 = length_total - length_1
    length_2_side = length_total - length_1_side

    # --- n_points per segment, guarded against degenerate ratios ---
    n_points_1 = max(int(length_1_rat * n_points), 10)
    n_points_2 = max(int(n_points) - n_points_1, 10)
    n_points_1_side = max(int(length_1_side_rat * n_points_side), 10)
    n_points_2_side = max(int(n_points_side) - n_points_1_side, 10)

    if sim:
        access = True
        length_access = 4

    c = gf.Component()

    # ---------------- center waveguide ----------------
    taper_1 = c << taper_sin2(
        width_in=width_in,
        width_out=width_center,
        length=length_1,
        m_taper=m_1,
        n_points=n_points_1,
        cross_sections=cross_sections,
        cross_section=cross_section,
        layers=layers,
        sim=sim,
        access=False,
    )
    taper_1.dmovex(length_input)

    taper_2 = c << taper_sin2(
        width_in=width_center,
        width_out=width_out,
        length=length_2,
        m_taper=m_2,
        n_points=n_points_2,
        cross_sections=cross_sections,
        cross_section=cross_section,
        layers=layers,
        sim=sim,
        access=False,
    )
    taper_2.dmovex(taper_1.dxmax)

    taper_3 = c << taper_sin2(
        width_in=width_out,
        width_out=width_out_taper_out,
        length=length_taper_out,
        m_taper=m_taper_out,
        n_points=n_points_taper_out,
        cross_sections=cross_sections,
        cross_section=cross_section,
        layers=layers,
        sim=sim,
        access=False,
    )
    taper_3.dmovex(taper_2.dxmax)

    port_out_x = taper_3.dxmax

    if access:
        wg_access_out = c << gf.components.straight(
            length=length_access, cross_section=cross_section, width=width_out_taper_out
        )
        wg_access_out.dmovex(taper_3.dxmax)
        port_out_x = wg_access_out.dxmax

    if sim:
        wg_access_out_hat = c << gf.components.straight(
            length=length_access,
            cross_section=cross_section_hat,
            width=width_out_taper_out,
        )
        wg_access_out_hat.dmovex(taper_3.dxmax)

    # ---------------- side waveguides ----------------
    for sign in (+1, -1):
        dy = sign * y_offset

        taper_1_side = c << taper_sin2(
            width_in=width_in_side,
            width_out=width_center_side,
            length=length_1_side,
            m_taper=m_1_side,
            n_points=n_points_1_side,
            cross_sections=cross_sections,
            cross_section=cross_section,
            layers=layers,
            sim=sim,
            access=False,
        )
        taper_1_side.dmovex(length_input)
        taper_1_side.dmovey(dy)

        taper_2_side = c << taper_sin2(
            width_in=width_center_side,
            width_out=width_out_side,
            length=length_2_side,
            m_taper=m_2_side,
            n_points=n_points_2_side,
            cross_sections=cross_sections,
            cross_section=cross_section,
            layers=layers,
            sim=sim,
            access=False,
        )
        taper_2_side.dmovex(taper_1_side.dxmax)
        taper_2_side.dmovey(dy)

        if access:
            wg_access_side = c << gf.components.straight(
                length=length_access_side,
                cross_section=cross_section,
                width=width_out_side,
            )
            wg_access_side.dmovex(taper_2_side.dxmax)
            wg_access_side.dmovey(dy)

            absorber_side = c << anwg_absorber(
                win=width_out_side,
                wout=width_out_side,
                taper_length=1,
                a=5.05,
                b=0.15,
                length_aux_st=1.0,
                cross_section=cross_section,
            )
            absorber_side.connect(
                "o1",
                wg_access_side.ports["o2"],
                allow_layer_mismatch=True,
                allow_width_mismatch=True,
                mirror=(sign == +1),
            )

        if sim:
            wg_access_side_hat = c << gf.components.straight(
                length=length_access_side,
                cross_section=cross_section_hat_side,
                width=width_out_side,
            )
            wg_access_side_hat.dmovex(taper_2_side.dxmax)
            wg_access_side_hat.dmovey(dy)

            absorber_side_hat = c << anwg_absorber(
                win=width_out_side,
                wout=width_out_side,
                taper_length=1,
                a=5.05,
                b=0.15,
                length_aux_st=1.0,
                cross_section=cross_section_hat_side,
            )
            absorber_side_hat.connect(
                "o1",
                wg_access_side_hat.ports["o2"],
                allow_layer_mismatch=True,
                allow_width_mismatch=True,
                mirror=(sign == +1),
            )

    # ---------------- trenches ----------------
    trench_top = c << gf.components.straight(
        length=length_total + length_input,
        cross_section=cross_section_trench,
        width=trench_width,
    )
    trench_top.dmovey((trench_gap + trench_width) / 2)
    trench_bot = c << gf.components.straight(
        length=length_total + length_input,
        cross_section=cross_section_trench,
        width=trench_width,
    )
    trench_bot.dmovey(-(trench_gap + trench_width) / 2)

    # ---------------- ports ----------------
    c.add_port(
        name="oaux1",
        orientation=180,
        center=(0, 0),
        layer=layer,
        width=width_in,
    )
    c.add_port(
        name="o1",
        orientation=0,
        center=(port_out_x, 0),
        layer=layer,
        width=width_out_taper_out,
    )

    c.flatten()
    return c


@gf.cell
def ec_sin2_strip_MAIN(
    trench_width: float = 20,
    trench_gap_in: float = 24,
    trench_gap_out: float = 20,
    length_input: float = 1,
    width_in: float = 0.15,
    dwidth_in: float = 0.1,
    width_out: float = 0.7,
    length_total: float = 400,
    length_1: float = 30,
    length_access: float = 1,
    m_1: float = 0.4,
    m_2: float = 0.9,
    n_points: float = 350,
    length_taper_out: float = 20,
    width_out_taper_out: float = 1.492,
    m_taper_out: float = 0.569565,
    n_points_taper_out: int = 100,
    cross_sections: list = [  # noqa: B006
        "strip",
        "nitride",
        "nitride2",
        "hat_nitride",
        "hat_nitride2",
    ],  # noqa: B006
    cross_section: str = "nitride2",
    layers: list = [LAYER.swg, LAYER.nwg, LAYER.anwg],  # noqa: B006
    sim: bool = True,
    access: bool = True,
):
    dwidth_in = make_even_third_decimal(dwidth_in)
    width_in = make_even_third_decimal(width_in)
    width_out = make_even_third_decimal(width_out)
    width_center = make_even_third_decimal(width_in + dwidth_in)
    width_out_taper_out = make_even_third_decimal(width_out_taper_out)
    trench_width = make_even_third_decimal(trench_width)
    trench_gap_in = make_even_third_decimal(trench_gap_in)
    trench_gap_out = make_even_third_decimal(trench_gap_out)

    if cross_section == cross_sections[0]:
        layer = layers[0]
    elif cross_section == cross_sections[1]:
        layer = layers[1]
        layer_hat = LAYER.HAT_NWG
        cross_section_hat = gf.cross_section.cross_section(
            width=width_out_taper_out,
            layer=layer_hat,
        )
    elif cross_section == cross_sections[2]:
        layer = layers[2]
        layer_hat = LAYER.HAT_AN
        cross_section_hat = gf.cross_section.cross_section(
            width=width_out_taper_out,
            layer=layer_hat,
        )

    length_rat = length_1 / length_total
    length_2 = length_total - length_1

    # --- constraint: width must be >= 0.25 by x = 100 ---
    x_check = 100.0
    x_local = x_check - length_input

    if x_local <= 0:
        width_at_check = width_in
    elif x_local <= length_1:
        width_at_check = taper_width_at(x_local, width_in, width_center, length_1, m_1)
    else:
        width_at_check = taper_width_at(
            x_local - length_1, width_center, width_out, length_2, m_2
        )

    min_width_required = 0.25
    if width_at_check < min_width_required:
        raise ValueError(
            f"Width at x={x_check} is {width_at_check:.4f}, below required minimum "
            f"of {min_width_required}. Adjust width_in, dwidth_in, length_1, m_1, or m_2."
        )

    n_points_1 = int(length_rat * n_points)
    n_points_2 = n_points - n_points_1

    c = gf.Component()

    taper_1 = c << taper_sin2(
        width_in=width_in,
        width_out=width_center,
        length=length_1,
        m_taper=m_1,
        n_points=n_points_1,
        cross_sections=cross_sections,
        cross_section=cross_section,
        layers=layers,
        sim=sim,
        access=False,
    )
    taper_1.dmovex(length_input)

    taper_2 = c << taper_sin2(
        width_in=width_center,
        width_out=width_out,
        length=length_2,
        m_taper=m_2,
        n_points=n_points_2,
        cross_sections=cross_sections,
        cross_section=cross_section,
        layers=layers,
        sim=sim,
        access=False,
    )
    taper_2.dmovex(taper_1.dxmax)

    taper_3 = c << taper_sin2(
        width_in=width_out,
        width_out=width_out_taper_out,
        length=length_taper_out,
        m_taper=m_taper_out,
        n_points=n_points_taper_out,
        cross_sections=cross_sections,
        cross_section=cross_section,
        layers=layers,
        sim=sim,
        access=False,
    )
    taper_3.dmovex(taper_2.dxmax)

    # --- half-trapezoid trenches ---
    # Outer edge horizontal; inner edge slopes so the gap goes
    #   trench_gap_in (input, x=0) -> trench_gap_out (output).
    # trench_width is measured on the larger side (the smaller-gap end).
    x0 = 0.0
    x1 = length_total + length_input
    inner_in = trench_gap_in / 2.0  # inner edge y at input
    inner_out = trench_gap_out / 2.0  # inner edge y at output
    outer_y = min(trench_gap_in, trench_gap_out) / 2.0 + trench_width

    top_trench = [
        (x0, inner_in),  # inner, input
        (x1, inner_out),  # inner, output
        (x1, outer_y),  # outer, output
        (x0, outer_y),  # outer, input
    ]
    c.add_polygon(top_trench, layer=LAYER.scrbo)
    c.add_polygon([(x, -y) for (x, y) in top_trench], layer=LAYER.scrbo)

    c.add_port(
        name="oaux1",
        orientation=180,
        center=(0, 0),
        layer=layer,
        width=width_in,
    )
    port_o2_x = taper_3.dxmax

    if sim:
        access = True
        length_access = 4

    if access:
        wg_access_out = c << gf.components.straight(
            length=length_access, cross_section=cross_section, width=width_out_taper_out
        )
        wg_access_out.dmovex(taper_3.dxmax)
        port_o2_x = wg_access_out.dxmax

    if sim:
        wg_access_out_hat = c << gf.components.straight(
            length=length_access,
            cross_section=cross_section_hat,
            width=width_out_taper_out,
        )
        wg_access_out_hat.dmovex(taper_3.dxmax)

    c.add_port(
        name="o1",
        orientation=0,
        center=(port_o2_x, 0),
        layer=layer,
        width=width_out_taper_out,
    )

    c.flatten()

    return c


@gf.cell
def ec_sin2_strip_MAIN_angled(
    trench_width: float = 20,
    trench_gap_in: float = 24,
    trench_gap_out: float = 20,
    length_input: float = 1,
    width_in: float = 0.15,
    dwidth_in: float = 0.1,
    width_out: float = 0.7,
    length_total: float = 400,
    length_1: float = 30,
    length_access: float = 1,
    m_1: float = 0.4,
    m_2: float = 0.9,
    n_points: float = 350,
    length_taper_out: float = 20,
    width_out_taper_out: float = 1.492,
    m_taper_out: float = 0.569565,
    n_points_taper_out: int = 100,
    cross_sections: list = [  # noqa: B006
        "strip",
        "nitride",
        "nitride2",
        "hat_nitride",
        "hat_nitride2",
    ],  # noqa: B006
    cross_section: str = "nitride2",
    layers: list = [LAYER.swg, LAYER.nwg, LAYER.anwg],  # noqa: B006
    sim: bool = True,
    access: bool = True,
    angle: float = 8.0,
    radius: float = 100.0,
    length_straight: float = 2.5,
) -> gf.Component:
    """Angled version of ec_sin2_strip_MAIN.

    Builds the straight taper, rotates it by `angle`, then adds an
    euler bend (radius = `radius`, default 100 um) at o2 that cancels
    the rotation so the output port exits perfectly horizontal again.
    A trench "patch" (same layer as the sin2 trenches, LAYER.scrbo) is
    added at o1 so the tilted trench edge is re-squared to a straight,
    die-facet-compatible edge, exactly mirroring the ec_rib_angled
    pattern.
    """

    # ------------------------------------------------------------------ #
    # 1.  Build the straight (un-rotated) taper
    # ------------------------------------------------------------------ #
    ec = ec_sin2_strip_MAIN(
        trench_width=trench_width,
        trench_gap_in=trench_gap_in,
        trench_gap_out=trench_gap_out,
        length_input=length_input,
        width_in=width_in,
        dwidth_in=dwidth_in,
        width_out=width_out,
        length_total=length_total,
        length_1=length_1,
        length_access=length_access,
        m_1=m_1,
        m_2=m_2,
        n_points=n_points,
        length_taper_out=length_taper_out,
        width_out_taper_out=width_out_taper_out,
        m_taper_out=m_taper_out,
        n_points_taper_out=n_points_taper_out,
        cross_sections=cross_sections,
        cross_section=cross_section,
        layers=layers,
        sim=sim,
        access=access,
    )

    # pull width/layer straight from the built ports so we don't have
    # to duplicate the cross_section -> layer branching logic
    layer_in = ec.ports["oaux1"].layer
    layer_out = ec.ports["o1"].layer
    width_in_port = ec.ports["oaux1"].width
    width_out_port = ec.ports["o1"].width

    # ------------------------------------------------------------------ #
    # 2.  Intermediate component: rotated taper + bend + patch
    # ------------------------------------------------------------------ #
    c = gf.Component()

    # capture original (pre-rotation) bbox corners (o1 sits at x=0/xmin)
    x0, y0 = ec.xmin, ec.ymin
    _, y1 = ec.xmax, ec.ymax

    ec_ref = c << ec
    ec_ref.rotate(angle)
    c.ports = {}

    o1_center = ec_ref["oaux1"].center
    o2_ref_port = ec_ref["o1"]

    # ------------------------------------------------------------------ #
    # 3.  Bend at o2 (radius = 100 um by default) - cancels the rotation
    #     so o2 exits perfectly straight (orientation = 0) again
    # ------------------------------------------------------------------ #
    if angle != 0.0:
        bend_xs = gf.CrossSection(
            sections=[
                gf.Section(
                    width=width_out_port, layer=layer_out, port_names=("o1", "o2")
                )
            ],
            radius=radius,
            radius_min=0,
        )
        bend = gf.components.bend_euler(
            angle=-angle,
            radius=radius,
            cross_section=bend_xs,
            allow_min_radius_violation=True,
        )
        bend_ref = c << bend
        bend_ref.connect(
            "o1", o2_ref_port, allow_layer_mismatch=True, allow_width_mismatch=True
        )
        c.ports = {}
        o2_center = bend_ref["o2"].center
        o2_orient = bend_ref["o2"].orientation
    else:
        o2_center = o2_ref_port.center
        o2_orient = o2_ref_port.orientation

    # ------------------------------------------------------------------ #
    # 4.  Patch at o1 - exact rotated corners + extendable straight section.
    #     Re-squares the tilted trench edge (LAYER.scrbo) back to a
    #     vertical die-facet, mirroring ec_rib_angled's layer_DT patch.
    # ------------------------------------------------------------------ #
    angle_rad = np.deg2rad(angle)
    cos_a, sin_a = np.cos(angle_rad), np.sin(angle_rad)

    def rot(x, y):
        return (x * cos_a - y * sin_a, x * sin_a + y * cos_a)

    top_left = rot(x0, y1)
    bot_left = rot(x0, y0)

    x_far = min(top_left[0], bot_left[0]) - length_straight  # push further left

    overlap = 0.05  # um, guarantees no gap after boolean cut

    patch_left = [
        (x_far, top_left[1]),
        (top_left[0] + overlap, top_left[1]),
        (bot_left[0] + overlap, bot_left[1]),
        (x_far, bot_left[1]),
    ]

    c_patch = gf.Component()
    c_patch.add_polygon(patch_left, layer=LAYER.scrbo)

    # cut_height uses trench_gap_in since the patch sits at the o1
    # (input, x=0) side of the taper
    cut_height = trench_gap_in
    cut_x_max = max(top_left[0], bot_left[0]) + overlap + 1
    cut_rect = [
        (x_far - 1, -cut_height / 2),
        (cut_x_max, -cut_height / 2),
        (cut_x_max, cut_height / 2),
        (x_far - 1, cut_height / 2),
    ]
    c_cut = gf.Component()
    c_cut.add_polygon(cut_rect, layer=LAYER.scrbo)

    c_patch_final = gf.boolean(c_patch, c_cut, operation="not", layer=LAYER.scrbo)
    c.add_ref(c_patch_final)

    o1_x = x_far

    # ------------------------------------------------------------------ #
    # 5.  Outer wrapper - fresh component, ports assigned here only
    # ------------------------------------------------------------------ #
    c_angled = gf.Component()
    c_angled.add_ref(c)

    c_angled.add_port(
        name="oaux1",
        orientation=180,
        center=(o1_x, o1_center[1]),
        layer=layer_in,
        width=width_in_port,
    )
    c_angled.add_port(
        name="o1",
        orientation=o2_orient,
        center=o2_center,
        layer=layer_out,
        width=width_out_port,
    )

    c_angled.flatten()
    return c_angled
