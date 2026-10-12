import json
from collections import Counter
from pathlib import Path

import networkx as nx
import pandas as pd
from v7b.tools.netlist.nxgraph import create_nxgraph


def pairwise(iterable):
    a = iter(iterable)
    return zip(a, a, strict=False)


netlist = json.loads(
    (Path(__file__).parents[2] / "output/v7b_netlist.json").read_text()
)

# create graph from the netlist
circuit_graph = create_nxgraph(netlist)

# get the ports from the netlist
ports = netlist["ports"]
inputs = []
outputs = []
tapers = []
bends = []
bends_45 = []
crossings = []
crossings2 = []
pucs = []
lenghts_041 = []
lenghts_150 = []
lengths_si2 = []
pbrs = []
path_puc = []
count = 0
straight_150_diff = []
straight_041_diff = []


for j in range(2):
    for i in range(72):
        if j == 0:
            input_port = ports[f"In{i + 1}"]
        else:
            input_port = ports[f"Out{i + 1}"]
        print(input_port)
        if j == 0:
            output_port = f"v7b~mesh_72x72_mockup_m11203850_m9718075,o{72 - i}"
            # output_port = f"v7b~mesh_72x72_mockup_m80714_m9718075,o{72-i}"
            # output_port = f"v7b~mesh_72x72_CFinner_mesh_e69a7c48_m5566564_9695575~puc{71 - i}_m5535080_m{6397870 - 90000 * i},o1"
        else:
            output_port = f"v7b~mesh_72x72_mockup_m80714_m9718075,o{73 + i}"
            # output_port = f"v7b~mesh_72x72_mockup_m11203850_m9718075,o{73+i}"
            # output_port = f"v7b~mesh_72x72_CFinner_mesh_e69a7c48_5556565_9695575~puc{2663 - i}_5550195_m{19357870 - 90000 * i},o3"
        paths = nx.all_simple_paths(circuit_graph, input_port, output_port)
        straights = []
        count = 0
        for path in paths:
            count += 1
            path_components = []
            length_15 = 0
            length_41 = 0
            length_si2 = 0
            bend45 = 0
            bend = 0
            pucs_array = []
            for x, y in pairwise(path):
                component_label, inport = x.split(",")
                component_label, outport = y.split(",")
                path_components.append(
                    netlist["instances"][component_label]["component"]
                )
                if "puc" in netlist["instances"][component_label]["component"]:
                    pucs_array.append(component_label.split("~")[-1])
                if "straight" in netlist["instances"][component_label]["component"]:
                    width = netlist["instances"][component_label]["info"]["width"]
                    scale = 1
                    length_info = netlist["instances"][component_label]["info"][
                        "length"
                    ]
                    if width == 0.93:
                        length_15 += length_info / scale
                    elif width == 2.00:
                        length_si2 += length_info / scale
                    else:
                        length_41 += length_info / scale
                elif "bend" in netlist["instances"][component_label]["component"]:
                    # angle = netlist["instances"][component_label]["settings"]["angle"]
                    # if abs(angle) == 45:
                    #     bend45 += 1
                    # else:
                    bend += 1

            element_counts = Counter(path_components)
            if element_counts["puc"] == 2 and element_counts["pbrs"] == 2:
                if j == 0:
                    inputs.append(f"IN{i}")
                    outputs.append(f"MESH{i}")
                else:
                    inputs.append(f"OUT{i}")
                    outputs.append(f"MESH{i}")
                tapers.append(element_counts["taper"])
                bends.append(bend)
                bends_45.append(bend45)
                crossings.append(element_counts["crossing"])
                crossings2.append(element_counts["crossing_anwg_si"])
                pucs.append(element_counts["puc"])
                pbrs.append(element_counts["pbrs"])
                lenghts_041.append(length_41)
                lenghts_150.append(length_15)
                lengths_si2.append(length_si2)
                if len(straight_150_diff) < 1:
                    straight_150_diff.append(0)
                    straight_041_diff.append(0)
                else:
                    straight_150_diff.append(lenghts_150[-2] - lenghts_150[-1])
                    straight_041_diff.append(lenghts_041[-2] - lenghts_041[-1])

df = pd.DataFrame(
    {
        "Input": inputs,
        "Output": outputs,
        "pucs": pucs,
        "pbrs": pbrs,
        "crossing monolayer": crossings,
        "crossing duolayer": crossings2,
        "bends": bends,
        "bends 45": bends_45,
        "tapers": tapers,
        "Lenght 0.41um": lenghts_041,
        "Lenght 1.5um": lenghts_150,
        "Length Si2": lengths_si2,
        "L041 diff": straight_041_diff,
        "L150 diff": straight_150_diff,
    }
)
print(df)
df.to_csv(Path(__file__).parents[2] / "output" / "v7b_paths_simplified.csv")
# writer = pd.ExcelWriter(Path(__file__).parents[2] / "output" /"v7b_paths_simplified.xlsx", engine="openpyxl")
# wb = writer.book
# df.to_excel(writer, index=False)
# wb.save(Path(__file__).parents[2] / "output" /"v7b_paths_simplified.xlsx")
