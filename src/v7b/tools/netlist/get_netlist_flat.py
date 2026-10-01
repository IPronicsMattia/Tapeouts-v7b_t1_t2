from __future__ import annotations

import json
import re
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path
from typing import Any

import gdsfactory as gf
from gdsfactory.component import Component
from v7b.tools.netlist.topolux_states import attach_states

dict_components = {
    "bend_euler": "bend",
    "bend_euler_custom_width": "bend",
    "bend_bezier_s_custom_width": "bend_s",
    "rib_taper": "taper",
    "3d_crossing": "crossing_anwg_si",
    "crossing_3D": "crossing_anwg_si",
    "anwg_ec_oband": "edge_coupler",
    "edge_coupler_array": "edge_coupler",
    "si_anwg_transition": "vertical_transition",
    "si_psr_tw": "pbrs",
    "v7b_puc": "puc",
    "lateral_pd": "photodiode",
}


def get_netlist_flat(
    component: Component,
    recursive_netlist: None,
    *,
    puc_map_path: str | Path = "puc_map.json",
    output_path: str | Path | None = None,
    n_io: int = 72,
    states_kwargs: dict[str, Any] | None = None,
    **kwargs,
) -> dict[str, Any]:
    """Parses a recursive netlist for a component as if it was a single netlist \
            with its lowest-level instances.


    Args:
        component: to extract flat netlist.
        puc_map_path: the topolux selector map, used for
            ``__pic_to_topolux_ids__`` and, when sweeping, for the mesh plane
            tokens.  The only file this function reads.
        output_path: where to *write* the netlist, including ``__states__``.
            Nothing is read from it, and no netlist file has to exist
            beforehand: the sweep runs on the netlist assembled above, in
            memory.  None, the default, skips the sweep entirely and leaves
            every existing caller unaffected.
        n_io: number of input/output PSRs, when sweeping.
        states_kwargs: passed through to ``topolux_states.add_states`` --
            ``mode``, ``limit``, ``strict``, ``cutoff``, ``on_unmapped``.

    Keyword Args:
        component_suffix: suffix to append to each component name, useful if to save .
        get_netlist_func: function to extract individual netlists.
        tolerance: tolerance in nm to consider two ports connected.
        exclude_port_types: optional list of port types to exclude from netlisting.
        get_instance_name: function to get instance name.

    Returns:
        instances: Dict of instance name and settings.
        connections: Dict of Instance1Name,portName: Instance2Name,portName.
        placements: Dict of instance names and placements (x, y, rotation).
        port: Dict portName: ComponentName,port.
        name: name of component.
        warnings: warning messages (disconnected pins).
        __states__: with `output_path`, a summary of the sweep -- where the
            file went and what it holds.  The states themselves are only in
            that file: at roughly a gigabyte they cannot be carried in this
            dict, so **do not dump the returned dict over `output_path`**, or
            a summary would replace the payload it describes.  None when no
            sweep ran.
    """
    if not recursive_netlist:
        recursive_netlist = component.get_netlist(
            recursive=True, exclude_port_types=["electrical"], **kwargs
        )
        # recursive_netlist[k]["nets"] = new_nets2
        for k in recursive_netlist.keys():
            nets = list(recursive_netlist[k]["nets"])
            # print(nets)
            if "warnings" in recursive_netlist[k]:
                if "optical" in recursive_netlist[k]["warnings"]:
                    if (
                        "unconnected_ports"
                        in recursive_netlist[k]["warnings"]["optical"]
                    ):
                        un_ports = recursive_netlist[k]["warnings"]["optical"][
                            "unconnected_ports"
                        ][0]

                        ports = list(un_ports["ports"])
                        rest_ports = ports.copy()
                        for idx, port in enumerate(ports):
                            if port in rest_ports:
                                rest_ports.pop(rest_ports.index(port))
                            port_aux = ""
                            for port2 in rest_ports:
                                idx2 = ports.index(port2)
                                if (
                                    abs(
                                        un_ports["values"][idx][0]
                                        - un_ports["values"][idx2][0]
                                    )
                                    < 0.005
                                ):
                                    if (
                                        abs(
                                            un_ports["values"][idx][1]
                                            - un_ports["values"][idx2][1]
                                        )
                                        < 0.005
                                    ):
                                        nets.append(
                                            {
                                                "p1": port,
                                                "p2": port2,
                                            }
                                        )
                                        port_aux = port2
                                    else:
                                        continue
                                else:
                                    continue
                            if port_aux in rest_ports:
                                rest_ports.pop(rest_ports.index(port_aux))

                recursive_netlist[k]["nets"] = nets

    else:
        print("Netlist as a parameter")

    import pathlib

    gdspath = pathlib.Path(f"{component.name}_recursive_netlist")
    nl_file = gdspath.with_suffix(".json")
    nl_file.write_text(json.dumps(recursive_netlist, indent=2))
    print(f"Wrote raw netlist to '{nl_file}'")

    top_level_name = component.name
    nets_index = _build_nets_index(recursive_netlist)
    hierarchical_instances = _flatten_hierarchy(top_level_name, recursive_netlist)
    connections = {}
    placements = {}
    instances = {}
    for hierarchical_instance in hierarchical_instances:
        c, p = _map_connections_ports(
            hierarchical_instance, top_level_name, recursive_netlist, nets_index
        )
        for key, value in c.items():
            if len(value) == 0:
                continue  # skip empty lists
            target = value[0]
            # Check if key or its mirror already exists
            if key not in connections and connections.get(target) != key:
                connections[key] = target

        placements.update(
            _accumulate_placements(hierarchical_instance, recursive_netlist)
        )
        instances.update(_get_instance_info(hierarchical_instance, recursive_netlist))

    connections_fix = {}
    for key, value in connections.items():
        connections_fix[key] = [value]

    # ports = get_psr_ports(recursive_netlist, component)
    ports = get_ports(recursive_netlist, component)

    # change component names to generic name
    for instance in instances:
        component_name = instances[instance]["component"]
        if component_name in dict_components:
            instances[instance]["component"] = dict_components[component_name]

    sorted_pic_to_elec_id = get_pic_to_elec_id(instances, placements)

    # __pic_to_topolux_ids__
    data = json.loads(Path(puc_map_path).read_text())
    topo_te = data.get("TE", data)
    topo_tm = data.get("TM", data)

    netlist = {
        "name": recursive_netlist[top_level_name]["name"],
        "connections": connections_fix,
        "placements": placements,
        "instances": instances,
        "ports": ports,
        "__pic_to_elec_ids__": sorted_pic_to_elec_id,
        "__pic_to_topolux_ids__": {"TE": topo_te, "TM": topo_tm},
    }

    # __states__: every route of every (In, Out) pair, with the switch state
    # each one needs.  Enumerated from the netlist just assembled above -- no
    # earlier file, no separate run -- and streamed straight to disk rather
    # than returned, because it is far larger than everything above it put
    # together.
    netlist["__states__"] = (
        attach_states(
            netlist,
            data,
            output_path,
            n_io=n_io,
            **(states_kwargs or {}),
        )
        if output_path
        else None
    )
    return netlist


