"""Fix-it tools: edit the AI's failed draft, recompile it and re-verify it.  OWNER: AGENT (task L-14, DECISIONS L-2a).

Contract
--------
    apply_edits(tsx, edits: list[FixEdit]) -> str      # raises EditError
    check_fix(run, *, base_attempt, edits, number) -> FixResult
    bound_netlist(run, circuit_json) -> Netlist         # pins bound to trusted pin maps, as the verifier does

Edits change the draft's TSX text, so the result is a real tscircuit board:

- `add_part`: a resistor or capacitor (`part`, `value`) from `a` to `b`, given
  the next free reference and footprint 0402, and **no part number** (rule 5);
- `set_value`: a resistor's or capacitor's value;
- `connect`: a trace from `a` to `b`;
- `disconnect`: removes every trace that reaches pin `a`;
- `delete`: removes part `ref` and every trace that reaches it;
- `set_label`: sets one entry of a chip's pinLabels (`pin` is the physical
  pin number). Traces name pins by label, so relabelling moves where they land,
  which is exactly how the AI's wrong pinout gets fixed.
- `set_trace_limit`: a decoupling cap's `maxDecouplingTraceLength` ("3mm"),
  which is how far from the pin tscircuit may place and route it. Its default
  of 1 mm makes tscircuit skip routing the whole board (reflow/route.py).

`a` and `b` are a pin (`U1.SDA`, `U1.pin3`) or a net (`V3_3`). Anything that
isn't is refused, so an edit can't inject text into the TSX.

`check_fix` writes the edited TSX to the run's `learn/fix/<number>/`,
compiles it with tsci and verifies it with the same binder and rules as a run.
There's no model call. A board the verifier refuses (two named nets shorted, no
components) comes back with `refused` set, never as clean.

Must never
----------
- add a part number, or call a model,
- report a fix as clean without the verifier's report,
- write outside the run folder's learn/fix/.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from reflow.circuit_netlist import CircuitJsonError, load_circuit_json, part_numbers
from reflow.compile import compile_board
from reflow.contracts import FIX_KINDS, FixEdit, FixResult, ResolvedParts, to_dict
from reflow.parts.catalog import CatalogError, parse_value
from reflow.pinbind import binder_for_spec

_PIN = re.compile(r"^([A-Za-z]+\d+)\.([A-Za-z0-9_+\-]+)$")
_NET = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_LABEL = re.compile(r"^[A-Za-z0-9_+\-#/]+$")
_PARTS = {"resistor": ("R", "resistance"), "capacitor": ("C", "capacitance")}


class EditError(ValueError):
    """An edit that can't be applied to this board."""


def apply_edits(tsx: str, edits: list[FixEdit]) -> str:
    for edit in edits:
        if edit.kind not in FIX_KINDS:
            raise EditError(f"unknown edit {edit.kind!r}; use one of {', '.join(sorted(FIX_KINDS))}")
        tsx = _APPLY[edit.kind](tsx, edit)
    return tsx


def check_fix(run, *, base_attempt: int, edits: list[FixEdit], number: int) -> FixResult:
    from reflow.verifier import VerifierInputError, make_verifier

    base = run.path / "attempts" / f"{base_attempt:02d}" / "index.circuit.tsx"
    if not base.is_file():
        raise EditError(f"attempt {base_attempt} has no index.circuit.tsx to edit")
    tsx = apply_edits(base.read_text(encoding="utf-8"), edits)
    folder = run.path / "learn" / "fix" / f"{number:02d}"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "index.circuit.tsx").write_text(tsx, encoding="utf-8")
    result = FixResult(number=number, base_attempt=base_attempt, edits=list(edits), compiled=False,
                       compile_errors=[], errors=0, warnings=0, violations=[],
                       tsx_path=str(folder / "index.circuit.tsx"))
    compiled = compile_board(tsx, folder / "build")
    (folder / "compile.json").write_text(json.dumps(to_dict(compiled), indent=2) + "\n", encoding="utf-8")
    if not compiled.ok:
        result.compile_errors = [e.message for e in compiled.errors]
        return result
    result.compiled, result.circuit_json = True, compiled.circuit_json
    parts = run.parts or ResolvedParts(resolved=[], unresolved=[])
    try:
        report = make_verifier(bind=binder_for_spec(run.spec))(compiled.circuit_json, parts, run.spec)
    except (CircuitJsonError, VerifierInputError) as exc:
        result.refused = str(exc)
        return result
    (folder / "verify.json").write_text(json.dumps(to_dict(report), indent=2, ensure_ascii=False) + "\n",
                                        encoding="utf-8")
    result.errors, result.warnings, result.violations = report.errors, report.warnings, list(report.violations)
    return result


