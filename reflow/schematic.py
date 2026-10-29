"""Our own KiCad schematic from circuit.json.  OWNER: AGENT (task O-04).

Contract
--------
    symbols_from_rules(rules_toml) -> {ref: "Lib:Symbol"}        # the [[part]] symbols
    write_schematic(circuit_json, out_dir, *, symbols, project=None) -> Path   # out_dir/board.kicad_sch
    check_schematic(sch, circuit_json, kicad_pcb) -> dict
    schematic_report(run_dir) -> dict                            # run_dir/schematic/, for export
    SchematicError                                               # a part this can't draw honestly

tscircuit's .kicad_sch export fails KiCad ERC on every eval board: wire ends
sit off the 1.27 mm grid, short of their pins, and symbols name libraries that
don't exist. `reflow check` on it is wrong both ways. This writes the same
netlist (circuit.json, which the verifier and the PCB use) as a schematic a
person can open in KiCad:

- Real KiCad library symbols, embedded as KiCad embeds them (a symbol that
  `extends` another is flattened): resistor Device:R, capacitor Device:C,
  pin header Connector_Generic:Conn_01xNN, and each chip from `symbols`
  (rules.toml [[part]] symbol = ...). Symbol pin n is the board's pin n, so
  the schematic and the PCB agree pad for pad.
- Parts in rows on the 1.27 mm grid. Each connected pin gets a 2.54 mm wire
  stub and a net label with the circuit.json net name; a pin the board leaves
  open gets a no-connect flag. No wire joins two parts, so none can miss a pin.
- A PWR_FLAG on each net that has a power-input pin and nothing driving it
  (a rail fed from a connector), as KiCad's ERC expects.

Refused (SchematicError) rather than drawn wrong: a chip with no KiCad symbol;
a board pin the symbol lacks, or a symbol pin the board lacks; an LED or diode
(tscircuit puts the anode on pad 1, KiCad's symbols put the cathode on pin 1);
any other part kind.

`check_schematic` is the bar a shipped schematic has to meet (the human's,
2026-10-29): KiCad ERC with 0 errors and 0 warnings, `reflow check` on it with
0 errors, and its nets the same as circuit.json's and the PCB's pads (as sets
of pins, every net with two or more). `problems` lists each miss; [] passes.

Must never
----------
- draw a pin on a net circuit.json doesn't put it on,
- swap pin numbers to make a symbol fit,
- call a schematic clean without the ERC, the check and the net comparison.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import uuid
from functools import lru_cache
from pathlib import Path

GRID = 1.27
STUB = 2.54
FORMAT_VERSION = "20250114"         # KiCad 9's schematic format; KiCad 10 reads it
ROW_WIDTH = 250.0
PWR_FLAG = "power:PWR_FLAG"
POLARIZED = {"simple_led", "simple_diode"}


class SchematicError(Exception):
    pass


# --- s-expressions that keep their quoting ----------------------------------

class Q(str):
    """A quoted string in an s-expression."""


_TOKEN = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+')


def _parse(text: str):
    stack = [[]]
    for tok in _TOKEN.findall(text):
        if tok == "(":
            stack.append([])
        elif tok == ")":
            done = stack.pop()
            stack[-1].append(done)
        elif tok.startswith('"'):
            stack[-1].append(Q(tok[1:-1].replace('\\"', '"').replace("\\\\", "\\")))
        else:
            stack[-1].append(tok)
    return stack[0][0]


def _dump(node, depth: int = 0) -> str:
    if isinstance(node, Q):
        return '"' + node.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if not isinstance(node, list):
        return str(node)
    flat = [_dump(child, depth + 1) for child in node]
    if not any(isinstance(child, list) for child in node[1:]) or len(" ".join(flat)) < 90:
        return "(" + " ".join(flat) + ")"
    head = [flat[0]] + [f for child, f in zip(node[1:], flat[1:]) if not isinstance(child, list)]
    tail = ["\n" + "\t" * (depth + 1) + f for child, f in zip(node[1:], flat[1:]) if isinstance(child, list)]
    return "(" + " ".join(head) + "".join(tail) + "\n" + "\t" * depth + ")"


def _kids(node, key):
    return [c for c in node[1:] if isinstance(c, list) and c and c[0] == key]


def _kid(node, key):
    found = _kids(node, key)
    return found[0] if found else None


# --- KiCad symbol library -----------------------------------------------------

@lru_cache(maxsize=None)
def _library(lib: str) -> dict:
    from reflow.parts.pinmap import _kicad_dir

    path = _kicad_dir(None) / f"{lib}.kicad_sym"
    if not path.is_file():
        raise SchematicError(f"KiCad symbol library {lib} not found ({path})")
    root = _parse(path.read_text(encoding="utf-8"))
    return {node[1]: node for node in _kids(root, "symbol")}


@lru_cache(maxsize=None)
def _flat_symbol(lib_id: str) -> list:
    """The symbol as a schematic embeds it: `extends` resolved, named "Lib:Name"."""
    lib, _, name = lib_id.partition(":")
    symbols = _library(lib)
    if name not in symbols:
        raise SchematicError(f"{lib_id} isn't in KiCad's {lib} library")
    chain, seen = [], set()
    current = name
    while True:
        if current in seen or current not in symbols:
            raise SchematicError(f"{lib_id}: broken extends chain at {current}")
        seen.add(current)
        chain.append(symbols[current])
        parent = _kid(symbols[current], "extends")
        if parent is None:
            break
        current = parent[1]
    root = chain[-1]
    props: dict[str, list] = {}
    for node in reversed(chain):
        for prop in _kids(node, "property"):
            props[prop[1]] = prop
    flat = ["symbol", Q(lib_id)]
    for child in root[2:]:
        if not isinstance(child, list) or child[0] in ("property", "extends"):
            continue
        if child[0] == "symbol":
            child = ["symbol", Q(name + child[1][len(root[1]):])] + child[2:]
        flat.append(child)
    at = next(i for i, c in enumerate(flat) if isinstance(c, list) and c[0] == "symbol")
    return flat[:at] + list(props.values()) + flat[at:]


def _pins(symbol: list) -> dict[str, dict]:
    pins = {}
    for unit in _kids(symbol, "symbol"):
        for pin in _kids(unit, "pin"):
            at = _kid(pin, "at")
            number = _kid(pin, "number")[1]
            pins[number] = {"type": pin[1], "x": float(at[1]), "y": float(at[2]),
                            "angle": int(float(at[3])) if len(at) > 3 else 0}
    return pins


def _extent(symbol: list) -> tuple[float, float, float, float]:
    xs, ys = [], []

    def walk(node):
        for child in node[1:]:
            if not isinstance(child, list):
                continue
            if child[0] in ("xy", "start", "end", "at") and child[0] != "at" or (child[0] == "at" and node[0] == "pin"):
                xs.append(float(child[1]))
                ys.append(-float(child[2]))
            if child[0] != "property":
                walk(child)
    walk(symbol)
    return (min(xs, default=0), min(ys, default=0), max(xs, default=0), max(ys, default=0))


# --- the board ------------------------------------------------------------------

def symbols_from_rules(rules_toml) -> dict[str, str]:
    from reflow.project_rules import load_rules

    return {part.ref: part.symbol for part in load_rules(rules_toml).part if part.symbol}


def _board(circuit_json: Path) -> tuple[dict, dict]:
    from reflow.circuit_netlist import load_circuit_json

    netlist = load_circuit_json(circuit_json)
    elements = json.loads(Path(circuit_json).read_text(encoding="utf-8"))
    raw = {e["name"]: e for e in elements if e.get("type") == "source_component"}
    return netlist, raw


def _lib_id(ref: str, raw: dict, pins: list[str], symbols: dict[str, str]) -> str:
    kind = raw.get("ftype", "")
    if ref in symbols:
        return symbols[ref]
    if kind == "simple_resistor":
        return "Device:R"
    if kind == "simple_capacitor":
        if raw.get("is_polarized") or raw.get("polarized"):
            raise SchematicError(f"{ref} is a polarized capacitor; no symbol mapping for its pins yet")
        return "Device:C"
    if kind == "simple_pin_header":
        if raw.get("double_row") or raw.get("doubleRow"):
            raise SchematicError(f"{ref} is a two-row header; no symbol mapping for it yet")
        return f"Connector_Generic:Conn_01x{len(pins):02d}"
    if kind in POLARIZED:
        raise SchematicError(
            f"{ref}: tscircuit puts the anode on pad 1, but KiCad's LED and diode symbols put the cathode on "
            "pin 1, so the schematic and the PCB would disagree on polarity. Check the part's cathode pad "
            "(expected.toml TO CHECK) before this board gets a schematic")
    if kind == "simple_chip":
        raise SchematicError(f"{ref} has no KiCad symbol; give it a [[part]] with symbol = \"Lib:Name\" in rules.toml")
    raise SchematicError(f"{ref} is a {kind or 'part'} this can't draw yet")


def _value(ref: str, raw: dict, lib_id: str) -> str:
    for key, item in raw.items():
        if key.startswith("display_") and isinstance(item, str) and item:
            return item
    return raw.get("manufacturer_part_number") or lib_id.partition(":")[2]


def write_schematic(circuit_json, out_dir, *, symbols: dict[str, str], project=None) -> Path:
    netlist, raw = _board(Path(circuit_json))
    order = sorted(netlist.components, key=lambda r: ({"U": 0, "J": 1}.get(re.match(r"[A-Za-z]*", r)[0], 2), _natural(r)))
    parts = []
    for ref in order:
        component = netlist.components[ref]
        board_pins = sorted(component.pins, key=_natural)
        lib_id = _lib_id(ref, raw.get(ref, {}), board_pins, symbols)
        symbol = _flat_symbol(lib_id)
        pins = _pins(symbol)
        for n in board_pins:
            if n not in pins:
                raise SchematicError(f"{ref} pin {n} is on the board, but {lib_id} has no pin {n}")
        for n in pins:
            if n not in component.pins:
                raise SchematicError(f"{lib_id} pin {n} isn't on the board's {ref}")
        nets = {n: component.pins[n].net for n in board_pins}
        parts.append({"ref": ref, "lib_id": lib_id, "symbol": symbol, "pins": pins, "nets": nets,
                      "value": _value(ref, raw.get(ref, {}), lib_id)})

    multi = {name for name, pins in netlist.nets.items() if len(pins) >= 2}
    driven = {}
    for part in parts:
        for n, net in part["nets"].items():
            kind = part["pins"][n]["type"]
            if net in multi:
                driven.setdefault(net, set()).add(kind)
    flags = sorted(net for net, kinds in driven.items() if "power_in" in kinds and "power_out" not in kinds)
    flag = _flat_symbol(PWR_FLAG)
    for i, net in enumerate(flags, start=1):
        parts.append({"ref": f"#FLG{i:02d}", "lib_id": PWR_FLAG, "symbol": flag, "pins": _pins(flag),
                      "nets": {"1": net}, "value": "PWR_FLAG"})

    root = _uuid("root", str(circuit_json))
    items, x, y, row_height = [], 25.4, 25.4, 0.0
    for part in parts:
        x0, y0, x1, y1 = _extent(part["symbol"])
        label = max((len(net) for net in part["nets"].values()), default=0) * 1.0 + STUB + 2 * GRID
        width, height = (x1 - x0) + 2 * label, (y1 - y0) + 2 * label
        if x + width > ROW_WIDTH and x > 25.4:
            x, y, row_height = 25.4, y + row_height + 2 * STUB, 0.0
        ox, oy = _snap(x + label - x0), _snap(y + label - y0)
        items += _place(part, ox, oy, root, multi)
        x += width + 2 * STUB
        row_height = max(row_height, height)

    lib_symbols = ["lib_symbols"] + [_flat_symbol(lib) for lib in sorted({p["lib_id"] for p in parts})]
    sheet = (["kicad_sch", ["version", FORMAT_VERSION], ["generator", Q("reflow")], ["generator_version", Q("1.0")],
              ["uuid", Q(root)], ["paper", Q("A4")], lib_symbols] + items
             + [["sheet_instances", ["path", Q("/"), ["page", Q("1")]]], ["embedded_fonts", "no"]])
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "board.kicad_sch"
    path.write_text(_dump(sheet) + "\n", encoding="utf-8")
    if project is not None:
        shutil.copyfile(project, out / "board.kicad_pro")
    return path


def _place(part: dict, ox: float, oy: float, root: str, multi: set[str]) -> list:
    ref, items = part["ref"], []
    instance = ["symbol", ["lib_id", Q(part["lib_id"])], ["at", _n(ox), _n(oy), "0"], ["unit", "1"],
                ["exclude_from_sim", "no"], ["in_bom", "no" if ref.startswith("#") else "yes"],
                ["on_board", "no" if ref.startswith("#") else "yes"], ["dnp", "no"], ["uuid", Q(_uuid(root, ref))]]
    for prop in _kids(part["symbol"], "property"):
        at = _kid(prop, "at")
        value = {"Reference": ref, "Value": part["value"]}.get(prop[1], prop[2])
        placed = ["property", Q(prop[1]), Q(value),
                  ["at", _n(ox + float(at[1])), _n(oy - float(at[2])), at[3] if len(at) > 3 else "0"]]
        placed += [c for c in prop[3:] if isinstance(c, list) and c[0] != "at"]
        instance.append(placed)
    for n in sorted(part["pins"], key=_natural):
        instance.append(["pin", Q(n), ["uuid", Q(_uuid(root, f"{ref}.{n}"))]])
    instance.append(["instances", ["project", Q("board"),
                                   ["path", Q("/" + root), ["reference", Q(ref)], ["unit", "1"]]]])
    items.append(instance)
    for n, net in sorted(part["nets"].items(), key=lambda kv: _natural(kv[0])):
        pin = part["pins"][n]
        px, py = _snap(ox + pin["x"]), _snap(oy - pin["y"])
        if net not in multi:
            items.append(["no_connect", ["at", _n(px), _n(py)], ["uuid", Q(_uuid(root, f"nc {ref}.{n}"))]])
            continue
        dx, dy = {0: (-1, 0), 90: (0, 1), 180: (1, 0), 270: (0, -1)}[pin["angle"] % 360]
        ex, ey = _snap(px + dx * STUB), _snap(py + dy * STUB)
        items.append(["wire", ["pts", ["xy", _n(px), _n(py)], ["xy", _n(ex), _n(ey)]],
                      ["stroke", ["width", "0"], ["type", "default"]], ["uuid", Q(_uuid(root, f"wire {ref}.{n}"))]])
        angle = {(-1, 0): "180", (1, 0): "0", (0, -1): "90", (0, 1): "270"}[(dx, dy)]
        justify = ["justify", "right", "bottom"] if angle in ("180", "270") else ["justify", "left", "bottom"]
        items.append(["label", Q(net), ["at", _n(ex), _n(ey), angle], ["fields_autoplaced", "yes"],
                      ["effects", ["font", ["size", "1.27", "1.27"]], justify],
                      ["uuid", Q(_uuid(root, f"label {ref}.{n}"))]])
    return items


def _snap(v: float) -> float:
    return round(v / GRID) * GRID


def _n(v: float) -> str:
    text = f"{v:.4f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def _uuid(*parts: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "reflow-schematic/" + "/".join(parts)))


def _natural(text: str):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", text)]


# --- the bar ---------------------------------------------------------------------

def check_schematic(sch, circuit_json, kicad_pcb) -> dict:
    from reflow.circuit_netlist import load_circuit_json
    from reflow.cli import export_netlist, find_kicad_cli, sort_violations
    from reflow.netlist import load_netlist
    from reflow.pcb_nets import load_pcb_pad_nets
    from reflow.rules import run_all

    sch = Path(sch)
    cli = find_kicad_cli()
    if cli is None:
        raise RuntimeError("kicad-cli not found, so the schematic can't be checked")
    report = sch.parent / f"{sch.stem}-erc.json"
    proc = subprocess.run([cli, "sch", "erc", "--format", "json", "--severity-all", "-o", str(report), str(sch)],
                          capture_output=True, text=True, timeout=300, stdin=subprocess.DEVNULL)
    if not report.is_file():
        raise RuntimeError(f"kicad-cli sch erc wrote no report: {(proc.stderr or proc.stdout).strip()[-300:]}")
    found = [v for sheet in json.loads(report.read_text(encoding="utf-8")).get("sheets", [])
             for v in sheet.get("violations", [])]
    erc = {"errors": sum(v["severity"] == "error" for v in found),
           "warnings": sum(v["severity"] == "warning" for v in found),
           "items": [f"{v['severity']} {v['type']}: " + "; ".join(i["description"] for i in v.get("items", []))
                     for v in found]}

    with tempfile.TemporaryDirectory(prefix="reflow-sch-") as tmp:
        netlist = load_netlist(export_netlist(cli, sch, Path(tmp) / "board.net"))
    violations = sort_violations(run_all(netlist))
    check = {"errors": sum(v.severity == "error" for v in violations),
             "warnings": sum(v.severity != "error" for v in violations),
             "violations": [f"{v.severity} {v.rule_id}: {v.message}" for v in violations]}

    board = {name: {(p.ref, p.pin) for p in pins} for name, pins in load_circuit_json(circuit_json).nets.items()}
    drawn = {name: {(p.ref, p.pin) for p in pins if not p.ref.startswith("#")} for name, pins in netlist.nets.items()}
    pads: dict[str, set] = {}
    for key, net in load_pcb_pad_nets(kicad_pcb).items():
        if net:
            pads.setdefault(net, set()).add(key)
    want = _partition(board)
    differences = [f"circuit.json net {name} {sorted(pins)} isn't one net in the schematic"
                   for name, pins in sorted(board.items()) if len(pins) >= 2 and frozenset(pins) not in _partition(drawn)]
    differences += [f"schematic net {name} {sorted(pins)} isn't a circuit.json net"
                    for name, pins in sorted(drawn.items()) if len(pins) >= 2 and frozenset(pins) not in want]
    pcb_ok = _partition(pads) == want
    if not pcb_ok:
        differences += [f"PCB net {name} {sorted(pins)} isn't a circuit.json net"
                        for name, pins in sorted(pads.items()) if len(pins) >= 2 and frozenset(pins) not in want]
    nets = {"circuit_json": _partition(drawn) == want, "pcb": pcb_ok, "differences": differences}

    problems = []
    if erc["errors"] or erc["warnings"]:
        kinds = sorted({v["type"] for v in found})
        problems.append(f"KiCad ERC on the schematic: {erc['errors']} errors, {erc['warnings']} warnings ({', '.join(kinds)})")
    if check["errors"]:
        problems.append(f"reflow check on the schematic: {check['errors']} errors "
                        f"({', '.join(sorted({v.rule_id for v in violations if v.severity == 'error'}))})")
    if not nets["circuit_json"]:
        problems.append("the schematic's nets differ from circuit.json")
    if not nets["pcb"]:
        problems.append("the PCB's pad nets differ from circuit.json")
    return {"path": str(sch), "erc": erc, "check": check, "nets": nets, "problems": problems}


def _partition(nets: dict[str, set]) -> set[frozenset]:
    return {frozenset(pins) for pins in nets.values() if len(pins) >= 2}


def schematic_report(run_dir) -> dict:
    """Write and check the best attempt's schematic in run_dir/schematic/; the result is also schematic.json."""
    from reflow.contracts import RunResult, Spec, from_dict

    run_dir = Path(run_dir)
    run = from_dict(RunResult, json.loads((run_dir / "run.json").read_text(encoding="utf-8")))
    spec = from_dict(Spec, json.loads((run_dir / "spec.json").read_text(encoding="utf-8")))
    build = run_dir / "attempts" / f"{run.best_attempt:02d}" / "build"
    workdir = run_dir / "schematic"
    if workdir.exists():
        shutil.rmtree(workdir)
    rules = _rules_path(run_dir, spec.rules_file)
    try:
        symbols = symbols_from_rules(rules) if rules else {}
        sch = write_schematic(build / "circuit.json", workdir, symbols=symbols, project=build / "board.kicad_pro")
        result = check_schematic(sch, build / "circuit.json", build / "board.kicad_pcb")
    except SchematicError as exc:
        workdir.mkdir(parents=True, exist_ok=True)
        result = {"path": "", "erc": None, "check": None, "nets": None, "problems": [str(exc)]}
    (workdir / "schematic.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


def _rules_path(run_dir: Path, rules_file: str) -> Path | None:
    if not rules_file:
        return None
    path = Path(rules_file)
    for candidate in (path, run_dir / path):
        if candidate.is_file():
            return candidate
    raise SchematicError(f"the spec's rules_file {rules_file} isn't there, so the chips' KiCad symbols are unknown")