# a placed instance's leaf token ends in its coordinates, optionally a rotation:
# "puc2100_5526055_m1067295", "pucmua72_6403363_10209644_A270"
_PLACEMENT_SUFFIX = re.compile(r"_(m?\d+)_(m?\d+)(_[AMR]\d+)*$")

_PUC = re.compile(r"^puc(?P<mua>mua)?(?P<n>\d+)$")
_PD = re.compile(r"^lateral_pd_puc(?P<mua>mua)?(?P<n>\d+)$")
_TH = re.compile(r"^serie_thermistor")


def get_pic_to_elec_id(
    instances: dict[str, dict],
    placements: dict[str, dict],
    *,
    thermistor_rows: int = 3,
    strict: bool = True,
) -> dict[str, dict[str, str]]:
    """Electrical names for every PUC, photodiode and thermistor instance.

    Args:
        instances: netlist ``instances`` block, keyed by full instance name.
        placements: netlist ``placements`` block, same keys, ``x``/``y`` in um.
        thermistor_rows: how many rows the thermistors form on the die.
        strict: raise if anything is unpaired, miscounted or unrecognised.
            Set False to get a best-effort map instead.

    Returns:
        ``{instance name: {port key: electrical name}}``.  PUCs carry ``btm``
        and ``top``, photodiodes ``pd``, thermistors ``th``.

    Raises:
        ValueError: with every fault listed, when ``strict`` and the layout does
            not match the assumptions above.
    """
    faults: list[str] = []

    pucs: dict[str, list[str]] = {}
    pds: dict[str, list[str]] = {}
    ths: list[str] = []

    for name, inst in instances.items():
        cell = _cell(name)
        component = inst.get("component", "")
        if _PD.match(cell):
            if "photodiode" not in component:
                faults.append(
                    f"{name}: {cell} looks like a PD but component is {component!r}"
                )
                continue
            pds.setdefault(cell, []).append(name)
        elif _PUC.match(cell):
            if "puc" not in component:
                faults.append(
                    f"{name}: {cell} looks like a PUC but component is {component!r}"
                )
                continue
            pucs.setdefault(cell, []).append(name)
        elif _TH.match(cell):
            ths.append(name)

    missing = [
        n
        for n in list(ths)
        + [n for g in pucs.values() for n in g]
        + [n for g in pds.values() for n in g]
        if n not in placements
    ]
    faults += [f"{n}: no placement" for n in missing]

    def x(n: str) -> float:
        return placements[n]["x"]

    def y(n: str) -> float:
        return placements[n]["y"]

    pic_to_elec: dict[str, dict[str, str]] = {}

    # ---- PUCs: two instances per cell, lower x is TE -------------------- #
    for cell, group in sorted(pucs.items()):
        m = _PUC.match(cell)
        number, mua = m["n"], "_MUA" if m["mua"] else ""
        if len(group) != 2 or any(n in missing for n in group):
            faults.append(f"{cell}: instanced {len(group)} times, expected 2")
            continue
        te, tm = sorted(group, key=x)
        if x(tm) - x(te) < 1e-6:
            faults.append(f"{cell}: both instances share an x, TE/TM undecidable")
            continue
        for inst_name, pol in ((te, "TE"), (tm, "TM")):
            pic_to_elec[inst_name] = {
                "btm": f"PUC{number}_bot{mua}_{pol}",
                "top": f"PUC{number}_top{mua}_{pol}",
            }

    # ---- photodiodes: one per mesh PUC, two per MUA PUC ----------------- #
    for cell, group in sorted(pds.items()):
        m = _PD.match(cell)
        number, mua = m["n"], bool(m["mua"])
        per_half = 2 if mua else 1
        if len(group) != 2 * per_half or any(n in missing for n in group):
            faults.append(
                f"{cell}: {len(group)} instances, expected {2 * per_half} "
                f"({'MUA' if mua else 'mesh'})"
            )
            continue
        by_x = sorted(group, key=x)
        halves = (by_x[:per_half], by_x[per_half:])
        if x(halves[1][0]) - x(halves[0][-1]) < 1e-6:
            faults.append(f"{cell}: the two halves are not separated in x")
            continue
        for half, pol in zip(halves, ("TE", "TM")):
            if not mua:
                pic_to_elec[half[0]] = {"pd": f"PD{number}_MESH_{pol}"}
                continue
            bot, top = sorted(half, key=y)
            if y(top) - y(bot) < 1e-6:
                faults.append(
                    f"{cell} ({pol}): both PDs share a y, top/bot undecidable"
                )
                continue
            pic_to_elec[bot] = {"pd": f"PD{number}_bot_MUA_{pol}"}
            pic_to_elec[top] = {"pd": f"PD{number}_top_MUA_{pol}"}

    # ---- thermistors: reading order, left to right then top to bottom --- #
    if ths:
        placed = [n for n in ths if n not in missing]
        by_y = sorted(placed, key=lambda n: -y(n))
        if thermistor_rows > len(by_y):
            faults.append(f"{len(by_y)} thermistors cannot form {thermistor_rows} rows")
        else:
            rows = _rows([y(n) for n in by_y], thermistor_rows)
            ordered: list[str] = []
            for r in range(thermistor_rows):
                ordered += sorted((n for n, k in zip(by_y, rows) if k == r), key=x)
            for i, th in enumerate(ordered):
                pic_to_elec[th] = {"th": f"TH_{i}_S"}

    if faults and strict:
        raise ValueError("pic_to_elec mapping failed:\n  " + "\n  ".join(faults))
    return pic_to_elec


