"""A testbench's inputs, read from a real board.  Task L-12 (DECISIONS L-2a), agent under O-1c.

Contract
--------
    supply_volts(text) -> float | None
    decoupling_board(netlist, circuit_json, *, ic_ref, supply_v, pcb=False) -> Found
    i2c_board(netlist, *, ic_ref, line, supply_v) -> Found

`netlist` is the board with its IC pins bound to the trusted pin map (so pin
names and power pins are the datasheet's, not the design's labels).

- Decoupling: the IC's first supply pin (a `power_in` pin whose name isn't a
  ground name). A cap with one pin on that net and the other on ground is the
  decoupling cap. A cap with one pin on that net and the other on another
  supply net is a series cap. Neither: no cap. With `pcb=True`, the path is the
  routed trace between the cap pad and the pin when one trace joins them,
  else the straight-line pad distance (`path_estimated`, a lower bound).
- I²C: the IC's pin named `line`. A resistor from its net to any non-ground
  net is the pull-up.

A board the testbench can't represent is refused (`board` None, `reason`
set): a supply pin connected to nothing, an I²C pin on no bus, a value that
won't parse.

Must never
----------
- guess a value the board doesn't have (assumptions belong to the testbench and are labelled there),
- read pin names from the design's labels instead of the bound netlist.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from reflow.parts.catalog import CatalogError, parse_value
from reflow.learn.sim import DecouplingBoard, I2cBoard

_GROUND = re.compile(r"^/?(GND|VSS|AGND|DGND|PGND|GROUND|0V|EP|PAD)\w*$", re.IGNORECASE)


@dataclass
class Found:
    board: object | None
    refs: list[str] = field(default_factory=list)
    reason: str = ""


def supply_volts(text: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*V\b", text or "")
    return float(match.group(1)) if match else None


def decoupling_board(netlist, circuit_json, *, ic_ref: str, supply_v: float, pcb: bool = False) -> Found:
    ic = netlist.components.get(ic_ref)
    if ic is None:
        return Found(None, reason=f"{ic_ref} isn't on this board")
    supply = next((p for p in sorted(ic.pins.values(), key=_pin_order)
                   if p.pintype == "power_in" and not _is_ground_name(p.function) and not _is_ground_net(p.net)), None)
    if supply is None:
        return Found(None, reason=f"{ic_ref} has no supply pin in its pin map")
    if netlist.is_unconnected(supply.net) or len(netlist.nets.get(supply.net, [])) < 2:
        return Found(None, reason=f"{ic_ref}.{supply.function} (pin {supply.pin}) is not connected to anything, "
                                  "so there's no supply to simulate")
    shunt, series = None, None
    for pin in netlist.nets[supply.net]:
        comp = netlist.components[pin.ref]
        if comp.prefix != "C":
            continue
        other = next((p for n, p in comp.pins.items() if n != pin.pin), None)
        if other is None:
            continue
        if _is_ground_net(other.net):
            shunt = shunt or (comp, pin)
        elif not netlist.is_unconnected(other.net):
            series = series or (comp, pin)
    chosen = shunt or series
    if chosen is None:
        return Found(DecouplingBoard(cap_f=None, supply_v=supply_v), refs=[ic_ref])
    comp, cap_pin = chosen
    try:
        cap_f = float(parse_value(comp.value))
    except (CatalogError, ValueError, ArithmeticError):
        return Found(None, reason=f"{comp.ref}'s value {comp.value!r} isn't a capacitance")
    board = DecouplingBoard(cap_f=cap_f, supply_v=supply_v, cap_in_series=shunt is None)
    if pcb and shunt is not None:
        path = _pcb_path(Path(circuit_json), (comp.ref, cap_pin.pin), (ic_ref, supply.pin))
        if path is not None:
            board.path_mm, board.path_estimated = path
    return Found(board, refs=sorted({comp.ref, ic_ref}))


def i2c_board(netlist, *, ic_ref: str, line: str, supply_v: float) -> Found:
    ic = netlist.components.get(ic_ref)
    if ic is None:
        return Found(None, reason=f"{ic_ref} isn't on this board")
    pin = next((p for p in ic.pins.values() if p.function.upper() == line.upper()), None)
    if pin is None:
        return Found(None, reason=f"{ic_ref} has no {line} pin")
    if netlist.is_unconnected(pin.net) or len(netlist.nets.get(pin.net, [])) < 2:
        return Found(None, reason=f"{ic_ref}.{line} (pin {pin.pin}) is on no bus, so there's no line to simulate")
    for other_pin in netlist.nets[pin.net]:
        comp = netlist.components[other_pin.ref]
        if comp.prefix != "R":
            continue
        far = next((p for n, p in comp.pins.items() if n != other_pin.pin), None)
        if far is None or _is_ground_net(far.net) or netlist.is_unconnected(far.net):
            continue
        try:
            ohms = float(parse_value(comp.value))
        except (CatalogError, ValueError, ArithmeticError):
            return Found(None, reason=f"{comp.ref}'s value {comp.value!r} isn't a resistance")
        return Found(I2cBoard(pullup_ohm=ohms, supply_v=supply_v), refs=sorted({comp.ref, ic_ref}))
    return Found(I2cBoard(pullup_ohm=None, supply_v=supply_v), refs=[ic_ref])


def _pcb_path(circuit: Path, a: tuple[str, str], b: tuple[str, str]) -> tuple[float, bool] | None:
    elements = json.loads(circuit.read_text(encoding="utf-8"))
    names = {e["source_component_id"]: e["name"] for e in elements if e["type"] == "source_component"}
    port_of = {(names.get(e["source_component_id"]), str(e["pin_number"])): e["source_port_id"]
               for e in elements if e["type"] == "source_port" and "pin_number" in e}
    xy = {e["source_port_id"]: (e["x"], e["y"]) for e in elements if e["type"] == "pcb_port" and "x" in e}
    pa, pb = port_of.get(a), port_of.get(b)
    if pa not in xy or pb not in xy:
        return None
    joined = {e["source_trace_id"] for e in elements if e["type"] == "source_trace"
              and set(e.get("connected_source_port_ids", [])) == {pa, pb}}
    for trace in (e for e in elements if e["type"] == "pcb_trace" and e.get("source_trace_id") in joined):
        points = [(p["x"], p["y"]) for p in trace.get("route", []) if "x" in p]
        if len(points) >= 2:
            return sum(math.dist(points[i], points[i + 1]) for i in range(len(points) - 1)), False
    return math.dist(xy[pa], xy[pb]), True


def _is_ground_net(net: str) -> bool:
    return bool(_GROUND.match(net or ""))


def _is_ground_name(name: str) -> bool:
    return bool(_GROUND.match(name or ""))


def _pin_order(pin) -> tuple:
    return (not pin.pin.isdigit(), int(pin.pin) if pin.pin.isdigit() else 0, pin.pin)
