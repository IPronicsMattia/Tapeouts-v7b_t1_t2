import math
import pathlib
import time

import gdsfactory as gf
import klayout.db as kdb

import v7b

start = time.time()

die_name = "v7b"
numbered_pucs = False

die = gf.Component(die_name)

die_border = die << gf.components.die(
    size=(
        25000,
        25000,
    ),
    die_name=None,
    bbox_layer=(118, 134),
    draw_corners=False,
    layer=None,
)

die_border2 = die << gf.components.die(
    size=(25000, 25150),
    die_name=None,
    bbox_layer=(166, 0),
    draw_corners=False,
    layer=None,
)

meshes = []
mua_in = []
mua_out = []
ec_in = []
ec_out = []


print("\n###############\nCOMPONENT PLACEMENT\n###############\n")
v7b.component_placement(die, meshes, mua_in, mua_out, ec_in, ec_out, numbered_pucs)

print(f"\nelapsed time:{math.ceil(time.time() - start)} seconds\n")

print("\n###############\nOPTICAL ROUTING\n###############\n")
v7b.optical_routing(die, meshes, mua_in, mua_out, ec_in, ec_out)

print(f"\nelapsed time:{math.ceil(time.time() - start)} seconds\n")

# print("\n###############\nNETLIST FLAT EXTRACTION\n###############\n")
# gdspath = pathlib.Path("mesh_die_netlist")
# nl_file = gdspath.with_suffix(".json")

# nl = v7b.get_netlist_flat(
#     component=die,
#     recursive_netlist=None,
#     output_path=nl_file,
# )

# print(f"Wrote netlist to '{nl_file}'")
# print(
#     f"  {nl['__states__']['paths']:,} routes over {nl['__states__']['pairs']:,} pairs"
# )

# print(f"\nelapsed time:{math.ceil(time.time() - start)} seconds\n")

# print("\n###############\nPAD PLACEMENT\n###############\n")
# print("Mesh Pads + Daisy chain\n")
# v7b.checkerboard_fill(
#     die,
#     offset=(72.861, -18.675),
#     keepout_layers=[(26, 0), (28, 0), (8, 0)],
#     draw_regions=False,
# )

# print(f"\nelapsed time:{math.ceil(time.time() - start)} seconds\n")

# print("\n###############\nELECTRICAL ROUTING\n###############\n")
# v7b.electrical_routing(die)

# print(f"\nelapsed time:{math.ceil(time.time() - start)} seconds\n")


# print("\n###############\nDUMMY PAD PLACEMENT\n###############\n")
# print("Mesh border dummy pads\n")
# DX = 11160

# MESH_BOXES = [
#     (-4729.11, 9754.53, -1231.12, 9929.72),
#     (-1406.03, 3273.34, -1230.84, 9751.74),
#     (-1228.42, 3273.63, -516.01, 3448.82),
#     (-693.7, -3211.81, -518.51, 3266.59),
#     (-516.37, -3211.99, 390.82, -3036.80),
#     (-9868.129, -9887.17, 387, -9700.98),
#     (-9868.47, -9705.17, -9693.28, 3260),
#     (-11389.68, 3082.1, -9872.771, 3257.29),
#     (-11393.9, 3273.34, -11218.71, 9751.74),
# ]


# def shift_x(boxes, dx, ndigits=3):
#     """Return boxes translated by dx along x (x0 and x1)."""
#     return [
#         (round(x0 + dx, ndigits), y0, round(x1 + dx, ndigits), y1)
#         for x0, y0, x1, y1 in boxes
#     ]


# v7b.checkerboard_fill(
#     die,
#     fill_regions=MESH_BOXES + shift_x(MESH_BOXES, DX),
#     offset=(72.861, -18.675),
#     layer_fill_region=(999, 2),
#     keepout_layers=[(26, 0), (28, 0), (18, 0), (8, 0)],
#     draw_regions=False,
# )