def get_ports(recursive_netlist, component):
    ports = {}
    instances = recursive_netlist[component.name]["instances"]

    ecs = [
        name
        for name, inst in instances.items()
        if "edge_coupler_array" in name and inst["settings"].get("n") == 88
    ]

    num = 8
    extra = 8
    for i in range(74):
        if i not in [36, 37]:
            ports.update(
                {f"Out{num - extra + 1}": f"{component.name}~{ecs[0]}~ec_{num},o2"}
            )
        else:
            extra += 1
        num += 1

    num = 8
    extra = 8
    for i in range(74):
        if i not in [36, 37]:
            ports.update(
                {f"In{num - extra + 1}": f"{component.name}~{ecs[1]}~ec_{num},o2"}
            )
        else:
            extra += 1
        num += 1

    return ports


def get_psr_ports(recursive_netlist, component):
    def _parse_xy(name: str) -> tuple[int, int]:
        parts = name.split("_")
        # name format: si_psr_tw_<x>_<y>_... where M prefix means negative
        x_str, y_str = parts[3], parts[4]
        x = -int(x_str[1:]) if x_str.lower().startswith("m") else int(x_str)
        y = -int(y_str[1:]) if y_str.lower().startswith("m") else int(y_str)
        return x, y

    all_psrs = [
        k for k in recursive_netlist[component.name]["instances"] if "si_psr_tw" in k
    ]
    ys = [_parse_xy(p)[1] for p in all_psrs]
    mid_y = (min(ys) + max(ys)) / 2

    # # In: left half, top-left first (x asc, y desc)
    # in_psrs = sorted(
    #     (p for p in all_psrs if _parse_xy(p)[0] < mid_x),
    #     key=lambda name: (_parse_xy(name)[0], -_parse_xy(name)[1]),
    # )
    # # Out: right half, top-right first (x desc, y desc)
    # out_psrs = sorted(
    #     (p for p in all_psrs if _parse_xy(p)[0] >= mid_x),
    #     key=lambda name: (-_parse_xy(name)[0], -_parse_xy(name)[1]),
    # )
    # In: top half, left first (x asc)
    in_psrs = sorted(
        (p for p in all_psrs if _parse_xy(p)[1] > mid_y),
        key=lambda name: (_parse_xy(name)[0], -_parse_xy(name)[1]),
    )
    # Out: bot half, left first (x asc)
    out_psrs = sorted(
        (p for p in all_psrs if _parse_xy(p)[1] < mid_y),
        key=lambda name: (_parse_xy(name)[0], -_parse_xy(name)[1]),
    )

    ports = {}
    for i, psr_name in enumerate(in_psrs):
        num = i + 1
        ports[f"In{num}_TE"] = f"{component.name}~{psr_name},o3"
        ports[f"In{num}_TM"] = f"{component.name}~{psr_name},o4"
    for i, psr_name in enumerate(out_psrs):
        num = i + 1
        ports[f"Out{num}_TE"] = f"{component.name}~{psr_name},o3"
        ports[f"Out{num}_TM"] = f"{component.name}~{psr_name},o4"

    return ports


