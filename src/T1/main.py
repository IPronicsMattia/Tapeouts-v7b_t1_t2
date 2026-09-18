import gdsfactory as gf
from component_placement import component_placement

die_name = "T1"
die = gf.Component(die_name)

die_border = die << gf.components.die(
    size=(
        25000.0,
        3780.0,
    ),
    die_name=None,
    bbox_layer=(118, 134),
    draw_corners=False,
    layer=None,
)
component_placement(die)
die_border2 = die << gf.components.die(
    size=(
        25000,
        3780,
    ),
    die_name=None,
    bbox_layer=(166, 0),
    draw_corners=False,
    layer=None,
)
die.show()