def bound_netlist(run, circuit_json):
    path = Path(circuit_json)
    parts = run.parts or ResolvedParts(resolved=[], unresolved=[])
    bound = binder_for_spec(run.spec)(load_circuit_json(path), parts, run.spec, part_numbers(path))
    return getattr(bound, "netlist", bound)


# ---------------------------------------------------------------------------
# the edits
# ---------------------------------------------------------------------------

def _add_part(tsx: str, e: FixEdit) -> str:
    if e.part not in _PARTS:
        raise EditError(f"add_part adds a resistor or capacitor, not {e.part!r}")
    prefix, attr = _PARTS[e.part]
    _value(e.value)
    a, b = _endpoint(e.a), _endpoint(e.b)
    taken = {int(m) for m in re.findall(rf'name="{prefix}(\d+)"', tsx)}
    ref = f"{prefix}{next(n for n in range(1, 10_000) if n not in taken)}"
    lines = [f'<{e.part} name="{ref}" {attr}="{e.value.strip()}" footprint="0402" />',
             f'<trace from=".{ref} > .pin1" to="{a}" />',
             f'<trace from=".{ref} > .pin2" to="{b}" />']
    return _insert(tsx, lines)


def _set_value(tsx: str, e: FixEdit) -> str:
    _value(e.value)
    start, end, tag, text = _element(tsx, e.ref)
    if tag not in _PARTS:
        raise EditError(f"{e.ref} is a {tag}; set_value changes a resistor or capacitor")
    attr = _PARTS[tag][1]
    if not re.search(rf'\b{attr}="[^"]*"', text):
        raise EditError(f"{e.ref} has no {attr}")
    new = re.sub(rf'\b{attr}="[^"]*"', f'{attr}="{e.value.strip()}"', text, count=1)
    return tsx[:start] + new + tsx[end:]


def _connect(tsx: str, e: FixEdit) -> str:
    return _insert(tsx, [f'<trace from="{_endpoint(e.a)}" to="{_endpoint(e.b)}" />'])


def _disconnect(tsx: str, e: FixEdit) -> str:
    selector = _endpoint(e.a)
    if not selector.startswith("."):
        raise EditError("disconnect takes a pin, like U1.SDA")
    return _drop_traces(tsx, lambda ends: selector in ends)


def _delete(tsx: str, e: FixEdit) -> str:
    start, end, _, _ = _element(tsx, e.ref)
    tsx = _cut(tsx, start, end)
    return _drop_traces(tsx, lambda ends: any(x.startswith(f".{e.ref} >") for x in ends))


def _set_label(tsx: str, e: FixEdit) -> str:
    if not e.pin.isdigit():
        raise EditError(f"pin must be a physical pin number, got {e.pin!r}")
    if not _LABEL.match(e.value.strip()):
        raise EditError(f"{e.value!r} isn't a pin label")
    start, end, _, text = _element(tsx, e.ref)
    block = re.search(r"pinLabels=\{\{(.*?)\}\}", text, re.S)
    if block is None:
        raise EditError(f"{e.ref} has no pinLabels")
    entries = block.group(1)
    entry = re.compile(rf'(\bpin{e.pin}\s*:\s*)"[^"]*"')
    if entry.search(entries):
        entries = entry.sub(lambda m: f'{m.group(1)}"{e.value.strip()}"', entries, count=1)
    else:
        entries = entries.rstrip().rstrip(",") + f', pin{e.pin}: "{e.value.strip()}" '
    new = text[:block.start(1)] + entries + text[block.end(1):]
    return tsx[:start] + new + tsx[end:]