@lru_cache(maxsize=512)
def _get_component_ports(name: str) -> list[str]:
    try:
        return [p.name for p in gf.get_component(name).ports]
    except ValueError:
        return []


def _build_nets_index(
    recursive_netlist: dict,
) -> dict[str, dict[str, list[str]]]:
    """Pre-index nets per component for O(1) port lookup instead of O(nets) linear scan."""
    nets_index: dict[str, dict[str, list[str]]] = {}
    for comp_name, comp_data in recursive_netlist.items():
        idx: dict[str, list[str]] = {}
        for item in comp_data.get("nets", []):
            p1, p2 = item["p1"], item["p2"]
            if p1 != p2:
                idx.setdefault(p1, []).append(p2)
                idx.setdefault(p2, []).append(p1)
        nets_index[comp_name] = idx
    return nets_index


def _cell(name: str) -> str:
    """The leaf cell name of a hierarchical instance name.

    Args:
        name: full instance name, ``~``-separated, e.g.
            ``v7b~mesh_72x72_CF..~inner_mesh_core_..~puc2100_5526055_m1067295``.

    Returns:
        The leaf token with its placement suffix stripped, e.g. ``puc2100``.
    """
    return _PLACEMENT_SUFFIX.sub("", name.rsplit("~", 1)[-1])


