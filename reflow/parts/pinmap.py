"""Pin maps from trusted sources.  OWNER: AGENT (task V-11, DECISIONS V-1, V-2).

Contract
--------
    from_st_pin_data(mpn, st_dir=None) -> PinMap
    from_kicad_symbol(lib_id, symbols_dir=None) -> PinMap
    compare_pin_maps(a, b) -> list[str]
    import_pin_map(mpn, *, st_dir=None, kicad_lib_id=None, symbols_dir=None) -> PinImport

A PinMap is one IC's pins (`contracts.CardPin`: number, name, kind) plus the
`contracts.Citation` it came from. The verifier relabels a design's pins from
it by physical pin number (V-12, HUMAN); the design's own labels never feed it.

Sources, in V-2's order (a signed PartCard override is V-12's job):
1. Vendor pin data. ST's STM32_open_pin_data: `<st_dir>/mcu/<RefName>.xml`,
   where a RefName like "STM32F103C(8-B)Tx" matches STM32F103C8T6 and
   STM32F103CBT6 ("(8-B)" lists alternatives, "x" is any one character, a
   trailing "TR" for tape and reel is allowed).
2. A KiCad symbol, named by its library id ("MCU_ST_STM32F1:STM32F103C8Tx").
   Symbols that `extends` another take the base symbol's pins.

`import_pin_map` uses the vendor map when there is one and checks it against
the KiCad symbol when both exist. Disagreements are returned as text for a
person to settle from the datasheet; the vendor map is still the result.

Kinds (`contracts.PIN_KINDS`): power and ground pins are told apart by name
(GND*, VSS*, AGND, DGND, PGND are ground), because both sources type them the
same. Every kind decided from a name instead of the source's own type is
recorded in `PinMap.notes`. Names lose KiCad markup (`V_{DD}` -> `VDD`).
`compare_pin_maps` compares `base_name`: ST appends the default alternate
function ("PC14-OSC32_IN"), KiCad doesn't ("PC14").

Directories come from the arguments, else REFLOW_ST_PIN_DATA and
REFLOW_KICAD_SYMBOL_DIR, else (KiCad only) the library installed next to
kicad-cli.

Must never
----------
- read a pin name or kind from TSX, circuit.json, or model text,
- download anything, or edit a source file,
- correct a source silently (a wrong datasheet link is reported as written),
- pick one of two disagreeing sources without returning the disagreement.
"""
from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from reflow.contracts import CardPin, Citation
from reflow.netlist import parse_sexpr

ST_DOC = "STMicroelectronics STM32_open_pin_data"
ST_URL = "https://github.com/STMicroelectronics/STM32_open_pin_data"

_GROUND_EXACT = {"AGND", "DGND", "PGND"}
_THERMAL_NAMES = {"EP", "EPAD", "PAD", "TAB"}
_KICAD_KINDS = {
    "input": "input",
    "output": "output",
    "power_out": "output",
    "bidirectional": "io",
    "tri_state": "io",
    "open_collector": "open_drain_out",
    "open_emitter": "open_drain_out",
    "no_connect": "nc",
}
_KICAD_UNTYPED = {"passive", "free", "unspecified"}
_ST_KINDS = {"I/O": "io", "MonoIO": "io", "Reset": "input", "Boot": "input"}
_MARKUP = re.compile(r"[~_^]\{|\}")


class PinMapError(ValueError):
    """A source is missing, malformed, or ambiguous for this part."""


class PinMapNotFound(PinMapError):
    """The source has no entry for this part."""


@dataclass
class PinMap:
    part: str                   # what was asked for: an MPN or a KiCad library id
    package: str                # "LQFP48", or the KiCad Footprint property
    pins: list[CardPin]         # sorted by pin number
    source: Citation
    notes: list[str] = field(default_factory=list)


@dataclass
class PinImport:
    pin_map: PinMap
    checked_against: Citation | None    # the second source, when there was one
    disagreements: list[str]            # empty when the sources agree


def base_name(name: str) -> str:
    """Name used to compare sources: before the first '-', upper case."""
    return name.split("-", 1)[0].strip().upper()


def import_pin_map(mpn: str, *, st_dir=None, kicad_lib_id: str | None = None,
                   symbols_dir=None) -> PinImport:
    vendor = None
    st_root = _dir_arg(st_dir, "REFLOW_ST_PIN_DATA")
    if st_root is not None:
        try:
            vendor = from_st_pin_data(mpn, st_dir=st_root)
        except PinMapNotFound:
            vendor = None
    kicad = from_kicad_symbol(kicad_lib_id, symbols_dir=symbols_dir) if kicad_lib_id else None
    if vendor is None and kicad is None:
        raise PinMapError(f"no trusted pin map for {mpn}: no vendor pin data and no KiCad symbol given")
    if vendor is None:
        return PinImport(pin_map=kicad, checked_against=None, disagreements=[])
    if kicad is None:
        return PinImport(pin_map=vendor, checked_against=None, disagreements=[])
    return PinImport(pin_map=vendor, checked_against=kicad.source,
                     disagreements=compare_pin_maps(vendor, kicad))


