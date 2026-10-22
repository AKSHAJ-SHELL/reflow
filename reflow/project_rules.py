"""A project's rules.toml: parse and check it.  OWNER: AGENT (task V-21, DECISIONS V-2).

Contract
--------
    load_rules(path) -> contracts.ProjectRules
    check_rules(rules, pin_maps) -> RulesCheck

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

`pin_maps` maps a reference ("U1") to a `reflow.parts.pinmap.PinMap`. A rules
file is written before any board exists, so the caller says which part each
reference is (`reflow rules check --symbol U1=Lib:Symbol` / `--mpn U1=MPN`).

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