def _rows(ys: list[float], rows: int) -> list[int]:
    """Cut a descending y sequence into ``rows`` groups at its largest gaps.

    Args:
        ys: y values, already sorted descending.
        rows: expected number of rows.

    Returns:
        For each entry, its row index.
    """
    gaps = [(ys[i] - ys[i + 1], i) for i in range(len(ys) - 1)]
    cuts = {i for _, i in sorted(gaps, reverse=True)[: rows - 1]}
    out, row = [], 0
    for i in range(len(ys)):
        if i and i - 1 in cuts:
            row += 1
        out.append(row)
    return out


def _flat_name(
    hierarchy,
    hierarchy_delimiter: str = "~",
):
    """Returns a unique name for the instance from its hierarchy."""
    name = ""
    for _, instance in hierarchy[:-1]:
        name += instance
        name += hierarchy_delimiter
    name += hierarchy[-1][1]
    return name


def _get_instance_info(hierarchy, recursive_netlist):
    """Returns instance info from its instance data."""
    return {
        _flat_name(hierarchy): recursive_netlist[hierarchy[-2][0]]["instances"][
            hierarchy[-1][1]
        ]
    }


def _get_leaf(
    instance_port,
    netlist,
    flat_name,
    all_netlists,
    hierarchy_delimiter: str = "~",
):
    """Given a instance, port and its netlist, maps ports down to the lowest hierarchy level."""
    instance, port = instance_port.split(",")
    netlist = all_netlists[netlist]["instances"][instance]["component"]
    found_lower_level = netlist in all_netlists.keys()

    if found_lower_level and port in all_netlists[netlist]["ports"]:
        instance_port = all_netlists[netlist]["ports"][port]
        flat_name = f"{flat_name}{hierarchy_delimiter}{instance}"
        found_lower_level, flat_name = _get_leaf(
            instance_port, netlist, flat_name, all_netlists
        )

    else:
        found_lower_level = False
        flat_name = f"{flat_name}{hierarchy_delimiter}{instance_port}"
    return found_lower_level, flat_name


def _lateral_map(
    local_leaf_port: str,
    all_netlists: dict[str, Any],
    higher_component: str,
    level: int,
    hierarchy,
    nets_index: dict[str, dict[str, list[str]]],
    hierarchy_delimiter: str = "~",
):
    """Returns connected ports at this hierarchical level."""
    connected_ports = nets_index.get(higher_component, {}).get(local_leaf_port, [])
    if not connected_ports:
        return []
    flat_name_prefix = _flat_name(hierarchy[: len(hierarchy) - level - 1])
    return [
        _get_leaf(p, higher_component, flat_name_prefix, all_netlists)[1]
        for p in connected_ports
    ]


def _map_connections_ports(
    hierarchy,
    top_name,
    all_netlists,
    nets_index: dict[str, dict[str, list[str]]],
    hierarchy_delimiter: str = "~",
):
    """Returns all nodes of interest across the flat recursive netlist."""
    connections = {}
    ports = {}

    # Starting point is ports of the leaf instance
    leaf_instance = hierarchy[-1][1]
    leaf_instance_name = hierarchy[-1][0].split(".")[-1]
    leaf_instance_ports = _get_component_ports(leaf_instance_name)

    for leaf_portname in leaf_instance_ports:
        current_connections = []
        current_ports = []
        local_leaf_port = f"{leaf_instance},{leaf_portname}"
        for level, (higher_component, higher_instance) in enumerate(
            hierarchy[:-1][::-1]
        ):
            # Identify connected node (with flattened names)
            current_connections.extend(
                _lateral_map(
                    local_leaf_port,
                    all_netlists,
                    higher_component,
                    level,
                    hierarchy,
                    nets_index,
                    hierarchy_delimiter,
                )
            )
            # Traverse up to higher level
            found_higher_level = False
            for portname, port in all_netlists[higher_component]["ports"].items():
                if local_leaf_port == port:
                    local_leaf_port = f"{higher_instance},{portname}"
                    found_higher_level = True
                    # If there is a port at top level, map to that as well
                    if higher_instance == top_name:
                        current_ports.append(local_leaf_port)
            if not found_higher_level:
                break
        flat_leaf_port = f"{_flat_name(hierarchy)},{leaf_portname}"
        connections[flat_leaf_port] = current_connections
        ports[flat_leaf_port] = current_ports

    return connections, ports