def compare_pin_maps(a: PinMap, b: PinMap) -> list[str]:
    left, right = {p.number: p for p in a.pins}, {p.number: p for p in b.pins}
    found = []
    for number in sorted(set(left) | set(right), key=_pin_order):
        x, y = left.get(number), right.get(number)
        if x is None or y is None:
            have, lack = (a, b) if y is None else (b, a)
            pin = x or y
            found.append(f"pin {number}: {have.source.doc} has {pin.name}, {lack.source.doc} has no pin {number}")
        elif base_name(x.name) != base_name(y.name) or x.kind != y.kind:
            found.append(f"pin {number}: {a.source.doc} says {x.name} ({x.kind}), "
                         f"{b.source.doc} says {y.name} ({y.kind})")
    return found


# ---------------------------------------------------------------------------
# ST STM32_open_pin_data
# ---------------------------------------------------------------------------

def from_st_pin_data(mpn: str, st_dir=None) -> PinMap:
    root_dir = _dir_arg(st_dir, "REFLOW_ST_PIN_DATA")
    if root_dir is None:
        raise PinMapError("no ST pin data directory (pass st_dir or set REFLOW_ST_PIN_DATA)")
    mcu_dir = root_dir / "mcu"
    if not mcu_dir.is_dir():
        raise PinMapError(f"{mcu_dir} is not a directory")
    matches = [path for path in sorted(mcu_dir.glob("*.xml")) if _ref_name_matches(path.stem, mpn)]
    if not matches:
        raise PinMapNotFound(f"no ST pin data file matches {mpn}")
    if len(matches) > 1:
        raise PinMapError(f"more than one ST pin data file matches {mpn}: {[p.name for p in matches]}")
    path = matches[0]
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise PinMapError(f"{path.name}: {exc}") from exc
    namespace = root.tag[1:].split("}", 1)[0] if root.tag.startswith("{") else ""
    tag = f"{{{namespace}}}Pin" if namespace else "Pin"
    pins: dict[str, CardPin] = {}
    notes: list[str] = []
    for element in root.findall(tag):
        number, name, st_type = (element.get(key) for key in ("Position", "Name", "Type"))
        if not number or not name or not st_type:
            raise PinMapError(f"{path.name}: a Pin is missing Position, Name or Type")
        if number in pins:
            raise PinMapError(f"{path.name}: two pins at position {number}")
        if st_type == "Power":
            kind = "ground" if _is_ground(name) else "power"
        elif st_type in _ST_KINDS:
            kind = _ST_KINDS[st_type]
        else:
            raise PinMapError(f"{path.name}: pin {number} {name} has unknown Type {st_type}")
        pins[number] = CardPin(number=number, name=name, kind=kind)
    if not pins:
        raise PinMapError(f"{path.name}: no pins")
    return PinMap(
        part=mpn,
        package=root.get("Package", ""),
        pins=[pins[n] for n in sorted(pins, key=_pin_order)],
        source=Citation(doc=ST_DOC, locator=f"mcu/{path.name}", url=ST_URL),
        notes=notes,
    )


def _ref_name_matches(ref_name: str, mpn: str) -> bool:
    pattern = ""
    for token in re.findall(r"\([^)]*\)|.", ref_name):
        if token.startswith("("):
            pattern += "(?:" + "|".join(re.escape(alt) for alt in token[1:-1].split("-")) + ")"
        elif token == "x":
            pattern += "."
        else:
            pattern += re.escape(token.upper())
    return re.fullmatch(pattern + "(?:TR)?", mpn.strip().upper()) is not None


# ---------------------------------------------------------------------------
# KiCad symbol libraries
# ---------------------------------------------------------------------------

def from_kicad_symbol(lib_id: str, symbols_dir=None) -> PinMap:
    if lib_id.count(":") != 1:
        raise PinMapError(f"KiCad library id must be 'Library:Symbol', got {lib_id!r}")
    lib, name = lib_id.split(":")
    path = _kicad_dir(symbols_dir) / f"{lib}.kicad_sym"
    symbols = _kicad_symbols(path)
    if name not in symbols:
        raise PinMapNotFound(f"{lib}.kicad_sym has no symbol {name}")
    chain = _extends_chain(symbols, name)
    raw = _kicad_pins(chain[-1], lib_id)
    pins, notes = [], []
    for number in sorted(raw, key=_pin_order):
        pin_name, etype = raw[number]
        kind, note = _kicad_kind(pin_name, etype)
        if note:
            notes.append(f"pin {number} {pin_name}: KiCad type {etype}, {note}")
        pins.append(CardPin(number=number, name=pin_name, kind=kind))
    return PinMap(
        part=lib_id,
        package=_property(chain, "Footprint"),
        pins=pins,
        source=Citation(doc=f"KiCad symbol library {lib}", locator=lib_id, url=_property(chain, "Datasheet")),
        notes=notes,
    )