# print("Fill pads\n")
# v7b.checkerboard_fill(
#     die,
#     fill_regions=[(-11551.06, -11702.21, 11556.01, 11683.22)],
#     pitch=(180, 180),
#     offset=(72.861, -18.675),
#     layer_fill_region=(999, 3),
#     keepout_layers=[(26, 0), (28, 0), (18, 0), (8, 0)],
#     keepout_clearance=90,
#     draw_regions=False,
# )

# print(f"\nelapsed time:{math.ceil(time.time() - start)} seconds\n")

# print("\n###############\nELECTRICAL PAD MAPPING\n###############\n")
# DC_ZONES = [
#     (-11847.72, 11999.52, -8244.08, 12277.16),
#     (7949.77, 11986.83, 11916.95, 12284.54),
#     (11827.41, -11761.92, 12084.94, 11984.46),
#     (8396.78, -12235.4, 12009.9, -11949.51),
#     (-11761.65, -12227.91, -7799.16, -11942.24),
#     (-12121.04, -12139.47, -11858.23, 11995.52),
#     (-529.96, 5831.29, -408.52, 7611.49),
#     (190.72, 1357.46, 319.17, 2767.43),
#     (-342.15, -618.43, -225.25, 498.26),
#     (550.55, -805.97, 659.91, 603.35),
#     (190.05, -2975.91, 316.76, -1562.67),
#     (542.38, -7280.82, 668.53, -5514.17),
# ]

# ctx = v7b.PadMapContext(die, pad_glob="*flipchip_pad*")

# signals, diagnostics = v7b.assign_puc_signals(ctx)
# grounds, gnd_diag = v7b.assign_puc_grounds(ctx)
# pd_sig, _ = v7b.assign_pd_signals(ctx)
# pd_bias, _ = v7b.assign_pd_bias(ctx)
# th, th_diag = v7b.assign_thermistors(ctx, rows=3)
# dc, dc_diag = v7b.assign_dc_chains(ctx, DC_ZONES, directions=[None] * 12 + [-1] * 6)
# dummies, _ = v7b.assign_dummies(ctx)
# pic, pic_faults = v7b.load_pic_names("mesh_die_netlist.json")

# v7b.write_pad_mapping(
#     ctx,
#     signals,
#     grounds,
#     pd_sig,
#     pd_bias,
#     th,
#     dc,
#     dummies,
#     pic_names=pic,
#     path="pad_mapping.xlsx",
#     unresolved="ERROR",
# )

# print(f"\nelapsed time:{math.ceil(time.time() - start)} seconds\n")

# print("\n###############\nELECTRICAL ANGLE PATCHING\n###############\n")
# # Don't use this unless you already know if you need acute angle patches
# report = v7b.run(die, (28, 0))  # Amount can be detected using calibre rule 28.S.1
# v7b.summarise(report, 0.001)  # Compare with this result

# print(f"\nelapsed time:{math.ceil(time.time() - start)} seconds\n")

# print("\n###############\nHANDMADE DUMMIES FOR SI TRIANGLES\n###############\n")
# MESH_BOXES = [
#     # Upper Triangle
#     (-5072.05, 11452.81, 3951.05, 11477.06),
#     (-5792.38, 11486.56, 2926.98, 11510.81),
#     (-6515.44, 11519.85, 1917.76, 11544.10),
#     (-7234.27, 11553.25, 902.81, 11577.50),
#     (-7953.37, 11584.97, -368.66, 11609.22),
#     (-8675.24, 11618.47, -1382.88, 11642.72),
#     (-9391.67, 11651.31, -2398.82, 11675.56),
#     (-10110.35, 11685.04, -3415.47, 11709.29),
#     (-10918.40, 11718.24, -4422.67, 11742.49),
#     # Upper TM input
#     (-4528.87, 11007.09, 6263.25, 11298.72),
#     # Lower Triangle
#     (-3961.41, -11476.17, 5077.222, -11451.92),
#     (-2937.34, -11509.92, 5782.02, -11485.67),
#     (-1928.12, -11543.21, 6505.08, -11518.96),
#     (-913.17, -11576.61, 7223.91, -11552.36),
#     (358.30, -11608.33, 7943.01, -11584.08),
#     (1372.52, -11641.83, 8664.88, -11617.58),
#     (2388.46, -11674.67, 9381.31, -11650.42),
#     (3405.11, -11708.40, 10099.99, -11684.15),
#     (4412.31, -11741.60, 10908.04, -11717.35),
#     # Lower TE output
#     (-6272.98, -11304.09, 4542.06, -11012.46),
# ]

