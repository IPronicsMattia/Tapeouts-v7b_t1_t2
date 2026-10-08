import gdsfactory as gf
import iprlayout_tower as ipr
from iprlayout_tower.tower_tech import LAYER

import v7b
import v7b.tools.circle_connect as circle_connect
from v7b.pdk import dc_connector, fill_named_rectangles_fast
from v7b.tools.circle_connect import Fallback


def electrical_routing(
    die: gf.Component,
) -> None:
    """This function places the electrical routing in the DIE"""

    die = gf.get_component(die)
    pdk = ipr.get_pdk()
    pdk.activate()

    #############################
    # CROSS-SECTIONS            #
    #############################
    xs_m3_11 = gf.get_cross_section("metal3", width=11)
    xs_m2_10 = gf.get_cross_section("metal2", width=10)
    xs_m1_10 = gf.get_cross_section("metal1", width=10)

    #############################
    # COMPONENTS                #
    #############################
    metal2_taper = gf.c.taper(
        5,
        width1=10,
        width2=11,
        port_types=("electrical", "electrical"),
        port_names=("e1", "e2"),
        layer=LAYER.metal2,
    )
    metal1_taper = gf.c.taper(
        5,
        width1=10,
        width2=11,
        port_types=("electrical", "electrical"),
        port_names=("e1", "e2"),
        layer=LAYER.metal1,
    )
    via1 = gf.partial(
        gf.c.via,
        layer=LAYER.via1,
        size=(0.2, 0.2),
        pitch=0.74,
        enclosure=0.46,
    )
    via2 = gf.partial(
        gf.c.via,
        layer=LAYER.via2,
        size=(0.36, 0.36),
        pitch=0.9,
        enclosure=0.69,
    )
    via_m2_m1 = gf.c.via_stack(
        layers=(LAYER.metal1, LAYER.metal2), vias=(via1, None), size=(10, 10)
    )
    via_m3_m2 = gf.c.via_stack(
        layers=(LAYER.metal2, LAYER.metal3), vias=(via2, None), size=(11, 11)
    )
    via_m3_m1 = gf.c.via_stack(
        layers=(LAYER.metal1, LAYER.metal2, LAYER.metal3),
        vias=(via1, via2, None),
        size=(11, 11),
    )

    #############################
    # PUC & PAD MATRIX          #
    #############################
    search_area = (-11203.084, -9699.12, 11835.24, 9770.7)
    puc_matrix = v7b.build_matrix(die, "puc*", "puc\\d+", area=search_area)
    pad_matrix = v7b.build_matrix(die, "flipchip_pad*", area=search_area)

    #############################
    # COMMON GROUND 9X9         #
    #############################
    METAL3_SHORT_WIDTH = 245.656
    METAL3_LONG_WIDTH = 425.656
    METAL3_HEIGHT = 65.656
    PAD_OFFSET = 32.828

    def _place_metal3_fill(width, pad_col, pad_row, vertical=False):
        size = (METAL3_HEIGHT, width) if vertical else (width, METAL3_HEIGHT)
        rect = die << gf.c.rectangle(size, LAYER.metal3, port_type=None)
        pad = pad_matrix[pad_col][pad_row]
        if vertical:
            rect.move((rect.x, rect.ymax), (pad.x, pad.y + PAD_OFFSET))
        else:
            rect.move((rect.xmin, rect.y), (pad.x - PAD_OFFSET, pad.y))
        return pad

    # PAD JOIN
    for row_offset in (0, 94):
        for i in range(12):
            for j in range(8):
                if (j + 1) % 3 != 0:
                    _place_metal3_fill(
                        METAL3_SHORT_WIDTH, 18 * i + j * 2, 49 + row_offset
                    )
                if j == 0:
                    _place_metal3_fill(METAL3_LONG_WIDTH, 1 + 18 * i, 48 + row_offset)
                _place_metal3_fill(
                    METAL3_LONG_WIDTH, 3 + j * 2 + 18 * i, 48 + row_offset
                )
            for j in range(3):
                _place_metal3_fill(
                    METAL3_SHORT_WIDTH, 4 + j * 6 + 18 * i, 47 + row_offset
                )
                _place_metal3_fill(
                    METAL3_SHORT_WIDTH, 4 + j * 6 + 18 * i, 51 + row_offset
                )

    # PUC TO PAD
    for j in range(2):
        for i in range(72):
            # LEFT SIDE
            ### PUC UP RIGHT
            if i % 2 == 0:
                length = (
                    pad_matrix[0][j * 94 + 49].x
                    - puc_matrix[0][17 * j + 8]["e3"].x / 1000
                )
            else:
                length = (
                    pad_matrix[3][j * 94 + 48].x
                    - puc_matrix[6][17 * j + 8]["e3"].x / 1000
                )
            st_ref = die << gf.c.straight(length, cross_section=xs_m3_11)
            st_ref.move(
                (st_ref.xmin, st_ref.y),
                (
                    puc_matrix[0 + 6 * i][8 + 17 * j]["e3"].x / 1000 + 5.5,
                    puc_matrix[0 + 6 * i][8 + 17 * j]["e3"].y / 1000 - 5.5,
                ),
            )

            st_ref = die << gf.c.straight(length, cross_section=xs_m3_11)
            st_ref.move(
                (st_ref.xmin, st_ref.y),
                (
                    puc_matrix[0 + 6 * i][8 + 17 * j]["e4"].x / 1000 + 5.5,
                    puc_matrix[0 + 6 * i][8 + 17 * j]["e4"].y / 1000 + 5.5,
                ),
            )
            bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m3_11)
            bend_ref.connect("e1", st_ref["e2"])

            ### PUC UP LEFT
            st_ref = die << gf.c.straight(8.761, cross_section=xs_m3_11)
            st_ref.connect("e1", puc_matrix[0 + 6 * i][6 + 17 * j]["e4"])
            bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m3_11)
            bend_ref.connect("e1", st_ref["e2"])
            if i % 2 == 0:
                st_ref = die << gf.c.straight(
                    pad_matrix[0][j * 94 + 49].x - bend_ref["e2"].x + 50,
                    cross_section=xs_m3_11,
                )
            else:
                st_ref = die << gf.c.straight(
                    pad_matrix[3][j * 94 + 48].x - bend_ref["e2"].x + 50,
                    cross_section=xs_m3_11,
                )

            st_ref.connect("e1", bend_ref["e2"])
            bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m3_11)
            bend_ref.connect("e1", st_ref["e2"])
            st_ref = die << gf.c.straight(32, cross_section=xs_m3_11)
            st_ref.connect("e1", bend_ref["e2"])

            st_ref = die << gf.c.straight(7.35, cross_section=xs_m3_11)
            st_ref.connect("e1", puc_matrix[0 + 6 * i][6 + 17 * j]["e3"])
            bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m3_11)
            bend_ref.connect("e1", st_ref["e2"], mirror=True)
            if i % 2 == 0:
                st_ref = die << gf.c.straight(
                    pad_matrix[0][j * 94 + 49].x - bend_ref["e2"].x,
                    cross_section=xs_m3_11,
                )
            else:
                st_ref = die << gf.c.straight(
                    pad_matrix[3][j * 94 + 48].x - bend_ref["e2"].x,
                    cross_section=xs_m3_11,
                )
            st_ref.connect("e1", bend_ref["e2"])

            ### PUC UP MIDDLE
            if i % 2 == 0:
                length = (
                    pad_matrix[1][j * 94 + 48].x
                    - puc_matrix[1][7 + 17 * j]["e3"].x / 1000
                )
            else:
                length = (
                    pad_matrix[4][j * 94 + 47].x
                    - puc_matrix[1][7 + 17 * j]["e3"].x / 1000
                )
            st_ref = die << gf.c.straight(length, cross_section=xs_m3_11)
            st_ref.move(
                (st_ref.xmin, st_ref.y),
                (
                    puc_matrix[1 + 6 * i][7 + 17 * j]["e3"].x / 1000 + 5.5,
                    puc_matrix[1 + 6 * i][7 + 17 * j]["e3"].y / 1000 - 5.5,
                ),
            )

            st_ref = die << gf.c.straight(length, cross_section=xs_m3_11)
            st_ref.move(
                (st_ref.xmin, st_ref.y),
                (
                    puc_matrix[1 + 6 * i][7 + 17 * j]["e4"].x / 1000 + 5.5,
                    puc_matrix[1 + 6 * i][7 + 17 * j]["e4"].y / 1000 + 5.5,
                ),
            )

            ### PUC LOW RIGHT
            if i % 2 == 0:
                length = (
                    pad_matrix[2][j * 94 + 49].x
                    - puc_matrix[3][8 + 17 * j]["e3"].x / 1000
                )
            else:
                length = (
                    pad_matrix[5][j * 94 + 48].x
                    - puc_matrix[3][8 + 17 * j]["e3"].x / 1000
                )

            st_ref = die << gf.c.straight(length, cross_section=xs_m3_11)
            st_ref.move(
                (st_ref.xmin, st_ref.y),
                (
                    puc_matrix[3 + 6 * i][8 + 17 * j]["e3"].x / 1000 + 5.5,
                    puc_matrix[3 + 6 * i][8 + 17 * j]["e3"].y / 1000 - 5.5,
                ),
            )
            bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m3_11)
            bend_ref.connect("e1", st_ref["e2"], mirror=True)

            st_ref = die << gf.c.straight(20, cross_section=xs_m3_11)

            st_ref.connect("e1", bend_ref["e2"])
            st_ref = die << gf.c.straight(length, cross_section=xs_m3_11)
            st_ref.move(
                (st_ref.xmin, st_ref.y),
                (
                    puc_matrix[3 + 6 * i][8 + 17 * j]["e4"].x / 1000 + 5.5,
                    puc_matrix[3 + 6 * i][8 + 17 * j]["e4"].y / 1000 + 5.5,
                ),
            )

            ### PUC LOW LEFT
            st_ref = die << gf.c.straight(10.172, cross_section=xs_m3_11)
            st_ref.connect("e1", puc_matrix[3 + 6 * i][6 + 17 * j]["e3"])
            bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m3_11)
            bend_ref.connect("e1", st_ref["e2"], mirror=True)
            if i % 2 == 0:
                length = pad_matrix[1][j * 94 + 48].x - bend_ref["e2"].x
            else:
                length = pad_matrix[4][j * 94 + 47].x - bend_ref["e2"].x
            st_ref = die << gf.c.straight(length, cross_section=xs_m3_11)
            st_ref.connect("e1", bend_ref["e2"])

            st_ref = die << gf.c.straight(7.35, cross_section=xs_m3_11)
            st_ref.connect("e1", puc_matrix[3 + 6 * i][6 + 17 * j]["e4"])
            bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m3_11)
            bend_ref.connect("e1", st_ref["e2"])
            st_ref = die << gf.c.straight(121.402, cross_section=xs_m3_11)
            st_ref.connect("e1", bend_ref["e2"])
            via_ref = die << via_m3_m2
            via_ref.connect("e1", st_ref["e2"])
            tap_ref = die << metal2_taper
            tap_ref.connect("e2", via_ref["e3"], allow_layer_mismatch=True)
            st_ref = die << gf.c.straight(20, cross_section=xs_m2_10)
            st_ref.connect("e1", tap_ref["e1"])
            bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m2_10)
            bend_ref.connect("e1", st_ref["e2"])
            st_ref = die << gf.c.straight(58.672, cross_section=xs_m2_10)
            st_ref.connect("e1", bend_ref["e2"])
            bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m2_10)
            bend_ref.connect("e1", st_ref["e2"], mirror=True)
            st_ref = die << gf.c.straight(20, cross_section=xs_m2_10)
            st_ref.connect("e1", bend_ref["e2"])
            tap_ref = die << metal2_taper
            tap_ref.connect("e1", st_ref["e2"])
            via_ref = die << via_m3_m2
            via_ref.connect("e1", tap_ref["e2"], allow_layer_mismatch=True)
            if i % 2 == 0:
                length = pad_matrix[1][j * 94 + 48].x - via_ref["e3"].x + 5
            else:
                length = pad_matrix[4][j * 94 + 47].x - via_ref["e3"].x + 5
            st_ref = die << gf.c.straight(length, cross_section=xs_m3_11)
            st_ref.connect("e1", via_ref["e3"])

            ### PUC LOW MIDDLE
            if i % 2 == 0:
                length = (
                    pad_matrix[2][j * 94 + 49].x
                    - puc_matrix[5][7 + 17 * j]["e3"].x / 1000
                )
            else:
                length = (
                    pad_matrix[5][j * 94 + 48].x
                    - puc_matrix[5][7 + 17 * j]["e3"].x / 1000
                )
            st_ref = die << gf.c.straight(length, cross_section=xs_m3_11)
            st_ref.move(
                (st_ref.xmin, st_ref.y),
                (
                    puc_matrix[5 + 6 * i][7 + 17 * j]["e3"].x / 1000 + 5.5,
                    puc_matrix[5 + 6 * i][7 + 17 * j]["e3"].y / 1000 - 5.5,
                ),
            )

            st_ref = die << gf.c.straight(66, cross_section=xs_m3_11)
            st_ref.move(
                (st_ref.xmin, st_ref.y),
                (
                    puc_matrix[5 + 6 * i][7 + 17 * j]["e4"].x / 1000 + 5.5,
                    puc_matrix[5 + 6 * i][7 + 17 * j]["e4"].y / 1000 + 5.5,
                ),
            )
            bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m3_11)
            bend_ref.connect("e1", st_ref["e2"])
            st_ref = die << gf.c.straight(26.15, cross_section=xs_m3_11)
            st_ref.connect("e1", bend_ref["e2"])
            bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m3_11)
            bend_ref.connect("e1", st_ref["e2"], mirror=True)
            if i % 2 == 0:
                length = pad_matrix[2][j * 94 + 49].x - bend_ref["e2"].x
            else:
                length = pad_matrix[5][j * 94 + 48].x - bend_ref["e2"].x
            st_ref = die << gf.c.straight(length, cross_section=xs_m3_11)
            st_ref.connect("e1", bend_ref["e2"])

            # RIGHT SIDE
            ### PUC UP LEFT
            if i % 2 == 0:
                length = (
                    puc_matrix[0][17 * j + 9]["e2"].x / 1000
                    - pad_matrix[0][j * 94 + 51].x
                )
            else:
                length = (
                    puc_matrix[6][17 * j + 9]["e2"].x / 1000
                    - pad_matrix[3][j * 94 + 52].x
                )
            st_ref = die << gf.c.straight(length, cross_section=xs_m3_11)
            st_ref.move(
                (st_ref.xmax, st_ref.y),
                (
                    puc_matrix[0 + 6 * i][9 + 17 * j]["e2"].x / 1000 - 5.5,
                    puc_matrix[0 + 6 * i][9 + 17 * j]["e2"].y / 1000 - 5.5,
                ),
            )

            st_ref = die << gf.c.straight(length, cross_section=xs_m3_11)
            st_ref.move(
                (st_ref.xmax, st_ref.y),
                (
                    puc_matrix[0 + 6 * i][9 + 17 * j]["e1"].x / 1000 - 5.5,
                    puc_matrix[0 + 6 * i][9 + 17 * j]["e1"].y / 1000 + 5.5,
                ),
            )
            bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m3_11)
            bend_ref.connect("e1", st_ref["e1"], mirror=True)

            ### PUC UP RIGHT
            st_ref = die << gf.c.straight(8.761, cross_section=xs_m3_11)
            st_ref.connect("e1", puc_matrix[0 + 6 * i][11 + 17 * j]["e1"])
            bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m3_11)
            bend_ref.connect("e1", st_ref["e2"], mirror=True)
            if i % 2 == 0:
                st_ref = die << gf.c.straight(
                    bend_ref["e2"].x - pad_matrix[0][j * 94 + 51].x + 50,
                    cross_section=xs_m3_11,
                )
            else:
                st_ref = die << gf.c.straight(
                    bend_ref["e2"].x - pad_matrix[3][j * 94 + 52].x + 50,
                    cross_section=xs_m3_11,
                )

            st_ref.connect("e1", bend_ref["e2"])
            bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m3_11)
            bend_ref.connect("e1", st_ref["e2"], mirror=True)
            st_ref = die << gf.c.straight(32, cross_section=xs_m3_11)
            st_ref.connect("e1", bend_ref["e2"])

            st_ref = die << gf.c.straight(7.35, cross_section=xs_m3_11)
            st_ref.connect("e1", puc_matrix[0 + 6 * i][11 + 17 * j]["e2"])
            bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m3_11)
            bend_ref.connect("e1", st_ref["e2"])
            if i % 2 == 0:
                st_ref = die << gf.c.straight(
                    bend_ref["e2"].x - pad_matrix[0][j * 94 + 51].x,
                    cross_section=xs_m3_11,
                )
            else:
                st_ref = die << gf.c.straight(
                    bend_ref["e2"].x - pad_matrix[3][j * 94 + 52].x,
                    cross_section=xs_m3_11,
                )
            st_ref.connect("e1", bend_ref["e2"])

            ### PUC UP MIDDLE
            if i % 2 == 0:
                length = (
                    puc_matrix[1][10 + 17 * j]["e2"].x / 1000
                    - pad_matrix[1][j * 94 + 52].x
                )
            else:
                length = (
                    puc_matrix[1][10 + 17 * j]["e2"].x / 1000
                    - pad_matrix[4][j * 94 + 53].x
                )
            st_ref = die << gf.c.straight(length, cross_section=xs_m3_11)
            st_ref.move(
                (st_ref.xmax, st_ref.y),
                (
                    puc_matrix[1 + 6 * i][10 + 17 * j]["e2"].x / 1000 - 5.5,
                    puc_matrix[1 + 6 * i][10 + 17 * j]["e2"].y / 1000 - 5.5,
                ),
            )

            st_ref = die << gf.c.straight(length, cross_section=xs_m3_11)
            st_ref.move(
                (st_ref.xmax, st_ref.y),
                (
                    puc_matrix[1 + 6 * i][10 + 17 * j]["e1"].x / 1000 - 5.5,
                    puc_matrix[1 + 6 * i][10 + 17 * j]["e1"].y / 1000 + 5.5,
                ),
            )

            ### PUC LOW LEFT
            if i % 2 == 0:
                length = (
                    puc_matrix[3][9 + 17 * j]["e2"].x / 1000
                    - pad_matrix[2][j * 94 + 51].x
                )
            else:
                length = (
                    puc_matrix[3][9 + 17 * j]["e2"].x / 1000
                    - pad_matrix[5][j * 94 + 52].x
                )

            st_ref = die << gf.c.straight(length, cross_section=xs_m3_11)
            st_ref.move(
                (st_ref.xmax, st_ref.y),
                (
                    puc_matrix[3 + 6 * i][9 + 17 * j]["e2"].x / 1000 - 5.5,
                    puc_matrix[3 + 6 * i][9 + 17 * j]["e2"].y / 1000 - 5.5,
                ),
            )
            bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m3_11)
            bend_ref.connect("e1", st_ref["e1"])

            st_ref = die << gf.c.straight(20, cross_section=xs_m3_11)

            st_ref.connect("e1", bend_ref["e2"])
            st_ref = die << gf.c.straight(length, cross_section=xs_m3_11)
            st_ref.move(
                (st_ref.xmax, st_ref.y),
                (
                    puc_matrix[3 + 6 * i][9 + 17 * j]["e1"].x / 1000 - 5.5,
                    puc_matrix[3 + 6 * i][9 + 17 * j]["e1"].y / 1000 + 5.5,
                ),
            )

            ### PUC LOW RIGHT
            st_ref = die << gf.c.straight(10.172, cross_section=xs_m3_11)
            st_ref.connect("e1", puc_matrix[3 + 6 * i][11 + 17 * j]["e2"])
            bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m3_11)
            bend_ref.connect("e1", st_ref["e2"])
            if i % 2 == 0:
                length = bend_ref["e2"].x - pad_matrix[1][j * 94 + 52].x
            else:
                length = bend_ref["e2"].x - pad_matrix[4][j * 94 + 53].x
            st_ref = die << gf.c.straight(length, cross_section=xs_m3_11)
            st_ref.connect("e1", bend_ref["e2"])

            st_ref = die << gf.c.straight(7.35, cross_section=xs_m3_11)
            st_ref.connect("e1", puc_matrix[3 + 6 * i][11 + 17 * j]["e1"])
            bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m3_11)
            bend_ref.connect("e1", st_ref["e2"], mirror=True)
            st_ref = die << gf.c.straight(121.402, cross_section=xs_m3_11)
            st_ref.connect("e1", bend_ref["e2"])
            via_ref = die << via_m3_m2
            via_ref.connect("e1", st_ref["e2"])
            tap_ref = die << metal2_taper
            tap_ref.connect("e2", via_ref["e3"], allow_layer_mismatch=True)
            st_ref = die << gf.c.straight(20, cross_section=xs_m2_10)
            st_ref.connect("e1", tap_ref["e1"])
            bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m2_10)
            bend_ref.connect("e1", st_ref["e2"], mirror=True)
            st_ref = die << gf.c.straight(58.672, cross_section=xs_m2_10)
            st_ref.connect("e1", bend_ref["e2"])
            bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m2_10)
            bend_ref.connect("e1", st_ref["e2"])
            st_ref = die << gf.c.straight(20, cross_section=xs_m2_10)
            st_ref.connect("e1", bend_ref["e2"])
            tap_ref = die << metal2_taper
            tap_ref.connect("e1", st_ref["e2"])
            via_ref = die << via_m3_m2
            via_ref.connect("e1", tap_ref["e2"], allow_layer_mismatch=True)
            if i % 2 == 0:
                length = via_ref["e3"].x + 5 - pad_matrix[1][j * 94 + 52].x
            else:
                length = via_ref["e3"].x + 5 - pad_matrix[4][j * 94 + 53].x
            st_ref = die << gf.c.straight(length, cross_section=xs_m3_11)
            st_ref.connect("e1", via_ref["e3"])

            ### PUC LOW MIDDLE
            if i % 2 == 0:
                length = (
                    puc_matrix[5][10 + 17 * j]["e2"].x / 1000
                    - pad_matrix[2][j * 94 + 51].x
                )
            else:
                length = (
                    puc_matrix[5][10 + 17 * j]["e2"].x / 1000
                    - pad_matrix[5][j * 94 + 52].x
                )

            st_ref = die << gf.c.straight(length, cross_section=xs_m3_11)
            st_ref.move(
                (st_ref.xmax, st_ref.y),
                (
                    puc_matrix[5 + 6 * i][10 + 17 * j]["e2"].x / 1000 - 5.5,
                    puc_matrix[5 + 6 * i][10 + 17 * j]["e2"].y / 1000 - 5.5,
                ),
            )

            st_ref = die << gf.c.straight(66, cross_section=xs_m3_11)
            st_ref.move(
                (st_ref.xmax, st_ref.y),
                (
                    puc_matrix[5 + 6 * i][10 + 17 * j]["e1"].x / 1000 - 5.5,
                    puc_matrix[5 + 6 * i][10 + 17 * j]["e1"].y / 1000 + 5.5,
                ),
            )
            bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m3_11)
            bend_ref.connect("e1", st_ref["e1"], mirror=True)
            st_ref = die << gf.c.straight(26.15, cross_section=xs_m3_11)
            st_ref.connect("e1", bend_ref["e2"])
            bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m3_11)
            bend_ref.connect("e1", st_ref["e2"])
            if i % 2 == 0:
                length = bend_ref["e2"].x - pad_matrix[2][j * 94 + 51].x
            else:
                length = bend_ref["e2"].x - pad_matrix[5][j * 94 + 52].x
            st_ref = die << gf.c.straight(length, cross_section=xs_m3_11)
            st_ref.connect("e1", bend_ref["e2"])

    #############################
    # SIGNALS 9X9               #
    #############################
    for j in range(2):
        for i in range(72):
            pad_shift = 0 if i % 2 == 0 else 1
            # LEFT SIDE
            ### PUC
            for m in range(2):
                row = 6 * i if m == 0 else 3 + 6 * i
                for k in range(2):
                    st_ref = die << gf.c.straight(118.197, cross_section=xs_m3_11)
                    port = "e2" if k == 0 else "e1"
                    aux = 1 if k == 0 else -1
                    st_ref.move(
                        (st_ref.xmax, st_ref.y),
                        (
                            puc_matrix[row][8 + j * 17][port].x / 1000 - 5.5,
                            puc_matrix[row][8 + j * 17][port].y / 1000 - 5.5 * aux,
                        ),
                    )
                    via_ref = die << via_m3_m2
                    via_ref.connect("e1", st_ref["e1"])
                    tap_ref = die << metal2_taper
                    tap_ref.connect("e2", via_ref["e3"], allow_layer_mismatch=True)
                    st_ref = die << gf.c.straight(20, cross_section=xs_m2_10)
                    st_ref.connect("e1", tap_ref["e1"])
                    bend_ref = die << ipr.wire_corner45(
                        radius=2, cross_section=xs_m2_10
                    )
                    bend_ref.connect("e1", st_ref["e2"], mirror=k == 0)
                    st_ref = die << gf.c.straight(14.175, cross_section=xs_m2_10)
                    st_ref.connect("e1", bend_ref["e2"])
                    bend_ref = die << ipr.wire_corner45(
                        radius=2, cross_section=xs_m2_10
                    )
                    bend_ref.connect("e1", st_ref["e2"], mirror=k != 0)
                    st_ref = die << gf.c.straight(131.399, cross_section=xs_m2_10)
                    st_ref.connect("e1", bend_ref["e2"])
                    via_ref = die << via_m2_m1
                    via_ref.connect("e1", st_ref["e2"])

                    # per (m, k): pad row offset, column (pad_shift sign varies)
                    pad_row, pad_col = {
                        (0, 0): (3 * i, 39 + pad_shift),
                        (0, 1): (3 * i, 41 + pad_shift),
                        (1, 0): (1 + 3 * i, 44 - pad_shift),
                        (1, 1): (2 + 3 * i, 43 + pad_shift),
                    }[m, k]
                    pad = pad_matrix[pad_row][pad_col + 94 * j]

                    st_ref = die << gf.c.straight(
                        via_ref["e3"].x - pad.x - 70,
                        cross_section=xs_m1_10,
                    )
                    st_ref.connect("e1", via_ref["e3"], allow_layer_mismatch=True)
                    tap_ref = die << metal1_taper
                    tap_ref.connect("e1", st_ref["e2"])
                    via_ref = die << via_m3_m1
                    via_ref.connect("e1", tap_ref["e2"], allow_layer_mismatch=True)
                    if m == 0:
                        dest = (
                            pad["e1"]
                            if k == 0
                            else gf.Port(
                                "e1",
                                width=11,
                                layer=LAYER.metal3,
                                port_type="electrical",
                                center=(pad.x, pad.y),
                                orientation=270,
                            )
                        )
                        gf.routing.route_single(
                            die,
                            via_ref["e3"],
                            dest,
                            bend=ipr.wire_corner45(xs_m3_11),
                            auto_taper=False,
                            cross_section=xs_m3_11,
                        )
                    else:
                        st_ref = die << gf.c.straight(
                            via_ref["e3"].x - pad.x,
                            cross_section=xs_m3_11,
                        )
                        st_ref.connect("e1", via_ref["e3"], allow_layer_mismatch=True)

                    ### PUC
                    aux = puc_matrix[6 * i][6 + j * 17]["e2"]
                    port = gf.Port(
                        "e1",
                        width=11,
                        layer=LAYER.metal3,
                        port_type="electrical",
                        center=(aux.x / 1000 - 5.5, aux.y / 1000 - 5.5),
                        orientation=180,
                    )
                    st_ref = die << gf.c.straight(20, cross_section=xs_m3_11)
                    st_ref.connect("e1", port)
                    via_ref = die << via_m3_m1
                    via_ref.connect("e1", st_ref["e2"])
                    tap_ref = die << metal1_taper
                    tap_ref.connect("e2", via_ref["e3"], allow_layer_mismatch=True)
                    st_ref = die << gf.c.straight(
                        tap_ref["e1"].x
                        - pad_matrix[3 * i][43 + pad_shift + 94 * j].x
                        - 70,
                        cross_section=xs_m1_10,
                    )
                    st_ref.connect("e1", tap_ref["e1"])
                    tap_ref = die << metal1_taper
                    tap_ref.connect("e1", st_ref["e2"])
                    via_ref = die << via_m3_m1
                    via_ref.connect("e1", tap_ref["e2"], allow_layer_mismatch=True)
                    st_ref = die << gf.c.straight(
                        via_ref["e3"].x - pad_matrix[3 * i][43 + pad_shift + 94 * j].x,
                        cross_section=xs_m3_11,
                    )
                    st_ref.connect("e1", via_ref["e3"])

                    aux = puc_matrix[6 * i][6 + j * 17]["e1"]
                    port1 = gf.Port(
                        "e1",
                        width=11,
                        layer=LAYER.metal3,
                        port_type="electrical",
                        center=(aux.x / 1000 - 5.5, aux.y / 1000 + 5.5),
                        orientation=180,
                    )
                    aux = pad_matrix[3 * i][45 + pad_shift + 94 * j]
                    port2 = gf.Port(
                        "e1",
                        width=11,
                        layer=LAYER.metal3,
                        port_type="electrical",
                        center=(aux.x + 10, aux.y),
                        orientation=270,
                    )
                    gf.routing.route_single(
                        die,
                        port1,
                        port2,
                        bend=ipr.wire_corner45(xs_m3_11),
                        auto_taper=False,
                        cross_section=xs_m3_11,
                    )

                    ### PUC
                    aux = puc_matrix[1 + 6 * i][7 + j * 17]["e2"]
                    port = gf.Port(
                        "e1",
                        width=11,
                        layer=LAYER.metal3,
                        port_type="electrical",
                        center=(aux.x / 1000 - 5.5, aux.y / 1000 - 5.5),
                        orientation=180,
                    )
                    st_ref = die << gf.c.straight(20, cross_section=xs_m3_11)
                    st_ref.connect("e1", port)
                    via_ref = die << via_m3_m1
                    via_ref.connect("e1", st_ref["e2"])
                    tap_ref = die << metal1_taper
                    tap_ref.connect("e2", via_ref["e3"], allow_layer_mismatch=True)
                    st_ref = die << gf.c.straight(
                        tap_ref["e1"].x
                        - pad_matrix[1 + 3 * i][40 - pad_shift + 94 * j].x
                        - 70,
                        cross_section=xs_m1_10,
                    )
                    st_ref.connect("e1", tap_ref["e1"])
                    tap_ref = die << metal1_taper
                    tap_ref.connect("e1", st_ref["e2"])
                    via_ref = die << via_m3_m1
                    via_ref.connect("e1", tap_ref["e2"], allow_layer_mismatch=True)
                    gf.routing.route_single(
                        die,
                        via_ref["e3"],
                        pad_matrix[1 + 3 * i][40 - pad_shift + 94 * j]["e1"],
                        bend=ipr.wire_corner45(xs_m3_11),
                        auto_taper=False,
                        cross_section=xs_m3_11,
                    )

                    aux = puc_matrix[1 + 6 * i][7 + j * 17]["e1"]
                    port = gf.Port(
                        "e1",
                        width=11,
                        layer=LAYER.metal3,
                        port_type="electrical",
                        center=(aux.x / 1000 - 5.5, aux.y / 1000 + 5.5),
                        orientation=180,
                    )
                    st_ref = die << gf.c.straight(20, cross_section=xs_m3_11)
                    st_ref.connect("e1", port)
                    via_ref = die << via_m3_m1
                    via_ref.connect("e1", st_ref["e2"])
                    tap_ref = die << metal1_taper
                    tap_ref.connect("e2", via_ref["e3"], allow_layer_mismatch=True)
                    st_ref = die << gf.c.straight(
                        tap_ref["e1"].x
                        - pad_matrix[1 + 3 * i][42 - pad_shift + 94 * j].x
                        - 70,
                        cross_section=xs_m1_10,
                    )
                    st_ref.connect("e1", tap_ref["e1"])
                    tap_ref = die << metal1_taper
                    tap_ref.connect("e1", st_ref["e2"])
                    via_ref = die << via_m3_m1
                    via_ref.connect("e1", tap_ref["e2"], allow_layer_mismatch=True)
                    st_ref = die << gf.c.straight(
                        via_ref["e3"].x
                        - pad_matrix[1 + 3 * i][42 - pad_shift + 94 * j].x,
                        cross_section=xs_m3_11,
                    )
                    st_ref.connect("e1", via_ref["e3"])

                    ### PUC
                    aux = puc_matrix[5 + 6 * i][7 + j * 17]["e2"]
                    port = gf.Port(
                        "e1",
                        width=11,
                        layer=LAYER.metal3,
                        port_type="electrical",
                        center=(aux.x / 1000 - 5.5, aux.y / 1000 - 5.5),
                        orientation=180,
                    )
                    st_ref = die << gf.c.straight(20, cross_section=xs_m3_11)
                    st_ref.connect("e1", port)
                    via_ref = die << via_m3_m1
                    via_ref.connect("e1", st_ref["e2"])
                    tap_ref = die << metal1_taper
                    tap_ref.connect("e2", via_ref["e3"], allow_layer_mismatch=True)
                    st_ref = die << gf.c.straight(
                        tap_ref["e1"].x
                        - pad_matrix[2 + 3 * i][41 + pad_shift + 94 * j].x
                        - 70,
                        cross_section=xs_m1_10,
                    )
                    st_ref.connect("e1", tap_ref["e1"])
                    tap_ref = die << metal1_taper
                    tap_ref.connect("e1", st_ref["e2"])
                    via_ref = die << via_m3_m1
                    via_ref.connect("e1", tap_ref["e2"], allow_layer_mismatch=True)
                    st_ref = die << gf.c.straight(
                        via_ref["e3"].x
                        - pad_matrix[2 + 3 * i][41 + pad_shift + 94 * j].x,
                        cross_section=xs_m3_11,
                    )
                    st_ref.connect("e1", via_ref["e3"])

                    aux = puc_matrix[5 + 6 * i][7 + j * 17]["e1"]
                    port = gf.Port(
                        "e1",
                        width=11,
                        layer=LAYER.metal3,
                        port_type="electrical",
                        center=(aux.x / 1000 - 5.5, aux.y / 1000 + 5.5),
                        orientation=180,
                    )
                    st_ref = die << gf.c.straight(20, cross_section=xs_m3_11)
                    st_ref.connect("e1", port)
                    via_ref = die << via_m3_m1
                    via_ref.connect("e1", st_ref["e2"])
                    tap_ref = die << metal1_taper
                    tap_ref.connect("e2", via_ref["e3"], allow_layer_mismatch=True)
                    st_ref = die << gf.c.straight(
                        tap_ref["e1"].x
                        - pad_matrix[2 + 3 * i][39 + pad_shift + 94 * j].x
                        - 70,
                        cross_section=xs_m1_10,
                    )
                    st_ref.connect("e1", tap_ref["e1"])
                    tap_ref = die << metal1_taper
                    tap_ref.connect("e1", st_ref["e2"])
                    via_ref = die << via_m3_m1
                    via_ref.connect("e1", tap_ref["e2"], allow_layer_mismatch=True)
                    aux = pad_matrix[2 + 3 * i][39 + pad_shift + 94 * j]
                    port = gf.Port(
                        "e1",
                        width=11,
                        layer=LAYER.metal3,
                        port_type="electrical",
                        center=(aux.x + 10, aux.y),
                        orientation=270,
                    )
                    gf.routing.route_single(
                        die,
                        via_ref["e3"],
                        port,
                        bend=ipr.wire_corner45(xs_m3_11),
                        auto_taper=False,
                        cross_section=xs_m3_11,
                    )

                    ### PUC
                    aux = puc_matrix[3 + 6 * i][6 + j * 17]["e2"]
                    port1 = gf.Port(
                        "e1",
                        width=11,
                        layer=LAYER.metal3,
                        port_type="electrical",
                        center=(aux.x / 1000 - 5.5, aux.y / 1000 - 5.5),
                        orientation=180,
                    )
                    aux = pad_matrix[1 + 3 * i][46 + 94 * j - pad_shift]
                    port2 = gf.Port(
                        "e1",
                        width=11,
                        layer=LAYER.metal3,
                        port_type="electrical",
                        center=(aux.x, aux.y),
                        orientation=270,
                    )
                    gf.routing.route_single(
                        die,
                        port1,
                        port2,
                        bend=ipr.wire_corner45(xs_m3_11),
                        auto_taper=False,
                        cross_section=xs_m3_11,
                    )
                    aux = puc_matrix[3 + 6 * i][6 + j * 17]["e1"]
                    port = gf.Port(
                        "e1",
                        width=11,
                        layer=LAYER.metal3,
                        port_type="electrical",
                        center=(aux.x / 1000 - 5.5, aux.y / 1000 + 5.5),
                        orientation=180,
                    )
                    gf.routing.route_single(
                        die,
                        pad_matrix[2 + 3 * i][45 + 94 * j + pad_shift]["e1"],
                        port,
                        bend=ipr.wire_corner45(xs_m3_11),
                        auto_taper=False,
                        cross_section=xs_m3_11,
                    )

            # RIGHT SIDE
            for m in range(2):
                row = 6 * i if m == 0 else 3 + 6 * i
                for k in range(2):
                    if (m == 0 and k == 0) or (m == 1 and k == 1):
                        cross = xs_m1_10
                        via = via_m3_m1
                        taper = metal1_taper
                    if (m == 0 and k == 1) or (m == 1 and k == 0):
                        cross = xs_m2_10
                        via = via_m3_m2
                        taper = metal2_taper

                    st_ref = die << gf.c.straight(118.197, cross_section=xs_m3_11)
                    port = "e3" if k == 0 else "e4"
                    aux = 1 if k == 0 else -1
                    st_ref.move(
                        (st_ref.xmin, st_ref.y),
                        (
                            puc_matrix[row][9 + j * 17][port].x / 1000 + 5.5,
                            puc_matrix[row][9 + j * 17][port].y / 1000 - 5.5 * aux,
                        ),
                    )
                    via_ref = die << via
                    via_ref.connect("e1", st_ref["e2"])
                    tap_ref = die << taper
                    tap_ref.connect("e2", via_ref["e3"], allow_layer_mismatch=True)
                    st_ref = die << gf.c.straight(20, cross_section=cross)
                    st_ref.connect("e1", tap_ref["e1"])
                    bend_ref = die << ipr.wire_corner45(radius=2, cross_section=cross)
                    bend_ref.connect("e1", st_ref["e2"], mirror=k != 0)
                    st_ref = die << gf.c.straight(10.85, cross_section=cross)
                    st_ref.connect("e1", bend_ref["e2"])
                    bend_ref = die << ipr.wire_corner45(radius=2, cross_section=cross)
                    bend_ref.connect("e1", st_ref["e2"], mirror=k == 0)
                    if k == 0:
                        st_ref = die << gf.c.straight(148.749, cross_section=cross)
                        st_ref.connect("e1", bend_ref["e2"])
                        bend_ref = die << ipr.wire_corner45(
                            radius=2, cross_section=cross
                        )
                        bend_ref.connect("e1", st_ref["e2"], mirror=k == 0)
                        st_ref = die << gf.c.straight(10.85, cross_section=cross)
                        st_ref.connect("e1", bend_ref["e2"])
                        bend_ref = die << ipr.wire_corner45(
                            radius=2, cross_section=cross
                        )
                        bend_ref.connect("e1", st_ref["e2"], mirror=k != 0)

                    # per (m, k): pad row offset, column
                    pad_row, pad_col = {
                        (0, 0): (3 * i, 61 - pad_shift),
                        (0, 1): (3 * i, 59 - pad_shift),
                        (1, 0): (1 + 3 * i, 56 + pad_shift),
                        (1, 1): (2 + 3 * i, 57 - pad_shift),
                    }[m, k]
                    pad = pad_matrix[pad_row][pad_col + 94 * j]

                    st_ref = die << gf.c.straight(
                        pad.x - bend_ref["e2"].x - 70,
                        cross_section=cross,
                    )
                    st_ref.connect("e1", bend_ref["e2"], allow_layer_mismatch=True)
                    tap_ref = die << taper
                    tap_ref.connect("e1", st_ref["e2"])
                    via_ref = die << via
                    via_ref.connect("e1", tap_ref["e2"], allow_layer_mismatch=True)

                    if m != k:
                        gf.routing.route_single(
                            die,
                            via_ref["e3"],
                            gf.Port(
                                "e1",
                                width=11,
                                layer=LAYER.metal3,
                                port_type="electrical",
                                center=(pad.x, pad.y),
                                orientation=270,
                            ),
                            bend=ipr.wire_corner45(xs_m3_11),
                            auto_taper=False,
                            cross_section=xs_m3_11,
                        )
                    else:
                        st_ref = die << gf.c.straight(
                            pad.x - via_ref["e3"].x,
                            cross_section=xs_m3_11,
                        )
                        st_ref.connect("e1", via_ref["e3"], allow_layer_mismatch=True)

            ### PUC
            aux = puc_matrix[6 * i][11 + j * 17]["e3"]
            pad = pad_matrix[3 * i][55 - pad_shift + 94 * j]
            port = gf.Port(
                "e1",
                width=11,
                layer=LAYER.metal3,
                port_type="electrical",
                center=(aux.x / 1000 + 5.5, aux.y / 1000 - 5.5),
                orientation=0,
            )
            st_ref = die << gf.c.straight(pad.x - port.x, cross_section=xs_m3_11)
            st_ref.connect("e1", port)

            aux = puc_matrix[6 * i][11 + j * 17]["e4"]
            port = gf.Port(
                "e1",
                width=11,
                layer=LAYER.metal3,
                port_type="electrical",
                center=(aux.x / 1000 + 5.5, aux.y / 1000 + 5.5),
                orientation=0,
            )
            st_ref = die << gf.c.straight(20, cross_section=xs_m3_11)
            st_ref.connect("e1", port)
            bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m3_11)
            bend_ref.connect("e1", st_ref["e2"], mirror=True)
            st_ref = die << gf.c.straight(10.85, cross_section=xs_m3_11)
            st_ref.connect("e1", bend_ref["e2"])
            bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m3_11)
            bend_ref.connect("e1", st_ref["e2"])

            aux = pad_matrix[3 * i][57 - pad_shift + 94 * j]
            port = gf.Port(
                "e1",
                width=11,
                layer=LAYER.metal3,
                port_type="electrical",
                center=(aux.x + 10, aux.y),
                orientation=270,
            )
            gf.routing.route_single(
                die,
                bend_ref["e2"],
                port,
                bend=ipr.wire_corner45(xs_m3_11),
                auto_taper=False,
                cross_section=xs_m3_11,
            )

            ### PUC
            aux = puc_matrix[1 + 6 * i][10 + j * 17]["e3"]
            pad = pad_matrix[1 + 3 * i][60 + pad_shift + 94 * j]
            port = gf.Port(
                "e1",
                width=11,
                layer=LAYER.metal3,
                port_type="electrical",
                center=(aux.x / 1000 + 5.5, aux.y / 1000 - 5.5),
                orientation=0,
            )
            st_ref = die << gf.c.straight(20, cross_section=xs_m3_11)
            st_ref.connect("e1", port)
            via_ref = die << via_m3_m1
            via_ref.connect("e1", st_ref["e2"])
            tap_ref = die << metal1_taper
            tap_ref.connect("e2", via_ref["e3"], allow_layer_mismatch=True)
            st_ref = die << gf.c.straight(7.35, cross_section=xs_m1_10)
            st_ref.connect("e1", tap_ref["e1"])
            bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m1_10)
            bend_ref.connect("e1", st_ref["e2"])
            st_ref = die << gf.c.straight(18.5, cross_section=xs_m1_10)
            st_ref.connect("e1", bend_ref["e2"])
            bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m1_10)
            bend_ref.connect("e1", st_ref["e2"], mirror=True)

            st_ref = die << gf.c.straight(
                pad.x - bend_ref["e2"].x - 70,
                cross_section=xs_m1_10,
            )
            st_ref.connect("e1", bend_ref["e2"])
            tap_ref = die << metal1_taper
            tap_ref.connect("e1", st_ref["e2"])
            via_ref = die << via_m3_m1
            via_ref.connect("e1", tap_ref["e2"], allow_layer_mismatch=True)
            gf.routing.route_single(
                die,
                via_ref["e3"],
                pad["e1"],
                bend=ipr.wire_corner45(xs_m3_11),
                auto_taper=False,
                cross_section=xs_m3_11,
            )

            aux = puc_matrix[1 + 6 * i][10 + j * 17]["e4"]
            pad = pad_matrix[1 + 3 * i][58 + pad_shift + 94 * j]
            port = gf.Port(
                "e1",
                width=11,
                layer=LAYER.metal3,
                port_type="electrical",
                center=(aux.x / 1000 + 5.5, aux.y / 1000 + 5.5),
                orientation=0,
            )
            st_ref = die << gf.c.straight(50, cross_section=xs_m3_11)
            st_ref.connect("e1", port)
            via_ref = die << via_m3_m1
            via_ref.connect("e1", st_ref["e2"])
            tap_ref = die << metal1_taper
            tap_ref.connect("e2", via_ref["e3"], allow_layer_mismatch=True)
            st_ref = die << gf.c.straight(7.35, cross_section=xs_m1_10)
            st_ref.connect("e1", tap_ref["e1"])
            bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m1_10)
            bend_ref.connect("e1", st_ref["e2"])
            st_ref = die << gf.c.straight(7.65, cross_section=xs_m1_10)
            st_ref.connect("e1", bend_ref["e2"])
            bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m1_10)
            bend_ref.connect("e1", st_ref["e2"], mirror=True)
            st_ref = die << gf.c.straight(
                pad.x - bend_ref["e2"].x - 70,
                cross_section=xs_m1_10,
            )
            st_ref.connect("e1", bend_ref["e2"])
            tap_ref = die << metal1_taper
            tap_ref.connect("e1", st_ref["e2"])
            via_ref = die << via_m3_m1
            via_ref.connect("e1", tap_ref["e2"], allow_layer_mismatch=True)
            st_ref = die << gf.c.straight(
                pad.x - via_ref["e3"].x,
                cross_section=xs_m3_11,
            )
            st_ref.connect("e1", via_ref["e3"])

            ### PUC
            aux = puc_matrix[5 + 6 * i][10 + j * 17]["e3"]
            pad = pad_matrix[2 + 3 * i][59 - pad_shift + 94 * j]
            port = gf.Port(
                "e1",
                width=11,
                layer=LAYER.metal3,
                port_type="electrical",
                center=(aux.x / 1000 + 5.5, aux.y / 1000 - 5.5),
                orientation=0,
            )
            st_ref = die << gf.c.straight(50, cross_section=xs_m3_11)
            st_ref.connect("e1", port)
            bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m3_11)
            bend_ref.connect("e1", st_ref["e2"], mirror=True)
            st_ref = die << gf.c.straight(18.5, cross_section=xs_m3_11)
            st_ref.connect("e1", bend_ref["e2"])
            bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m3_11)
            bend_ref.connect("e1", st_ref["e2"])
            port = gf.Port(
                "e1",
                width=11,
                layer=LAYER.metal3,
                port_type="electrical",
                center=(pad.x, pad.y),
                orientation=270,
            )
            gf.routing.route_single(
                die,
                bend_ref["e2"],
                port,
                bend=ipr.wire_corner45(xs_m3_11),
                auto_taper=False,
                cross_section=xs_m3_11,
            )

            aux = puc_matrix[5 + 6 * i][10 + j * 17]["e4"]
            pad = pad_matrix[2 + 3 * i][61 - pad_shift + 94 * j]
            port = gf.Port(
                "e1",
                width=11,
                layer=LAYER.metal3,
                port_type="electrical",
                center=(aux.x / 1000 + 5.5, aux.y / 1000 + 5.5),
                orientation=0,
            )
            st_ref = die << gf.c.straight(20, cross_section=xs_m3_11)
            st_ref.connect("e1", port)
            via_ref = die << via_m3_m2
            via_ref.connect("e1", st_ref["e2"])
            tap_ref = die << metal2_taper
            tap_ref.connect("e2", via_ref["e3"], allow_layer_mismatch=True)
            st_ref = die << gf.c.straight(7.35, cross_section=xs_m2_10)
            st_ref.connect("e1", tap_ref["e1"])
            bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m2_10)
            bend_ref.connect("e1", st_ref["e2"])
            st_ref = die << gf.c.straight(7.35, cross_section=xs_m2_10)
            st_ref.connect("e1", bend_ref["e2"])
            bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m2_10)
            bend_ref.connect("e1", st_ref["e2"], mirror=True)
            st_ref = die << gf.c.straight(
                pad.x - bend_ref["e2"].x - 70,
                cross_section=xs_m2_10,
            )
            st_ref.connect("e1", bend_ref["e2"])
            tap_ref = die << metal2_taper
            tap_ref.connect("e1", st_ref["e2"])
            via_ref = die << via_m3_m2
            via_ref.connect("e1", tap_ref["e2"], allow_layer_mismatch=True)
            port = gf.Port(
                "e1",
                width=11,
                layer=LAYER.metal3,
                port_type="electrical",
                center=(pad.x + 10, pad.y),
                orientation=270,
            )
            gf.routing.route_single(
                die,
                via_ref["e3"],
                port,
                bend=ipr.wire_corner45(xs_m3_11),
                auto_taper=False,
                cross_section=xs_m3_11,
            )

            ### PUC
            aux = puc_matrix[3 + 6 * i][11 + j * 17]["e3"]
            port1 = gf.Port(
                "e1",
                width=11,
                layer=LAYER.metal3,
                port_type="electrical",
                center=(aux.x / 1000 + 5.5, aux.y / 1000 - 5.5),
                orientation=0,
            )
            aux = pad_matrix[1 + 3 * i][54 + 94 * j + pad_shift]
            port2 = gf.Port(
                "e1",
                width=11,
                layer=LAYER.metal3,
                port_type="electrical",
                center=(aux.x, aux.y),
                orientation=270,
            )
            gf.routing.route_single(
                die,
                port1,
                port2,
                bend=ipr.wire_corner45(xs_m3_11),
                auto_taper=False,
                cross_section=xs_m3_11,
            )
            aux = puc_matrix[3 + 6 * i][11 + j * 17]["e4"]
            port = gf.Port(
                "e1",
                width=11,
                layer=LAYER.metal3,
                port_type="electrical",
                center=(aux.x / 1000 + 5.5, aux.y / 1000 + 5.5),
                orientation=0,
            )
            gf.routing.route_single(
                die,
                pad_matrix[2 + 3 * i][55 + 94 * j - pad_shift]["e1"],
                port,
                bend=ipr.wire_corner45(xs_m3_11),
                auto_taper=False,
                cross_section=xs_m3_11,
            )

    #############################
    # LEFT TO RIGHT CONNECTIONS #
    #############################
    column = [0, 1, 2, 12, 13]
    column_shift = [0, 6, 12, 62, 70]
    ground_shift = [0, 8, 14, 62, 70]
    for j in range(2):
        for m in range(5):
            for i in range(72 if m < 2 else 216):
                pad_shift = 0 if i % 2 == 0 else 1
                if m in (1, 2):
                    pad_shift *= -1
                puc = puc_matrix[2 * i][column[m] + j * 17]

                # SIGNAL UPPER PS
                pad = pad_matrix[i][1 - pad_shift + j * 94 + column_shift[m]]
                aux = puc["e3"]
                port = gf.Port(
                    "e1",
                    width=11,
                    layer=LAYER.metal3,
                    port_type="electrical",
                    center=(aux.x / 1000 + 5.5, aux.y / 1000 - 5.5),
                    orientation=0,
                )
                st_ref = die << gf.c.straight(pad.x - port.x, cross_section=xs_m3_11)
                st_ref.connect("e1", port)

                # SIGNAL LOWER PS
                pad = pad_matrix[i][3 - pad_shift + j * 94 + column_shift[m]]
                st_ref = die << gf.c.straight(7.35, cross_section=xs_m3_11)
                st_ref.connect("e1", puc["e4"])
                bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m3_11)
                bend_ref.connect("e1", st_ref["e2"])

                port = gf.Port(
                    "e1",
                    width=11,
                    layer=LAYER.metal3,
                    port_type="electrical",
                    center=(pad.x, pad.y),
                    orientation=270,
                )
                gf.routing.route_single(
                    die,
                    bend_ref["e2"],
                    port,
                    bend=ipr.wire_corner45(xs_m3_11),
                    auto_taper=False,
                    cross_section=xs_m3_11,
                )

                # COMMON GROUND
                if i % 4 == 0:
                    com_pad = _place_metal3_fill(
                        METAL3_SHORT_WIDTH,
                        1 + i,
                        4 + j * 94 + ground_shift[m],
                        vertical=True,
                    )

                # LOWER PS GROUND
                port = puc["e1"]
                st_ref = die << gf.c.straight(7.35, cross_section=xs_m3_11)
                st_ref.connect("e1", port)
                bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m3_11)
                bend_ref.connect("e1", st_ref["e2"])
                st_ref = die << gf.c.straight(20, cross_section=xs_m3_11)
                st_ref.connect("e1", bend_ref["e2"])
                via_ref = die << via_m3_m2
                via_ref.connect("e1", st_ref["e2"])
                tap_ref = die << metal2_taper
                tap_ref.connect("e2", via_ref["e3"], allow_layer_mismatch=True)
                st_ref = die << gf.c.straight(
                    com_pad.x - tap_ref["e1"].x - 50,
                    cross_section=xs_m2_10,
                )
                st_ref.connect("e1", tap_ref["e1"])
                tap_ref = die << metal2_taper
                tap_ref.connect("e1", st_ref["e2"])
                via_ref = die << via_m3_m2
                via_ref.connect("e1", tap_ref["e2"], allow_layer_mismatch=True)
                st_ref = die << gf.c.straight(
                    com_pad.x - via_ref["e3"].x,
                    cross_section=xs_m3_11,
                )
                st_ref.connect("e1", via_ref["e3"])
                if (i % 4 == 0) or (i % 4 == 3):
                    bend_ref = die << ipr.wire_corner45(
                        radius=2, cross_section=xs_m3_11
                    )
                    bend_ref.connect("e1", st_ref["e2"], mirror=i % 4 == 0)
                    st_ref = die << gf.c.straight(
                        100,
                        cross_section=xs_m3_11,
                    )
                    st_ref.connect("e1", bend_ref["e2"])

                # UPPER PS GROUND
                port = puc["e2"]
                st_ref = die << gf.c.straight(7.35, cross_section=xs_m3_11)
                st_ref.connect("e1", port)
                bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m3_11)
                bend_ref.connect("e1", st_ref["e2"], mirror=True)
                st_ref = die << gf.c.straight(20, cross_section=xs_m3_11)
                st_ref.connect("e1", bend_ref["e2"])
                via_ref = die << via_m3_m1
                via_ref.connect("e1", st_ref["e2"])
                tap_ref = die << metal1_taper
                tap_ref.connect("e2", via_ref["e3"], allow_layer_mismatch=True)
                st_ref = die << gf.c.straight(86.5, cross_section=xs_m1_10)
                st_ref.connect("e1", tap_ref["e1"])
                bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m1_10)
                bend_ref.connect("e1", st_ref["e2"], mirror=True)
                st_ref = die << gf.c.straight(52.85, cross_section=xs_m1_10)
                st_ref.connect("e1", bend_ref["e2"])
                via_ref = die << via_m2_m1
                via_ref.connect("e1", st_ref["e2"], allow_layer_mismatch=True)

    #############################
    # RIGHT TO LEFT CONNECTIONS #
    #############################
    column = [3, 4, 5, 14, 15, 16]
    column_shift = [0, 8, 12, 56, 62, 67]
    ground_shift = [0, 8, 14, 58, 64, 69]
    for j in range(2):
        for m in range(6):
            if m < 4:
                extra = 0
            elif m == 4:
                extra = 144
            else:
                extra = 288
            for i in range(216 if m < 4 else 72):
                pad_shift = 0 if i % 2 == 0 else 1
                if m > 1:
                    pad_shift *= -1
                puc = puc_matrix[2 * i + extra][column[m] + j * 17]

                # SIGNAL UPPER PS
                pad = pad_matrix[i + extra // 2][
                    25 - pad_shift + j * 94 + column_shift[m]
                ]
                aux = puc["e2"]
                port = gf.Port(
                    "e1",
                    width=11,
                    layer=LAYER.metal3,
                    port_type="electrical",
                    center=(aux.x / 1000 + 5.5, aux.y / 1000 - 5.5),
                    orientation=180,
                )
                st_ref = die << gf.c.straight(port.x - pad.x, cross_section=xs_m3_11)
                st_ref.connect("e1", port)

                # SIGNAL LOWER PS
                pad = pad_matrix[i + extra // 2][
                    23 - pad_shift + j * 94 + column_shift[m]
                ]
                st_ref = die << gf.c.straight(7.35, cross_section=xs_m3_11)
                st_ref.connect("e1", puc["e1"])
                bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m3_11)
                bend_ref.connect("e1", st_ref["e2"], mirror=True)

                port = gf.Port(
                    "e1",
                    width=11,
                    layer=LAYER.metal3,
                    port_type="electrical",
                    center=(pad.x, pad.y),
                    orientation=270,
                )
                gf.routing.route_single(
                    die,
                    bend_ref["e2"],
                    port,
                    bend=ipr.wire_corner45(xs_m3_11),
                    auto_taper=False,
                    cross_section=xs_m3_11,
                )

                # COMMON GROUND
                if i % 4 == 0:
                    com_pad = _place_metal3_fill(
                        METAL3_SHORT_WIDTH,
                        1 + i + extra // 2,
                        20 + j * 94 + ground_shift[m],
                        vertical=True,
                    )

                # LOWER PS GROUND
                port = puc["e4"]
                st_ref = die << gf.c.straight(7.35, cross_section=xs_m3_11)
                st_ref.connect("e1", port)
                bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m3_11)
                bend_ref.connect("e1", st_ref["e2"], mirror=True)
                st_ref = die << gf.c.straight(20, cross_section=xs_m3_11)
                st_ref.connect("e1", bend_ref["e2"])
                via_ref = die << via_m3_m2
                via_ref.connect("e1", st_ref["e2"])
                tap_ref = die << metal2_taper
                tap_ref.connect("e2", via_ref["e3"], allow_layer_mismatch=True)
                st_ref = die << gf.c.straight(
                    tap_ref["e1"].x - com_pad.x - 50,
                    cross_section=xs_m2_10,
                )
                st_ref.connect("e1", tap_ref["e1"])
                tap_ref = die << metal2_taper
                tap_ref.connect("e1", st_ref["e2"])
                via_ref = die << via_m3_m2
                via_ref.connect("e1", tap_ref["e2"], allow_layer_mismatch=True)
                st_ref = die << gf.c.straight(
                    via_ref["e3"].x - com_pad.x,
                    cross_section=xs_m3_11,
                )
                st_ref.connect("e1", via_ref["e3"])
                if (i % 4 == 0) or (i % 4 == 3):
                    bend_ref = die << ipr.wire_corner45(
                        radius=2, cross_section=xs_m3_11
                    )
                    bend_ref.connect("e1", st_ref["e2"], mirror=i % 4 == 3)
                    st_ref = die << gf.c.straight(
                        100,
                        cross_section=xs_m3_11,
                    )
                    st_ref.connect("e1", bend_ref["e2"])

                # UPPER PS GROUND
                port = puc["e3"]
                st_ref = die << gf.c.straight(7.35, cross_section=xs_m3_11)
                st_ref.connect("e1", port)
                bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m3_11)
                bend_ref.connect("e1", st_ref["e2"])
                st_ref = die << gf.c.straight(20, cross_section=xs_m3_11)
                st_ref.connect("e1", bend_ref["e2"])
                via_ref = die << via_m3_m1
                via_ref.connect("e1", st_ref["e2"])
                tap_ref = die << metal1_taper
                tap_ref.connect("e2", via_ref["e3"], allow_layer_mismatch=True)
                st_ref = die << gf.c.straight(86.5, cross_section=xs_m1_10)
                st_ref.connect("e1", tap_ref["e1"])
                bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m1_10)
                bend_ref.connect("e1", st_ref["e2"])
                st_ref = die << gf.c.straight(52.85, cross_section=xs_m1_10)
                st_ref.connect("e1", bend_ref["e2"])
                via_ref = die << via_m2_m1
                via_ref.connect("e1", st_ref["e2"], allow_layer_mismatch=True)

    #############################
    # MESH PDs                  #
    #############################
    for j in range(2):
        if j == 0:
            search_area = (67.8, -9735.29, 203.845, -3192.91)
        else:
            search_area = (11235.38, -9735.29, 11302.21, -3192.91)

        pd_matrix = v7b.build_matrix(die, "lateral_pd*", area=search_area)
        for i in range(72):
            # SIGNAL
            pad_shift = 0 if i % 2 == 0 else -1
            pad = pad_matrix[144 + i][95 + pad_shift + j * 94]
            st_ref = die << gf.c.straight(2, cross_section=xs_m2_10)
            st_ref.connect("e1", pd_matrix[i][0]["e2"])
            tap_ref = die << metal2_taper
            tap_ref.connect("e1", st_ref["e2"])
            via_ref = die << via_m3_m2
            via_ref.connect("e1", tap_ref["e2"], allow_layer_mismatch=True)
            port = gf.Port(
                "e1",
                width=11,
                layer=LAYER.metal3,
                port_type="electrical",
                center=(pad.x, pad.y),
                orientation=270,
            )
            gf.routing.route_single(
                die,
                via_ref["e3"],
                port,
                bend=ipr.wire_corner45(xs_m3_11),
                auto_taper=False,
                cross_section=xs_m3_11,
            )

            # COMMON GROUND
            if i % 4 == 0:
                _place_metal3_fill(
                    METAL3_SHORT_WIDTH, 145 + i, 96 + j * 94, vertical=True
                )

            # GROUND
            pad = pad_matrix[145 + i + pad_shift][96 + j * 94]
            st_ref = die << gf.c.straight(2, cross_section=xs_m2_10)
            st_ref.connect("e1", pd_matrix[i][0]["e1"])
            tap_ref = die << metal2_taper
            tap_ref.connect("e1", st_ref["e2"])
            via_ref = die << via_m3_m2
            via_ref.connect("e1", tap_ref["e2"], allow_layer_mismatch=True)
            port = gf.Port(
                "e1",
                width=11,
                layer=LAYER.metal3,
                port_type="electrical",
                center=(pad.x, pad.y),
                orientation=90 if i % 2 == 0 else 270,
            )
            gf.routing.route_single(
                die,
                via_ref["e3"],
                port,
                bend=ipr.wire_corner45(xs_m3_11),
                auto_taper=False,
                cross_section=xs_m3_11,
            )

    #############################
    # INPUT MUAs                #
    #############################
    for j in range(2):
        if j == 0:
            search_area = (-11223, 9754, -4730, 11096)
        else:
            search_area = (-56.393, 9754, 6436.98, 11096)

        pd_matrix = v7b.build_matrix(die, "lateral_pd*", area=search_area)
        puc_matrix = v7b.build_matrix(die, "puc*", "pucmua\\d+", area=search_area)
        pad_matrix = v7b.build_matrix(die, "flipchip_pad*", area=search_area)

        for i in range(72):
            pad_shift = 0 if i % 2 == 0 else -1
            # COMMON GROUND
            if i % 4 == 0:
                for pad_col, pad_row in ((0, i), (10, i), (9, 1 + i)):
                    _place_metal3_fill(METAL3_SHORT_WIDTH, pad_col, pad_row)
            # PDs
            for k in range(2):
                # GROUND PD
                if k == 0:
                    pad = pad_matrix[10][i + pad_shift]
                    pd = pd_matrix[1][i * 2 + 1]
                else:
                    pad = pad_matrix[0][i + pad_shift]
                    pd = pd_matrix[0][i * 2]

                st_ref = die << gf.components.straight(6, cross_section=xs_m2_10)
                st_ref.connect("e1", pd["e1"])
                via_ref = die << via_m2_m1
                via_ref.connect("e1", st_ref["e2"])
                leng = via_ref["e3"].y - pad.y if k == 0 else pad.y - via_ref["e3"].y
                st_ref = die << gf.c.straight(leng - 50, cross_section=xs_m1_10)
                st_ref.connect("e1", via_ref["e3"], allow_layer_mismatch=True)
                tap_ref = die << metal1_taper
                tap_ref.connect("e1", st_ref["e2"])
                via_ref = die << via_m3_m1
                via_ref.connect("e1", tap_ref["e2"], allow_layer_mismatch=True)

                if k == 1 and i % 2 == 0:
                    st_ref = die << gf.components.straight(34, cross_section=xs_m3_11)
                    st_ref.connect("e1", via_ref["e3"])
                else:
                    port = gf.Port(
                        "e1",
                        width=11,
                        layer=LAYER.metal3,
                        port_type="electrical",
                        center=(pad.x, pad.y),
                        orientation=0,
                    )
                    gf.routing.route_single(
                        die,
                        via_ref["e3"],
                        port,
                        bend=ipr.wire_corner45(xs_m3_11),
                        auto_taper=False,
                        cross_section=xs_m3_11,
                    )
                if i % 2 == 0:
                    # SIGNAL PD
                    if k == 0:
                        pad = pad_matrix[8][i]
                    else:
                        pad = pad_matrix[6][i]
                    st_ref = die << gf.components.straight(0.5, cross_section=xs_m2_10)
                    st_ref.connect("e1", pd["e2"])
                    tap_ref = die << metal2_taper
                    tap_ref.connect("e1", st_ref["e2"])
                    via_ref = die << via_m3_m2
                    via_ref.connect("e1", tap_ref["e2"], allow_layer_mismatch=True)
                    if k == 1:
                        st_ref = die << gf.c.straight(
                            abs(pad.y - via_ref["e3"].y), cross_section=xs_m3_11
                        )
                        st_ref.connect("e1", via_ref["e3"])
                    else:
                        port = gf.Port(
                            "e1",
                            width=11,
                            layer=LAYER.metal3,
                            port_type="electrical",
                            center=(pad.x, pad.y),
                            orientation=0 if k == 0 else 180,
                        )
                        gf.routing.route_single(
                            die,
                            via_ref["e3"],
                            port,
                            bend=ipr.wire_corner45(xs_m3_11),
                            auto_taper=False,
                            cross_section=xs_m3_11,
                        )
                else:
                    # SIGNAL PD
                    if k == 0:
                        pad = pad_matrix[5][i]
                        st_ref = die << gf.components.straight(
                            30, cross_section=xs_m2_10
                        )
                        st_ref.connect("e1", pd["e2"])
                        bend_ref = die << ipr.wire_corner45(
                            radius=2, cross_section=xs_m2_10
                        )
                        bend_ref.connect("e1", st_ref["e2"], mirror=True)
                        st_ref = die << gf.components.straight(
                            58.501, cross_section=xs_m2_10
                        )
                        st_ref.connect("e1", bend_ref["e2"])
                        bend_ref = die << ipr.wire_corner45(
                            radius=2, cross_section=xs_m2_10
                        )
                        bend_ref.connect("e1", st_ref["e2"], mirror=True)
                        st_ref = die << gf.components.straight(
                            200, cross_section=xs_m2_10
                        )
                        st_ref.connect("e1", bend_ref["e2"])
                        bend_ref = die << ipr.wire_corner45(
                            radius=2, cross_section=xs_m2_10
                        )
                        bend_ref.connect("e1", st_ref["e2"])
                        st_ref = die << gf.components.straight(
                            20.6, cross_section=xs_m2_10
                        )
                        st_ref.connect("e1", bend_ref["e2"])
                        bend_ref = die << ipr.wire_corner45(
                            radius=2, cross_section=xs_m2_10
                        )
                        bend_ref.connect("e1", st_ref["e2"], mirror=True)
                        st_ref = die << gf.components.straight(
                            275, cross_section=xs_m2_10
                        )
                        st_ref.connect("e1", bend_ref["e2"])
                        bend_ref = die << ipr.wire_corner45(
                            radius=2, cross_section=xs_m2_10
                        )
                        bend_ref.connect("e1", st_ref["e2"], mirror=True)
                        st_ref = die << gf.components.straight(
                            38.228, cross_section=xs_m2_10
                        )
                        st_ref.connect("e1", bend_ref["e2"])
                        bend_ref = die << ipr.wire_corner45(
                            radius=2, cross_section=xs_m2_10
                        )
                        bend_ref.connect("e1", st_ref["e2"])
                        st_ref = die << gf.components.straight(
                            20.6, cross_section=xs_m2_10
                        )
                        st_ref.connect("e1", bend_ref["e2"])
                        tap_ref = die << metal2_taper
                        tap_ref.connect("e1", st_ref["e2"])
                        via_ref = die << via_m3_m2
                        via_ref.connect("e1", tap_ref["e2"], allow_layer_mismatch=True)
                        st_ref = die << gf.c.straight(43.221, cross_section=xs_m3_11)
                        st_ref.connect("e1", via_ref["e3"])
                    else:
                        pad = pad_matrix[7][i]
                        st_ref = die << gf.components.straight(
                            0.5, cross_section=xs_m2_10
                        )
                        st_ref.connect("e1", pd["e2"])
                        tap_ref = die << metal2_taper
                        tap_ref.connect("e1", st_ref["e2"])
                        via_ref = die << via_m3_m2
                        via_ref.connect("e1", tap_ref["e2"], allow_layer_mismatch=True)
                        st_ref = die << gf.c.straight(
                            abs(pad.y - via_ref["e3"].y), cross_section=xs_m3_11
                        )
                        st_ref.connect("e1", via_ref["e3"])

            # MUAs
            # GROUND PS
            puc = puc_matrix[0][i]
            pad = pad_matrix[9][1 + i + pad_shift]
            port = gf.Port(
                "e1",
                width=11,
                layer=LAYER.metal3,
                port_type="electrical",
                center=(puc["e4"].x / 1000 + 5.5, puc["e4"].y / 1000 - 5.5),
                orientation=270,
            )
            st_ref = die << gf.c.straight(10, cross_section=xs_m3_11)
            st_ref.connect("e1", port)
            via_ref = die << via_m3_m1
            via_ref.connect("e1", st_ref["e2"])
            tap_ref = die << metal1_taper
            tap_ref.connect("e2", via_ref["e3"], allow_layer_mismatch=True)
            st_ref = die << gf.c.straight(7.35, cross_section=xs_m1_10)
            st_ref.connect("e1", tap_ref["e1"])
            bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m1_10)
            bend_ref.connect("e1", st_ref["e2"])
            st_ref = die << gf.c.straight(70.33, cross_section=xs_m1_10)
            st_ref.connect("e1", bend_ref["e2"])
            bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m1_10)
            bend_ref.connect("e1", st_ref["e2"], mirror=True)
            st_ref = die << gf.c.straight(
                bend_ref["e2"].y - pad.y - 50, cross_section=xs_m1_10
            )
            st_ref.connect("e1", bend_ref["e2"])
            tap_ref = die << metal1_taper
            tap_ref.connect("e1", st_ref["e2"])
            via_ref = die << via_m3_m1
            via_ref.connect("e1", tap_ref["e2"], allow_layer_mismatch=True)

            if i % 2 == 0:
                st_ref = die << gf.c.straight(34, cross_section=xs_m3_11)
                st_ref.connect("e1", via_ref["e3"])
            else:
                port = gf.Port(
                    "e1",
                    width=11,
                    layer=LAYER.metal3,
                    port_type="electrical",
                    center=(pad.x, pad.y),
                    orientation=0,
                )
                gf.routing.route_single(
                    die,
                    via_ref["e3"],
                    port,
                    bend=ipr.wire_corner45(xs_m3_11),
                    auto_taper=False,
                    cross_section=xs_m3_11,
                )

            port = gf.Port(
                "e1",
                width=11,
                layer=LAYER.metal3,
                port_type="electrical",
                center=(puc["e3"].x / 1000 - 5.5, puc["e3"].y / 1000 - 5.5),
                orientation=270,
            )
            st_ref = die << gf.c.straight(10, cross_section=xs_m3_11)
            st_ref.connect("e1", port)
            via_ref = die << via_m3_m1
            via_ref.connect("e1", st_ref["e2"])
            tap_ref = die << metal1_taper
            tap_ref.connect("e2", via_ref["e3"], allow_layer_mismatch=True)
            st_ref = die << gf.c.straight(7.35, cross_section=xs_m1_10)
            st_ref.connect("e1", tap_ref["e1"])

            # SIGNAL PS
            # LEFT SIDE
            pad = pad_matrix[4 + pad_shift][i]
            port = gf.Port(
                "e1",
                width=11,
                layer=LAYER.metal3,
                port_type="electrical",
                center=(pad.x, pad.y),
                orientation=180,
            )
            port2 = gf.Port(
                "e1",
                width=11,
                layer=LAYER.metal3,
                port_type="electrical",
                center=(puc["e1"].x / 1000 + 5.5, puc["e1"].y / 1000 + 5.5),
                orientation=90,
            )
            gf.routing.route_single(
                die,
                port2,
                port,
                bend=ipr.wire_corner45(xs_m3_11),
                auto_taper=False,
                cross_section=xs_m3_11,
                start_straight_length=27,
                end_straight_length=35,
            )
            # RIGHT SIDE
            pad = pad_matrix[2 + pad_shift][i]
            port = gf.Port(
                "e1",
                width=11,
                layer=LAYER.metal3,
                port_type="electrical",
                center=(puc["e2"].x / 1000 - 5.5, puc["e2"].y / 1000 + 5.5),
                orientation=90,
            )
            st_ref = die << gf.c.straight(5, cross_section=xs_m3_11)
            st_ref.connect("e1", port)
            via_ref = die << via_m3_m1
            via_ref.connect("e1", st_ref["e2"])
            tap_ref = die << metal1_taper
            tap_ref.connect("e2", via_ref["e3"], allow_layer_mismatch=True)
            st_ref = die << gf.c.straight(
                pad.y - tap_ref["e1"].y - 50, cross_section=xs_m1_10
            )
            st_ref.connect("e1", tap_ref["e1"])
            tap_ref = die << metal1_taper
            tap_ref.connect("e1", st_ref["e2"])
            via_ref = die << via_m3_m1
            via_ref.connect("e1", tap_ref["e2"], allow_layer_mismatch=True)
            port = gf.Port(
                "e1",
                width=11,
                layer=LAYER.metal3,
                port_type="electrical",
                center=(pad.x, pad.y),
                orientation=0,
            )
            gf.routing.route_single(
                die,
                via_ref["e3"],
                port,
                bend=ipr.wire_corner45(xs_m3_11),
                auto_taper=False,
                cross_section=xs_m3_11,
            )

    #############################
    # LOOP MUAs                 #
    #############################
    # LEFT SIDE
    search_area = (-11500.75, 9756.604, -11213.71, 11097.74)

    pd_matrix = v7b.build_matrix(die, "lateral_pd*", area=search_area)
    puc_matrix = v7b.build_matrix(die, "puc*", "pucmua\\d+", area=search_area)
    pad_matrix = v7b.build_matrix(die, "flipchip_pad*", area=search_area)

    # pad_shift = 0 if i % 2 == 0 else -1
    # COMMON GROUND
    _place_metal3_fill(METAL3_SHORT_WIDTH, 11, 0)
    _place_metal3_fill(METAL3_SHORT_WIDTH, 8, 0, True)
    # PUC GROUND
    for i in range(2):
        for k in range(2):
            shift = -1 if k == 1 else 1
            puc = puc_matrix[0][i]
            port = gf.Port(
                "e1",
                width=11,
                layer=LAYER.metal3,
                port_type="electrical",
                center=(
                    puc[f"e{4 - k}"].x / 1000 + 5.5 * shift,
                    puc[f"e{4 - k}"].y / 1000 - 5.5,
                ),
                orientation=270,
            )
            st_ref = die << gf.c.straight(20 + 20 * i, cross_section=xs_m3_11)
            st_ref.connect("e1", port)
            bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m3_11)
            bend_ref.connect("e1", st_ref["e2"], mirror=True)
            st_ref = die << gf.c.straight(
                bend_ref["e2"].x - pad_matrix[1][0].x, cross_section=xs_m3_11
            )
            st_ref.connect("e1", bend_ref["e2"])

    # PUC SIGNALS
    for i in range(2):
        for k in range(2):
            puc = puc_matrix[0][i]
            if i == 0:
                pad = pad_matrix[7 - k][k]
            else:
                pad = pad_matrix[7 - k * 2][2]
            shift = 1 if k == 0 else -1
            port = gf.Port(
                "e1",
                width=11,
                layer=LAYER.metal3,
                port_type="electrical",
                center=(
                    puc[f"e{1 + k}"].x / 1000 + 5.5 * shift,
                    puc[f"e{1 + k}"].y / 1000 + 5.5,
                ),
                orientation=90,
            )
            if i == 1 and k == 1:
                st_ref = die << gf.c.straight(5, cross_section=xs_m3_11)
                st_ref.connect("e1", port)
                via_ref = die << via_m3_m1
                via_ref.connect("e1", st_ref["e2"])
                tap_ref = die << metal1_taper
                tap_ref.connect("e2", via_ref["e3"], allow_layer_mismatch=True)
                port2 = gf.Port(
                    "e1",
                    width=11,
                    layer=LAYER.metal3,
                    port_type="electrical",
                    center=(pad.x, pad.y),
                    orientation=270,
                )
                st_ref = die << gf.c.straight(34, cross_section=xs_m3_11)
                st_ref.connect("e1", port2)
                via_ref = die << via_m3_m1
                via_ref.connect("e1", st_ref["e2"])
                tap_ref2 = die << metal1_taper
                tap_ref2.connect("e2", via_ref["e3"], allow_layer_mismatch=True)
                gf.routing.route_single(
                    die,
                    tap_ref2["e1"],
                    tap_ref["e1"],
                    auto_taper=False,
                    cross_section=xs_m1_10,
                    bend=ipr.wire_corner45(radius=2, cross_section=xs_m1_10),
                )
            else:
                port2 = gf.Port(
                    "e1",
                    width=11,
                    layer=LAYER.metal3,
                    port_type="electrical",
                    center=(pad.x, pad.y),
                    orientation=270 if i == 0 else 180,
                )
                gf.routing.route_single(
                    die,
                    port,
                    port2,
                    auto_taper=False,
                    cross_section=xs_m3_11,
                    bend=ipr.wire_corner45(radius=2, cross_section=xs_m3_11),
                    start_straight_length=20 if k == 0 else 100,
                    end_straight_length=23 if i == 1 else 0,
                )

    # UP PD SIGNALS
    for i in range(2):
        pad = pad_matrix[5 - i][i]
        pd = pd_matrix[0][i * 2]
        st_ref = die << gf.c.straight(5, cross_section=xs_m2_10)
        st_ref.connect("e1", pd["e2"])
        via_ref1 = die << via_m2_m1
        via_ref1.connect("e1", st_ref["e2"])
        port2 = gf.Port(
            "e1",
            width=11,
            layer=LAYER.metal3,
            port_type="electrical",
            center=(pad.x, pad.y),
            orientation=270,
        )
        st_ref = die << gf.c.straight(110 if i == 0 else 130, cross_section=xs_m3_11)
        st_ref.connect("e1", port2)
        via_ref = die << via_m3_m1
        via_ref.connect("e1", st_ref["e2"])
        tap_ref = die << metal1_taper
        tap_ref.connect("e2", via_ref["e3"], allow_layer_mismatch=True)
        gf.routing.route_single(
            die,
            tap_ref["e1"],
            via_ref1["e3"],
            auto_taper=False,
            cross_section=xs_m1_10,
            bend=ipr.wire_corner45(radius=2, cross_section=xs_m1_10),
        )

    # UP PD GROUNDS
    for i in range(2):
        pd = pd_matrix[0][i * 2]
        port = gf.Port(
            "e1",
            width=10,
            layer=LAYER.metal2,
            port_type="electrical",
            center=(pd["e1"].x / 1000, pd["e1"].y / 1000 - 15.8),
            orientation=270,
        )
        st_ref = die << gf.c.straight(20, cross_section=xs_m2_10)
        st_ref.connect("e1", port)
        bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m2_10)
        bend_ref.connect("e1", st_ref["e2"], mirror=True)
        st_ref = die << gf.c.straight(21.63, cross_section=xs_m2_10)
        st_ref.connect("e1", bend_ref["e2"])
        bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m2_10)
        bend_ref.connect("e1", st_ref["e2"])
        st_ref = die << gf.c.straight(20, cross_section=xs_m2_10)
        st_ref.connect("e1", bend_ref["e2"])
        via_ref = die << via_m2_m1
        via_ref.connect("e1", st_ref["e2"])
        st_ref = die << gf.c.straight(355, cross_section=xs_m1_10)
        st_ref.connect("e1", via_ref["e3"], allow_layer_mismatch=True)
        tap_ref = die << metal1_taper
        tap_ref.connect("e1", st_ref["e2"])
        via_ref = die << via_m3_m1
        via_ref.connect("e1", tap_ref["e2"], allow_layer_mismatch=True)
        st_ref = die << gf.c.straight(20, cross_section=xs_m3_11)
        st_ref.connect("e1", via_ref["e3"])

    # LOW PD GROUND
    for i in range(2):
        tap_ref = die << metal2_taper
        tap_ref.connect("e1", pd_matrix[1][1 + 2 * i]["e1"])
        via_ref = die << via_m3_m2
        via_ref.connect("e1", tap_ref["e2"], allow_layer_mismatch=True)
        st_ref = die << gf.c.straight(20, cross_section=xs_m3_11)
        st_ref.connect("e1", via_ref["e3"])
        bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m3_11)
        bend_ref.connect("e1", st_ref["e2"], mirror=i == 1)
        st_ref = die << gf.c.straight(22, cross_section=xs_m3_11)
        st_ref.connect("e1", bend_ref["e2"])
        bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m3_11)
        bend_ref.connect("e1", st_ref["e2"], mirror=i == 0)
        st_ref = die << gf.c.straight(
            bend_ref["e2"].y - pad_matrix[11][0].y, cross_section=xs_m3_11
        )
        st_ref.connect("e1", bend_ref["e2"])

    # LOW PD SIGNAL
    for i in range(2):
        pad = pad_matrix[10 + 2 * i][1]
        pd = pd_matrix[1][1 + 2 * i]
        st_ref = die << gf.c.straight(34, cross_section=xs_m3_11)
        st_ref.connect("e1", pad["e1"])
        via_ref = die << via_m3_m2
        via_ref.connect("e1", st_ref["e2"])
        tap_ref = die << metal2_taper
        tap_ref.connect("e2", via_ref["e3"], allow_layer_mismatch=True)
        gf.routing.route_single(
            die,
            tap_ref["e1"],
            pd["e2"],
            auto_taper=False,
            cross_section=xs_m2_10,
            bend=ipr.wire_corner45(radius=2, cross_section=xs_m2_10),
        )

    # RIGHT SIDE
    search_area = (6428.18, 9736.54, 6693.71, 11117.14)

    pd_matrix = v7b.build_matrix(die, "lateral_pd*", area=search_area)
    puc_matrix = v7b.build_matrix(die, "puc*", "pucmua\\d+", area=search_area)
    pad_matrix = v7b.build_matrix(die, "flipchip_pad*", area=search_area)

    # pad_shift = 0 if i % 2 == 0 else -1
    # COMMON GROUND
    _place_metal3_fill(METAL3_SHORT_WIDTH, 12, 0)
    _place_metal3_fill(METAL3_SHORT_WIDTH, 9, 2, True)
    # PUC GROUND
    for i in range(2):
        for k in range(2):
            shift = -1 if k == 1 else 1
            puc = puc_matrix[0][i]
            port = gf.Port(
                "e1",
                width=11,
                layer=LAYER.metal3,
                port_type="electrical",
                center=(
                    puc[f"e{4 - k}"].x / 1000 + 5.5 * shift,
                    puc[f"e{4 - k}"].y / 1000 - 5.5,
                ),
                orientation=270,
            )
            st_ref = die << gf.c.straight(40 - 20 * i, cross_section=xs_m3_11)
            st_ref.connect("e1", port)
            bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m3_11)
            bend_ref.connect("e1", st_ref["e2"])
            st_ref = die << gf.c.straight(
                pad_matrix[0][2].x - bend_ref["e2"].x, cross_section=xs_m3_11
            )
            st_ref.connect("e1", bend_ref["e2"])

    # PUC SIGNALS
    for i in range(2):
        for k in range(2):
            puc = puc_matrix[0][i]
            if i == 0:
                pad = pad_matrix[6][k * 2]
            else:
                pad = pad_matrix[7 + k][1 + k]
            shift = 1 if k == 0 else -1
            port = gf.Port(
                "e1",
                width=11,
                layer=LAYER.metal3,
                port_type="electrical",
                center=(
                    puc[f"e{1 + k}"].x / 1000 + 5.5 * shift,
                    puc[f"e{1 + k}"].y / 1000 + 5.5,
                ),
                orientation=90,
            )
            port2 = gf.Port(
                "e1",
                width=11,
                layer=LAYER.metal3,
                port_type="electrical",
                center=(pad.x, pad.y),
                orientation=180 if k == 0 else 270,
            )
            gf.routing.route_single(
                die,
                port,
                port2,
                auto_taper=False,
                cross_section=xs_m3_11,
                bend=ipr.wire_corner45(radius=2, cross_section=xs_m3_11),
                end_straight_length=23,
                start_straight_length=195 if k == 1 and i == 0 else 15,
            )

    # UP PD SIGNALS
    for i in range(2):
        pad = pad_matrix[4 + i][i]
        pd = pd_matrix[0][i * 2]
        st_ref = die << gf.c.straight(5, cross_section=xs_m2_10)
        st_ref.connect("e1", pd["e2"])
        via_ref1 = die << via_m2_m1
        via_ref1.connect("e1", st_ref["e2"])
        port2 = gf.Port(
            "e1",
            width=11,
            layer=LAYER.metal3,
            port_type="electrical",
            center=(pad.x, pad.y),
            orientation=180,
        )
        st_ref = die << gf.c.straight(36, cross_section=xs_m3_11)
        st_ref.connect("e1", port2)
        via_ref = die << via_m3_m1
        via_ref.connect("e1", st_ref["e2"])
        tap_ref = die << metal1_taper
        tap_ref.connect("e2", via_ref["e2"], allow_layer_mismatch=True)
        gf.routing.route_single(
            die,
            tap_ref["e1"],
            via_ref1["e3"],
            auto_taper=False,
            cross_section=xs_m1_10,
            bend=ipr.wire_corner45(radius=2, cross_section=xs_m1_10),
            start_straight_length=30,
        )

    # UP PD GROUNDS
    for i in range(2):
        pd = pd_matrix[0][i * 2]
        port = gf.Port(
            "e1",
            width=10,
            layer=LAYER.metal2,
            port_type="electrical",
            center=(pd["e1"].x / 1000, pd["e1"].y / 1000 - 21.8),
            orientation=270,
        )
        st_ref = die << gf.c.straight(40, cross_section=xs_m2_10)
        st_ref.connect("e1", port)
        bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m2_10)
        bend_ref.connect("e1", st_ref["e2"])
        st_ref = die << gf.c.straight(51.63, cross_section=xs_m2_10)
        st_ref.connect("e1", bend_ref["e2"])
        bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m2_10)
        bend_ref.connect("e1", st_ref["e2"], mirror=True)
        st_ref = die << gf.c.straight(20, cross_section=xs_m2_10)
        st_ref.connect("e1", bend_ref["e2"])
        via_ref = die << via_m2_m1
        via_ref.connect("e1", st_ref["e2"])
        st_ref = die << gf.c.straight(405, cross_section=xs_m1_10)
        st_ref.connect("e1", via_ref["e3"], allow_layer_mismatch=True)
        tap_ref = die << metal1_taper
        tap_ref.connect("e1", st_ref["e2"])
        via_ref = die << via_m3_m1
        via_ref.connect("e1", tap_ref["e2"], allow_layer_mismatch=True)
        st_ref = die << gf.c.straight(20, cross_section=xs_m3_11)
        st_ref.connect("e1", via_ref["e3"])

    # LOW PD GROUND
    for i in range(2):
        st_ref = die << gf.c.straight(10, cross_section=xs_m2_10)
        st_ref.connect("e1", pd_matrix[1][1 + 2 * i]["e1"])
        via_ref = die << via_m2_m1
        via_ref.connect("e1", st_ref["e2"])
        st_ref = die << gf.c.straight(
            via_ref["e3"].y - pad_matrix[12][0].y - 63, cross_section=xs_m1_10
        )
        st_ref.connect("e1", via_ref["e3"], allow_layer_mismatch=True)
        tap_ref = die << metal1_taper
        tap_ref.connect("e1", st_ref["e2"])
        via_ref = die << via_m3_m1
        via_ref.connect("e1", tap_ref["e2"], allow_layer_mismatch=True)
        st_ref = die << gf.c.straight(50, cross_section=xs_m3_11)
        st_ref.connect("e1", via_ref["e3"])

    # LOW PD SIGNAL
    for i in range(2):
        pad = pad_matrix[10 + i][i]
        pd = pd_matrix[1][1 + 2 * i]
        st_ref = die << gf.c.straight(10, cross_section=xs_m2_10)
        st_ref.connect("e1", pd["e2"])
        tap_ref = die << metal2_taper
        tap_ref.connect("e1", st_ref["e2"])
        via_ref = die << via_m3_m2
        via_ref.connect("e1", tap_ref["e2"], allow_layer_mismatch=True)
        gf.routing.route_single(
            die,
            via_ref["e3"],
            pad["e1"],
            auto_taper=False,
            cross_section=xs_m3_11,
            bend=ipr.wire_corner45(radius=2, cross_section=xs_m3_11),
            start_straight_length=10,
        )

    #############################
    # THERMISTORS               #
    #############################
    th_matrix = v7b.build_matrix(
        die, "serie_thermistor*", area=(-11700, -11850, 11700, 11850)
    )
    th_taper = gf.c.taper(
        10,
        width1=3.1,
        width2=11,
        port_types=("electrical", "electrical"),
        port_names=("e1", "e2"),
        layer=LAYER.metal1,
    )
    pairs = [(0, 0), (5, 1), (3, 2), (1, 3), (3, 4), (4, 5), (0, 6), (2, 7), (5, 7)]
    for i in range(9):
        for k in range(2):
            tap_ref = die << th_taper
            tap_ref.connect("e1", th_matrix[pairs[i][0]][pairs[i][1]][f"e{k + 1}"])
            via_ref = die << via_m3_m1
            via_ref.connect("e1", tap_ref["e2"], allow_layer_mismatch=True)
            st_ref = die << gf.c.straight(50 if k == 0 else 15, cross_section=xs_m3_11)
            st_ref.connect("e1", via_ref["e3"])
            if k == 1:
                bend_ref = die << ipr.wire_corner45(radius=2, cross_section=xs_m3_11)
                bend_ref.connect("e1", st_ref["e2"], mirror=True)
                st_ref = die << gf.c.straight(50, cross_section=xs_m3_11)
                st_ref.connect("e1", bend_ref["e2"])

    #############################
    # METAL 3 SLOTS             #
    #############################
    die << fill_named_rectangles_fast(
        die,
        name_regex=r"rect.*",
        rect_layer=(28, 0),
        no_fill_layers=((118, 131),),
        slot_size=2.4,
        pitch=4.8,
        margin=2.4,
        keepout_gap=0.5,
    )

    die << fill_named_rectangles_fast(
        die,
        name_regex=r"circ.*",
        rect_layer=(28, 0),
        no_fill_layers=((118, 131),),
        slot_size=2.4,
        pitch=4.8,
        margin=2.4,
        keepout_gap=0.5,
    )

    die << fill_named_rectangles_fast(
        die,
        name_regex=r"rounded_triang.*",
        rect_layer=(28, 0),
        no_fill_layers=((118, 131),),
        slot_size=2.4,
        pitch=4.8,
        margin=2.4,
        keepout_gap=0.5,
    )

    #############################
    # DAISY CHAIN               #
    #############################
    # OUTTER DC
    search_areas = (
        (-11929.967, 11986.22, -7886.56, 12266.95),
        (-12116.34, -12123.62, -11855.86, 12088.27),
        (-11855.86, -12214.79, -7426.69, -11944.37),
        (7593.96, -12214.22, 11996.66, -11944.37),
        (11823.56, -11944.37, 12088.64, 12074.153),
        (7321.47, 11991.69, 11903.89, 12262.22),
    )
    for search_area in search_areas:
        pad_matrix = v7b.build_matrix(die, "flipchip_pad*", area=search_area)
        links = circle_connect.build_links(pad_matrix, width=20, axis="auto")
        circle_connect.place_connectors(die, links, dc_connector())

    # INNER DC
    search_areas = (
        (-529.96, 5831.29, -408.52, 7611.49),
        (190.72, 1357.46, 319.17, 2767.43),
        (-342.15, -618.43, -225.25, 588.26),
        (550.55, -805.97, 659.91, 603.35),
        (190.05, -2975.91, 316.76, -1562.67),
        (542.38, -7280.82, 668.53, -5514.17),
    )
    for search_area in search_areas:
        pad_matrix = v7b.build_matrix(die, "flipchip_pad*", area=search_area)
        links = circle_connect.build_links(
            pad_matrix,
            width=20,
            axis="column",
            max_length=2.5 * 90,
            fallback=Fallback(max_distance=1.5 * 180),
        )
        circle_connect.place_connectors(die, links, dc_connector())