def _kicad_dir(symbols_dir) -> Path:
    chosen = _dir_arg(symbols_dir, "REFLOW_KICAD_SYMBOL_DIR")
    if chosen is not None:
        return chosen
    from reflow.cli import find_kicad_cli
    cli = find_kicad_cli()
    if cli is not None:
        base = Path(cli).resolve().parent.parent
        for candidate in (base / "SharedSupport" / "symbols", base / "share" / "kicad" / "symbols"):
            if candidate.is_dir():
                return candidate
    raise PinMapError("KiCad symbol library not found (pass symbols_dir or set REFLOW_KICAD_SYMBOL_DIR)")


def _kicad_symbols(path: Path) -> dict[str, list]:
    try:
        root = parse_sexpr(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise PinMapNotFound(f"{path}: {exc.strerror or exc}") from exc
    except IndexError as exc:
        raise PinMapError(f"{path}: unbalanced s-expression") from exc
    if not isinstance(root, list) or not root or root[0] != "kicad_symbol_lib":
        raise PinMapError(f"{path}: not a kicad_symbol_lib")
    return {node[1]: node for node in root[1:] if isinstance(node, list) and node[:1] == ["symbol"]}


def _extends_chain(symbols: dict[str, list], name: str) -> list[list]:
    chain, seen = [], set()
    while True:
        if name in seen:
            raise PinMapError(f"symbol {name} extends itself")
        seen.add(name)
        node = symbols.get(name)
        if node is None:
            raise PinMapError(f"symbol extends missing base {name}")
        chain.append(node)
        parent = _child_value(node, "extends")
        if not parent:
            return chain
        name = parent


def _kicad_pins(node: list, lib_id: str) -> dict[str, tuple[str, str]]:
    pins: dict[str, tuple[str, str]] = {}

    def walk(symbol: list) -> None:
        for child in symbol[2:]:
            if not isinstance(child, list) or not child:
                continue
            if child[0] == "symbol":
                walk(child)
            elif child[0] == "pin":
                number = _child_value(child, "number")
                entry = (_clean(_child_value(child, "name")), child[1] if len(child) > 1 else "")
                if not number:
                    raise PinMapError(f"{lib_id}: a pin has no number")
                if pins.setdefault(number, entry) != entry:
                    raise PinMapError(f"{lib_id}: pin {number} is both {pins[number]} and {entry}")

    walk(node)
    if not pins:
        raise PinMapError(f"{lib_id}: no pins")
    return pins


def _kicad_kind(name: str, etype: str) -> tuple[str, str]:
    if etype == "power_in":
        return ("ground" if _is_ground(name) else "power"), ""
    if etype in _KICAD_KINDS:
        return _KICAD_KINDS[etype], ""
    if etype in _KICAD_UNTYPED:
        if _is_ground(name):
            return "ground", "kind ground from its name"
        if name.upper() in _THERMAL_NAMES:
            return "thermal_pad", "kind thermal_pad from its name"
        return "io", "no electrical type, listed as io"
    raise PinMapError(f"pin {name}: unknown KiCad electrical type {etype}")


def _property(chain: list[list], key: str) -> str:
    for node in chain:
        for child in node[2:]:
            if isinstance(child, list) and child[:2] == ["property", key] and len(child) > 2:
                value = child[2]
                return "" if value == "~" else value
    return ""


def _child_value(node: list, key: str) -> str:
    for child in node[1:]:
        if isinstance(child, list) and child and child[0] == key and len(child) > 1:
            return child[1]
    return ""


# ---------------------------------------------------------------------------
# shared
# ---------------------------------------------------------------------------

def _clean(name: str) -> str:
    return "" if name.strip() == "~" else _MARKUP.sub("", name).strip()


def _is_ground(name: str) -> bool:
    upper = base_name(name)
    return upper.startswith(("GND", "VSS")) or upper in _GROUND_EXACT


def _pin_order(number: str) -> tuple[int, int, str]:
    return (0, int(number), "") if number.isdigit() else (1, 0, number)


def _dir_arg(value, env: str) -> Path | None:
    if value is not None:
        return Path(value)
    text = os.environ.get(env, "").strip()
    return Path(text) if text else None
