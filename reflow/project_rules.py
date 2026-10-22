"""A project's rules.toml: parse and check it.  OWNER: AGENT (task V-21, DECISIONS V-2).

Contract
--------
    load_rules(path) -> contracts.ProjectRules
    check_rules(rules, pin_maps) -> RulesCheck
    pin_maps_from_parts(rules) -> (pin_maps, warnings)
    render_rules(rules, plan) -> str
    rules_prompt_block(spec, plan) -> str

`load_rules` parses the TOML strictly with `from_dict(ProjectRules, ...)`: a
missing `why` or `source`, or an unknown key, raises RulesFileError.

`check_rules` reports, without raising:

- errors: `on` not written REF.PIN; `need` not in RULE_NEEDS; `to` missing
  where the need connects to a net (cap, pullup, pulldown, tie) or present
  where it doesn't (open, connected); a `value` that doesn't parse, or a range
  "low..high" whose low is above its high; a blank `why` or `source`; a pin
  that isn't on its part's pin map (matched by number or by `base_name`).
- warnings: a part with no pin map given (its pin names weren't checked), and
  every power, ground, reset or boot pin no rule mentions. Reset and boot pins
  are recognised by name (NRST, RESET, RST, MCLR, BOOT*), because neither pin
  source types them.

`pin_maps` maps a reference ("U1") to a `reflow.parts.pinmap.PinMap`.
`pin_maps_from_parts` builds them from the file's `[[part]]` table (V-2a): a
`symbol` gives the KiCad symbol, otherwise `mpn` is looked up in vendor pin
data; a part with neither gets a warning. When a `[[part]]` table exists, a
rule whose reference isn't in it is a warning too.

`render_rules` is what the codegen and fix prompts get (V-22): one line per
`[[part]]` ("U1 is the MCP9808 (plan part p1). Give it reference U1.") and
one per rule ("U1.VDD: capacitor to GND, 100nF..1uF"), never `why` or
`source`. `rules_prompt_block` reads `spec.rules_file` ("none" when empty; a
missing or invalid file raises).

Must never
----------
- send `why` or `source` anywhere (they are for people),
- read a pin name or kind from a design,
- change the rules file.
"""
from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from reflow.contracts import RULE_NEEDS, ContractError, ProjectRules, from_dict
from reflow.parts.catalog import CatalogError, parse_value
from reflow.parts.pinmap import PinMap, base_name

_ON = re.compile(r"([A-Za-z]+\d+)\.(\S+)")
_NEEDS_A_NET = {"cap", "pullup", "pulldown", "tie"}
_RESET_BOOT = ("NRST", "RESET", "RST", "MCLR", "BOOT")
_WORDING = {
    "cap": "capacitor to {to}",
    "pullup": "pull-up resistor to {to}",
    "pulldown": "pull-down resistor to {to}",
    "tie": "wire directly to {to}",
    "open": "leave unconnected",
    "connected": "must be connected",
}


class RulesFileError(ValueError):
    """The rules file can't be read as ProjectRules."""