def _accumulate_placements(
    hierarchy,
    all_netlists,
):
    """Iterate through hierarchy tuples, accumulating placement information."""
    placements = dict.fromkeys(["x", "y", "mirror", "rotation"], 0)
    for (higher_component, _higher_instance), (_lower_component, lower_instance) in zip(
        hierarchy[:-1], hierarchy[1:]
    ):
        for key in ["x", "y", "mirror", "rotation"]:
            value = (
                all_netlists.get(higher_component, {})
                .get("placements", {})
                .get(lower_instance, {})
                .get(key, None)
            )
            if value is not None:
                placements[key] += value

    return {_flat_name(hierarchy): placements}


def _flatten_str_list(xs):
    """Flatten nested list of strings to list of strings."""
    for x in xs:
        if isinstance(x, Iterable) and not isinstance(x, str | bytes):
            yield from _flatten_str_list(x)
        else:
            yield x


def _flatten_hierarchy(
    netlist_name: str,
    all_netlists: list[dict[str, Any]],
    hierarchy_delimiter: str = "~",
    component_instance_delimiter: str = ";",
):
    """Converts _flatten_netlist output str's to list of hierarchical (component, instance) tuples."""

    instance_dict = _flatten_hierarchy_recurse(
        netlist_name=netlist_name,
        all_netlists=all_netlists,
        hierarchy_delimiter=hierarchy_delimiter,
        component_instance_delimiter=component_instance_delimiter,
    )

    hierarchies_lists = []
    for hierarchy in _flatten_str_list(list(instance_dict.keys())):
        hierarchy_list = []
        levels = hierarchy.split(hierarchy_delimiter)
        for level in levels:
            components, instance = level.split(component_instance_delimiter)
            hierarchy_list.append((components, instance))
        hierarchies_lists.append(hierarchy_list)

    return hierarchies_lists


def _flatten_hierarchy_recurse(
    netlist_name: str,
    all_netlists: list[dict[str, Any]],
    hierarchy: str | None = None,
    hierarchy_delimiter: str = "~",
    component_instance_delimiter: str = ";",
) -> dict[str, Any]:
    """Flattens the provided recursive netlist by recursively updating a list.

    Args:
        netlist_name: netlist entry to flatten
        all_netlists: list of all possible netlists (output of get_netlist_recursive)
        hierarchy: str to append to netlist_name
        hierarchy_delimiter: str to separate hierarchy levels in flattened keys
        component_instance_delimiter: str to separate instance name from component name for netlist reconstruction

    Returns:
        str of ...{hierarchy_delimiter}{component}{component_instance_delimiter}{instance}{hierarchy_delimiter} used to flatten the netlist
    """
    instance_dict = {}
    if hierarchy is None:
        top_component = all_netlists[netlist_name]["name"]
        hierarchy = f"{top_component}{component_instance_delimiter}{netlist_name}"
    for instance_name, instance in all_netlists[netlist_name]["instances"].items():
        component_name = instance["component"]
        hierarchy_str = f"{hierarchy}{hierarchy_delimiter}{component_name}{component_instance_delimiter}{instance_name}"
        if component_name not in all_netlists.keys():
            instance_dict[hierarchy_str] = True  # Done for this leaf
        else:
            instance_dict.update(
                _flatten_hierarchy_recurse(
                    component_name,
                    all_netlists,
                    hierarchy_str,
                )
            )

    return instance_dict