# for i in range(2):
#     MESH_BOXES.extend(
#         [
#             (-11516.3 + 11161 * i, 9749.01, -4856.35 + 11161 * i, 10062.504),
#             (-11516.94 + 11161 * i, 3378.24, -11225.57500 + 11161 * i, 10061.81),
#             (-10894.59 + 11161 * i, 2890.81, -10566.43 + 11161 * i, 9650.82500),
#             (-10894.59 + 11161 * i, 2890.81, -10172.82 + 11161 * i, 3187.77),
#             (-10481.88 + 11161 * i, -9572.757, -10172.82 + 11161 * i, 3187.77),
#             (-10133.64 + 11161 * i, 3278.14, -9830.22 + 11161 * i, 9535.51),
#             (-10133.02 + 11161 * i, -3117.53, -9831.96 + 11161 * i, 3256.77),
#             (-1311.02 + 11161 * i, 3220.53, -982.77 + 11161 * i, 9558.77),
#             (-1311.70 + 11161 * i, -3064.54, -982.77 + 11161 * i, 3184.97),
#             (-560.13 + 11161 * i, -3265.48, -235.96 + 11161 * i, 3081.72),
#             (-561.24 + 11161 * i, -9617.15, -235.96 + 11161 * i, -3292.63),
#             (165.00 + 11161 * i, -10074.88, 470.71 + 11161 * i, -3375.79500),
#             (-6314.79800 + 11161 * i, -10074.88, 470.71 + 11161 * i, -9764.23),
#         ]
#     )
# for k in range(2):
#     for j in range(2):
#         for i in range(3):
#             MESH_BOXES.extend(
#                 [
#                     (
#                         -9501.66 + j * 7322 + 11161 * k,
#                         3338.48 - 6485 * i,
#                         -8940.737 + j * 7322 + 11161 * k,
#                         9552.116 - 6485 * i,
#                     ),
#                     (
#                         -8819.74 + j * 6210 + 11161 * k,
#                         3338.48 - 6485 * i,
#                         -8516.82 + j * 6210 + 11161 * k,
#                         9552.11 - 6485 * i,
#                     ),
#                 ]
#             )
# for k in range(2):
#     for j in range(2):
#         for i in range(6):
#             MESH_BOXES.extend(
#                 [
#                     (
#                         -8180.71 + j * 4942 + 11161 * k,
#                         6569.79 - 3250 * i,
#                         -7892.139 + j * 4942 + 11161 * k,
#                         9571.91 - 3250 * i,
#                     ),
#                     (
#                         -7775.84 + j * 4258 + 11161 * k,
#                         6569.79 - 3250 * i,
#                         -7618.87 + j * 4258 + 11161 * k,
#                         9571.91 - 3250 * i,
#                     ),
#                 ]
#             )

# report = v7b.fill_component(die, MESH_BOXES)
# print(report.placed, report.ok)

die.show()

# opts = kdb.SaveLayoutOptions()
# opts.format = "OASIS"
# opts.oasis_compression_level = 10
# opts.oasis_strict_mode = True

# die.write("v7b_main.oas", save_options=opts)

# print(f"\nelapsed time:{math.ceil(time.time() - start)} seconds\n")