@dataclass
class RulesCheck:
    rules: int
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def load_rules(path) -> ProjectRules:
    file = Path(path)
    try:
        data = tomllib.loads(file.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RulesFileError(f"{file}: {exc.strerror or exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise RulesFileError(f"{file}: not valid TOML ({exc})") from exc
    try:
        return from_dict(ProjectRules, data)
    except ContractError as exc:
        raise RulesFileError(f"{file}: {exc}") from exc


def check_rules(rules: ProjectRules, pin_maps: dict[str, PinMap]) -> RulesCheck:
    result = RulesCheck(rules=len(rules.rule))
    covered: set[tuple[str, str]] = set()
    unmapped: set[str] = set()
    for index, rule in enumerate(rules.rule, 1):
        label = f"rule {index} ({rule.on})"
        result.errors.extend(f"{label}: {problem}" for problem in _field_problems(rule))
        match = _ON.fullmatch(rule.on.strip())
        if match is None:
            continue
        ref, pin_text = match.groups()
        pin_map = pin_maps.get(ref)
        if pin_map is None:
            unmapped.add(ref)
            continue
        pin = _find_pin(pin_map, pin_text)
        if pin is None:
            result.errors.append(
                f"{label}: {ref}.{pin_text} is not a pin of {pin_map.source.locator} ({pin_map.source.doc})"
            )
        else:
            covered.add((ref, pin.number))
    for ref in sorted(unmapped):
        result.warnings.append(f"{ref}: no pin map given, so its pin names were not checked")
    named = {part.ref for part in rules.part}
    if named:
        refs = {m.group(1) for r in rules.rule if (m := _ON.fullmatch(r.on.strip()))}
        for ref in sorted(refs - named):
            result.warnings.append(f"{ref} is used by a rule but not listed in [[part]], so codegen won't know which part it is")
    for ref in sorted(pin_maps):
        for pin in pin_maps[ref].pins:
            role = _role(pin)
            if role and (ref, pin.number) not in covered:
                result.warnings.append(f"{ref}.{pin.name} (pin {pin.number}) is a {role} pin and no rule mentions it")
    return result


def _field_problems(rule) -> list[str]:
    problems = []
    if _ON.fullmatch(rule.on.strip()) is None:
        problems.append(f"on {rule.on!r} must be REF.PIN, like U1.VDD")
    if rule.need not in RULE_NEEDS:
        problems.append(f"need {rule.need!r} is not one of {', '.join(sorted(RULE_NEEDS))}")
    elif rule.need in _NEEDS_A_NET and not rule.to.strip():
        problems.append(f"to: a {rule.need} rule needs the net on the other side, like GND")
    elif rule.need not in _NEEDS_A_NET and rule.to.strip():
        problems.append(f"to: a {rule.need} rule takes no net")
    if rule.value.strip():
        problems.extend(_value_problems(rule.value))
    if not rule.why.strip():
        problems.append("why is blank: say in your own words why the datasheet asks for this")
    if not rule.source.strip():
        problems.append("source is blank: name the document, section and page")
    return problems


def _value_problems(text: str) -> list[str]:
    pieces = [piece.strip() for piece in text.split("..")]
    if len(pieces) > 2 or not all(pieces):
        return [f"value {text!r} must be one value or a range low..high"]
    try:
        numbers = [parse_value(piece) for piece in pieces]
    except CatalogError:
        return [f"value {text!r} is not a value like 100nF or 4.7k"]
    if len(numbers) == 2 and numbers[0] > numbers[1]:
        return [f"value {text!r}: the low end is above the high end"]
    return []


def _find_pin(pin_map: PinMap, text: str):
    for pin in pin_map.pins:
        if pin.number == text:
            return pin
    wanted = base_name(text)
    for pin in pin_map.pins:
        if base_name(pin.name) == wanted:
            return pin
    return None


def _role(pin) -> str:
    if pin.kind in ("power", "ground"):
        return pin.kind
    name = base_name(pin.name)
    if name.startswith(_RESET_BOOT):
        return "boot" if name.startswith("BOOT") else "reset"
    return ""


def pin_maps_from_parts(rules: ProjectRules) -> tuple[dict[str, PinMap], list[str]]:
    """Pin maps for the [[part]] table. A symbol that can't be read raises PinMapError."""
    from reflow.parts.pinmap import PinMapError, from_kicad_symbol, import_pin_map

    maps, warnings = {}, []
    for part in rules.part:
        if part.symbol.strip():
            maps[part.ref] = from_kicad_symbol(part.symbol.strip())
            continue
        try:
            maps[part.ref] = import_pin_map(part.mpn).pin_map
        except PinMapError as exc:
            warnings.append(f"{part.ref}: no pin map for {part.mpn} ({exc}); add symbol = \"Library:Symbol\"")
    return maps, warnings


def render_rules(rules: ProjectRules, plan) -> str:
    lines = []
    for part in rules.part:
        match = next((p for p in (plan.parts if plan else []) if p.mpn and p.mpn == part.mpn), None)
        where = f" (plan part {match.id})" if match else ""
        lines.append(f"{part.ref} is the {part.mpn}{where}. Give it reference {part.ref}.")
    for rule in rules.rule:
        wording = _WORDING.get(rule.need, rule.need).format(to=rule.to.strip())
        value = f", {rule.value.strip()}" if rule.value.strip() else ""
        lines.append(f"{rule.on.strip()}: {wording}{value}")
    return "\n".join(lines)


def rules_prompt_block(spec, plan) -> str:
    if not spec.rules_file.strip():
        return "none"
    return render_rules(load_rules(spec.rules_file), plan)
