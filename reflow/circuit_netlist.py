"""tscircuit circuit.json -> Netlist.  OWNER: AGENT (task V-10, DECISIONS V-1).

Contract
--------
    load_circuit_json(path) -> reflow.netlist.Netlist

Reads only the source_* elements that `tsci export -f circuit-json` writes
(checked against tsci 0.0.2768). Every other element type is ignored.

- Components: one per source_component, keyed by its `name` ("U1").
- Pins: one per source_port, keyed by `str(pin_number)`. `function` is the
  port name exactly as the TSX labelled it. `pintype` is always "": pin kinds
  come only from a trusted pin map (V-12), never from the design.
- Nets: ports are grouped by `subcircuit_connectivity_map_key`. A group with
  a source_net takes that net's name. A group without one is
  `Net-(<ref>-<pin name>)` after its first pin (by ref, then pin number), or
  `unconnected-(<ref>-<pin name>-Pad<n>)` when it has a single port.
- Output order is deterministic: nets by name, pins by ref then pin number.

Raises CircuitJsonError for an unreadable or malformed file, a missing key,
a duplicate reference or pin number, a port on an unknown component, one
net name on two separate nets, or more than one subcircuit. Raises
MergedNetsError when two named nets share one connectivity key, e.g. a
trace from net.V3_3 to net.GND: picking one name would hide the short.

Must never
----------
- read the .kicad_sch or .kicad_pcb export, or call tsci,
- set a pin type or rename a pin from the TSX labels,
- pick one name for two connected named nets,
- read a part number into anything.
"""
from __future__ import annotations

import json
from pathlib import Path

from reflow.netlist import Component, Netlist, Pin


class CircuitJsonError(ValueError):
    """circuit.json is unreadable, malformed, or ambiguous."""


class MergedNetsError(CircuitJsonError):
    """Two named nets are connected to each other."""


_COMPONENT_KEYS = ("source_component_id", "name")
_PORT_KEYS = ("source_port_id", "source_component_id", "name", "pin_number")
_VALUE_KEYS = ("display_value", "display_resistance", "display_capacitance", "display_inductance")


def load_circuit_json(path) -> Netlist:
    elements = _read(Path(path))
    components, by_id = _components(elements)
    ports = _ports(elements, by_id)
    names = _net_names(elements)

    groups: dict[str, list[tuple[str, dict]]] = {}
    lone: list[tuple[str, dict]] = []
    for ref, port in ports:
        key = port.get("subcircuit_connectivity_map_key")
        if key:
            groups.setdefault(key, []).append((ref, port))
        else:
            lone.append((ref, port))

    nets: dict[str, list[Pin]] = {}
    for key, members in groups.items():
        _add_net(nets, _group_name(key, members, names), members, components)
    for ref, port in lone:
        _add_net(nets, _unconnected(ref, port), [(ref, port)], components)
    return Netlist(components=components, nets={name: nets[name] for name in sorted(nets)})


def _read(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CircuitJsonError(f"{path}: {exc.strerror or exc}") from exc
    except json.JSONDecodeError as exc:
        raise CircuitJsonError(f"{path}: invalid JSON ({exc.msg})") from exc
    if not isinstance(data, list):
        raise CircuitJsonError(f"{path}: expected a list of elements")
    for index, element in enumerate(data):
        if not isinstance(element, dict) or not isinstance(element.get("type"), str):
            raise CircuitJsonError(f"{path}: element {index} has no type")
    return data


def _require(element: dict, keys: tuple[str, ...]) -> None:
    for key in keys:
        if key not in element:
            raise CircuitJsonError(f"{element['type']} is missing {key}")


def _components(elements: list[dict]) -> tuple[dict[str, Component], dict[str, str]]:
    components: dict[str, Component] = {}
    by_id: dict[str, str] = {}
    for element in elements:
        if element["type"] != "source_component":
            continue
        _require(element, _COMPONENT_KEYS)
        cid, ref = element["source_component_id"], element["name"]
        if ref in components or cid in by_id:
            raise CircuitJsonError(f"duplicate component {ref} ({cid})")
        by_id[cid] = ref
        components[ref] = Component(
            ref=ref,
            value=next((str(element[k]) for k in _VALUE_KEYS if element.get(k)), ""),
            footprint="",
            lib="tscircuit",
            part=str(element.get("ftype", "")),
        )
    return components, by_id


def _ports(elements: list[dict], by_id: dict[str, str]) -> list[tuple[str, dict]]:
    ports: list[tuple[str, dict]] = []
    seen: set[tuple[str, int]] = set()
    subcircuits: set[str] = set()
    for element in elements:
        if element["type"] != "source_port":
            continue
        _require(element, _PORT_KEYS)
        ref = by_id.get(element["source_component_id"])
        if ref is None:
            raise CircuitJsonError(
                f"port {element['source_port_id']} is on unknown component {element['source_component_id']}"
            )
        number = element["pin_number"]
        if isinstance(number, bool) or not isinstance(number, int):
            raise CircuitJsonError(f"{ref} port {element['name']} has a non-integer pin_number")
        if (ref, number) in seen:
            raise CircuitJsonError(f"{ref} has two ports with pin number {number}")
        seen.add((ref, number))
        if element.get("subcircuit_id"):
            subcircuits.add(element["subcircuit_id"])
        ports.append((ref, element))
    if len(subcircuits) > 1:
        raise CircuitJsonError(f"more than one subcircuit is not supported: {sorted(subcircuits)}")
    return ports


def _net_names(elements: list[dict]) -> dict[str, list[str]]:
    """{connectivity key: [source_net names]}. A name used on two keys raises."""
    names: dict[str, list[str]] = {}
    key_of: dict[str, str] = {}
    for element in elements:
        if element["type"] != "source_net":
            continue
        _require(element, ("name",))
        key = element.get("subcircuit_connectivity_map_key")
        if not key:
            continue
        name = element["name"]
        if key_of.setdefault(name, key) != key:
            raise CircuitJsonError(f"net name {name} is used for two separate nets")
        if name not in names.setdefault(key, []):
            names[key].append(name)
    return names


def _group_name(key: str, members: list[tuple[str, dict]], names: dict[str, list[str]]) -> str:
    named = sorted(names.get(key, []))
    if len(named) > 1:
        raise MergedNetsError(f"named nets {' and '.join(named)} are connected to each other")
    if named:
        return named[0]
    if len(members) == 1:
        return _unconnected(*members[0])
    ref, port = min(members, key=lambda item: (item[0], item[1]["pin_number"]))
    return f"Net-({ref}-{port['name']})"


def _unconnected(ref: str, port: dict) -> str:
    return f"unconnected-({ref}-{port['name']}-Pad{port['pin_number']})"


def _add_net(nets: dict[str, list[Pin]], name: str, members: list[tuple[str, dict]],
             components: dict[str, Component]) -> None:
    if name in nets:
        raise CircuitJsonError(f"two separate nets would both be named {name}")
    pins = []
    for ref, port in sorted(members, key=lambda item: (item[0], item[1]["pin_number"])):
        pin = Pin(ref=ref, pin=str(port["pin_number"]), net=name, pintype="", function=port["name"])
        components[ref].pins[pin.pin] = pin
        pins.append(pin)
    nets[name] = pins
