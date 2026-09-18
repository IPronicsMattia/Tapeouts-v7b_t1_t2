import gdsfactory as gf

import T2

# Name of the die
die_name = "T2"
die = gf.Component(die_name)

# Place the Frame of the DIE (all components including trenches are inside)
die_border = die << gf.components.die(
    size=(25000.0, 3780.0),
    die_name=None,
    bbox_layer=(118, 134),
    draw_corners=False,
    layer=None,
)

# Place the data extent layer (all components except trenches are inside)
die_border2 = die << gf.components.die(
    size=(
        25000.0 + 75,
        3780 + 75 * 2,
    ),
    die_name=None,
    bbox_layer=(166, 0),
    draw_corners=False,
    layer=None,
)
die_border2.movex(-75 / 2)

# Add all needed components to the die
T2.component_placement(die=die)
die.show()
