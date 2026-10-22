"""Bind IC pins to trusted pin maps.  Task V-12, written by the agent under O-1b; the human reviews it.

Contract
--------
    PinBinder(pin_map_for)(netlist, parts, spec, part_numbers) -> BindResult
    binder_for_spec(spec, *, st_dir=None, symbols_dir=None) -> PinBinder

The design's own pin labels decide which physical pin each trace reaches, so a
wrong label wires a net to the wrong pin while every rule, reading the same
labels, sees a correct board (the first real run: an MCP9808 with its VDD on
GND). Binding replaces the labels with the truth before the rules run.

For every IC (reference prefix U):

1. Identify it: one of the part numbers it carries in circuit.json
   (`part_numbers`, an LCSC id first, else the MPN) must be a row of
   ResolvedParts. Otherwise `pinout.unidentified`.
2. Find its pin map: `pin_map_for(ref, resolved_part)` returns a
   `reflow.parts.pinmap.PinMap`, or None (or raises PinMapError) when there is
   none: `pinout.no_pin_map`. V-1: no trusted pin map is a verify error.
3. For each of its pins, by physical number: a label that is neither the map's
   name (compared with `base_name`) nor generic ("pin3") is `pinout.mismatch`,
   as is a pin number the package doesn't have. Then the pin takes the map's
   name, and a KiCad-style type from the map's kind (power and ground pins
   become `power_in`, so the decoupling rules can run).

All three are errors, and they come back to the model as fix hints.
Components other than U are left as they are.

`binder_for_spec` looks a chip's pin map up in this order: the spec's rules
file `[[part]]` symbol (by reference, else by MPN prefix; V-2a), then vendor
pin data for the resolved MPN (`import_pin_map`).

Must never
----------
- take a pin name or kind from the design, or keep a design label that disagrees,
- treat a part number the design carries as resolved without a ResolvedParts row,
- pass an IC it could not check.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from reflow.contracts import ResolvedPart, ResolvedParts, Spec
from reflow.netlist import Netlist
from reflow.parts.pinmap import PinMap, PinMapError, base_name, from_kicad_symbol, import_pin_map
from reflow.violation import Violation

_PINTYPE = {
    "power": "power_in",
    "ground": "power_in",
    "input": "input",
    "output": "output",
    "io": "bidirectional",
    "open_drain_out": "open_collector",
    "nc": "no_connect",
    "thermal_pad": "passive",
    "address": "input",
    "i2c_sda": "bidirectional",
    "i2c_scl": "input",
}
_GENERIC = re.compile(r"pin\d+", re.IGNORECASE)


@dataclass
class BindResult:
    netlist: Netlist
    violations: list[Violation]


class PinBinder:
    def __init__(self, pin_map_for: Callable[[str, ResolvedPart], PinMap | None]) -> None:
        self.pin_map_for = pin_map_for

    def __call__(self, netlist: Netlist, parts: ResolvedParts, spec: Spec, part_numbers: dict) -> BindResult:
        violations: list[Violation] = []
        for ref in sorted(netlist.components):
            component = netlist.components[ref]
            if component.prefix != "U":
                continue
            carried = part_numbers.get(ref) or {"mpn": "", "lcsc": []}
            row = _resolved_row(carried, parts)
            if row is None:
                violations.append(_unidentified(ref, carried, component))
                continue
            try:
                pin_map = self.pin_map_for(ref, row)
                reason = ""
            except PinMapError as exc:
                pin_map, reason = None, str(exc)
            if pin_map is None:
                violations.append(_no_pin_map(ref, row, reason))
                continue
            violations.extend(_relabel(ref, component, pin_map))
        return BindResult(netlist=netlist, violations=violations)


def binder_for_spec(spec: Spec, *, st_dir=None, symbols_dir=None) -> PinBinder:
    from reflow.project_rules import load_rules

    rule_parts = load_rules(spec.rules_file).part if spec.rules_file.strip() else []
    cache: dict[tuple[str, str], PinMap | None] = {}

    def pin_map_for(ref: str, row: ResolvedPart) -> PinMap | None:
        key = (ref, row.mpn)
        if key not in cache:
            entry = next((p for p in rule_parts if p.ref == ref), None) or next(
                (p for p in rule_parts if row.mpn.casefold().startswith(p.mpn.casefold())), None)
            if entry is not None and entry.symbol.strip():
                cache[key] = from_kicad_symbol(entry.symbol.strip(), symbols_dir=symbols_dir)
            else:
                cache[key] = import_pin_map(row.mpn, st_dir=st_dir).pin_map
        return cache[key]

    return PinBinder(pin_map_for)


def _resolved_row(carried: dict, parts: ResolvedParts) -> ResolvedPart | None:
    ids = {i.casefold() for i in carried.get("lcsc", [])}
    for row in parts.resolved:
        if row.lcsc.casefold() in ids:
            return row
    mpn = (carried.get("mpn") or "").casefold()
    if mpn:
        for row in parts.resolved:
            if row.mpn.casefold() == mpn:
                return row
    return None


def _relabel(ref: str, component, pin_map: PinMap) -> list[Violation]:
    truth = {p.number: p for p in pin_map.pins}
    where = f"{pin_map.source.doc} {pin_map.source.locator}"
    found = []
    for number in sorted(component.pins, key=lambda n: (not n.isdigit(), int(n) if n.isdigit() else 0, n)):
        pin = component.pins[number]
        label = pin.function
        known = truth.get(number)
        if known is None:
            found.append(Violation(
                "pinout.mismatch", "error",
                f"{ref} pin {number} is labelled {label}, but {where} has no pin {number}",
                "A pin number the package doesn't have can't be placed on the footprint, so its trace goes nowhere.",
                f"Remove pin{number} from {ref}'s pinLabels and route that net to the pin the pin map names for it.",
                [ref], [pin.net],
            ))
            continue
        if label and not _GENERIC.fullmatch(label) and base_name(label) != base_name(known.name):
            found.append(Violation(
                "pinout.mismatch", "error",
                f"{ref} pin {number} is labelled {label}, but {where} says pin {number} is {known.name}",
                (f"The labels in the design decide which physical pin each trace reaches. With this label, "
                 f"{pin.net} lands on {known.name}, not on {label}."),
                (f'Set {ref} pinLabels pin{number}: "{known.name}" and re-route the traces you meant for '
                 f"{label} to the pin the pin map gives {label}."),
                [ref], [pin.net],
            ))
        pin.function = known.name
        pin.pintype = _PINTYPE.get(known.kind, "passive")
    return found


def _unidentified(ref: str, carried: dict, component) -> Violation:
    shown = ", ".join(filter(None, [carried.get("mpn", ""), *carried.get("lcsc", [])]))
    nets = sorted({p.net for p in component.pins.values()})[:3]
    if shown:
        message = f"{ref} carries {shown}, which is not in the resolved parts table, so its pins can't be checked"
    else:
        message = f"{ref} carries no part number from the resolved parts table, so its pins can't be checked"
    return Violation(
        "pinout.unidentified", "error", message,
        "Without knowing which part a chip is, its pins can't be compared with a pin map, so wrong wiring would pass.",
        f"Give {ref} the manufacturerPartNumber and the jlcpcb supplierPartNumbers from its row in the resolved-parts table.",
        [ref], nets,
    )


def _no_pin_map(ref: str, row: ResolvedPart, reason: str) -> Violation:
    detail = f" ({reason})" if reason else ""
    return Violation(
        "pinout.no_pin_map", "error",
        f"{ref} is {row.mpn} ({row.lcsc}), and no trusted pin map was found for it{detail}",
        "Without a pin map, the chip's pins can't be checked, so a wrong pinout would pass.",
        f"Add a [[part]] for {ref} with symbol = \"Library:Symbol\" to the project's rules.toml.",
        [ref], [],
    )