def _set_trace_limit(tsx: str, e: FixEdit) -> str:
    if not re.fullmatch(r"\d+(?:\.\d+)?mm", e.value.strip()):
        raise EditError(f"{e.value!r} isn't a length in mm, like 3mm")
    start, end, tag, text = _element(tsx, e.ref)
    if tag != "capacitor":
        raise EditError(f"{e.ref} is a {tag}; a trace limit belongs on a decoupling capacitor")
    value = e.value.strip()
    if re.search(r'\bmaxDecouplingTraceLength="[^"]*"', text):
        new = re.sub(r'\bmaxDecouplingTraceLength="[^"]*"', f'maxDecouplingTraceLength="{value}"', text, count=1)
    else:
        new = re.sub(r"\s*/>$", f' maxDecouplingTraceLength="{value}" />', text, count=1)
    return tsx[:start] + new + tsx[end:]


_APPLY = {"add_part": _add_part, "set_trace_limit": _set_trace_limit, "set_value": _set_value, "connect": _connect, "disconnect": _disconnect,
          "delete": _delete, "set_label": _set_label}


# ---------------------------------------------------------------------------
# TSX helpers
# ---------------------------------------------------------------------------

def _endpoint(text: str) -> str:
    text = (text or "").strip()
    pin = _PIN.match(text)
    if pin:
        return f".{pin.group(1)} > .{pin.group(2)}"
    if _NET.match(text):
        return f"net.{text}"
    raise EditError(f"{text!r} isn't a net or pin (a net like V3_3, or a pin like U1.SDA)")


def _value(text: str) -> None:
    try:
        parse_value(text.strip())
    except (CatalogError, ValueError, ArithmeticError) as exc:
        raise EditError(f"{text!r} isn't a value like 4.7k or 100nF") from exc


def _elements(tsx: str):
    """(start, end, tag, text) for every self-closing JSX element."""
    i = 0
    while True:
        i = tsx.find("<", i)
        if i < 0:
            return
        tag = re.match(r"<([a-z][a-zA-Z0-9]*)", tsx[i:])
        if tag is None:
            i += 1
            continue
        j, depth, quote = i + len(tag.group(0)), 0, ""
        while j < len(tsx):
            ch = tsx[j]
            if quote:
                quote = "" if ch == quote else quote
            elif ch in "\"'":
                quote = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            elif ch == ">" and depth == 0:
                break
            j += 1
        if j < len(tsx) and tsx[j - 1] == "/":
            yield i, j + 1, tag.group(1), tsx[i:j + 1]
        i = j + 1


def _element(tsx: str, ref: str):
    for start, end, tag, text in _elements(tsx):
        if tag != "trace" and re.search(rf'\bname="{re.escape(ref)}"', text):
            return start, end, tag, text
    raise EditError(f"there's no part {ref} on this board")


def _drop_traces(tsx: str, matches) -> str:
    spans = []
    for start, end, tag, text in _elements(tsx):
        if tag == "trace":
            ends = re.findall(r'\b(?:from|to)="([^"]*)"', text)
            if matches(ends):
                spans.append((start, end))
    for start, end in reversed(spans):
        tsx = _cut(tsx, start, end)
    return tsx


def _cut(tsx: str, start: int, end: int) -> str:
    line_start = tsx.rfind("\n", 0, start) + 1
    line_end = tsx.find("\n", end)
    if tsx[line_start:start].strip() == "" and (line_end < 0 or tsx[end:line_end].strip() == ""):
        return tsx[:line_start] + tsx[(line_end + 1) if line_end >= 0 else end:]
    return tsx[:start] + tsx[end:]


def _insert(tsx: str, lines: list[str]) -> str:
    close = tsx.rfind("</board>")
    if close < 0:
        raise EditError("the draft has no <board> to add to")
    line_start = tsx.rfind("\n", 0, close) + 1
    indent = re.match(r"\s*", tsx[line_start:close]).group(0) + "  "
    block = "".join(f"{indent}{line}\n" for line in lines)
    return tsx[:line_start] + block + tsx[line_start:]
