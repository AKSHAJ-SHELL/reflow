"""Integration: real tsci, real kicad-cli, real rules, and the real design loop.

Only the model is scripted. Everything a board passes through after the model
(compile_board, circuit.json, the design verifier in reflow/verifier.py) is
the code a live run uses. Skips cleanly when tsci or kicad-cli is missing
(docs/agents/04-testing-rules.md rule 9).

The design verifier needs a pin-binding step (V-12, HUMAN, not built yet).
These tests pass `unbound`, which leaves pins untyped, so the decoupling
rules cannot fire here; the I2C rules work on pin names and do.

`verify_kicad_sch` is the old path through tscircuit's .kicad_sch export. It
is kept only for tests about that export, which loses connectivity (V-1).

TSX inputs live in tests/data/integration/. They are test inputs, not
verifier fixtures: there is no expected.toml here.
"""
import json
import re
import shutil
from pathlib import Path

import pytest

from reflow.cli import export_netlist, find_kicad_cli, sort_violations
from reflow.compile import compile_board, find_tsci
from reflow.contracts import (
    Plan,
    ResolvedPart,
    ResolvedParts,
    RunResult,
    Spec,
    VerifyReport,
    from_dict,
)
from reflow.harness.loop import run_design
from reflow.llm import Completion
from reflow.netlist import load_netlist
from reflow.rules import run_all
from reflow.verifier import make_verifier, verify_circuit_json

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "tests" / "data" / "integration"
EXAMPLES = ROOT / "docs" / "examples"

KICAD_CLI = find_kicad_cli()
pytestmark = [
    pytest.mark.skipif(find_tsci() is None, reason="tsci not installed"),
    pytest.mark.skipif(KICAD_CLI is None, reason="kicad-cli not found"),
]


def _tsx(name: str) -> str:
    return (DATA / name).read_text(encoding="utf-8")


def _compile(tsx: str, workdir: Path):
    result = compile_board(tsx, workdir)
    assert result.ok, f"tsci failed: {result.errors}\n{result.stderr_tail}"
    return result


def _netlist(kicad_sch: str, tmp: Path):
    return load_netlist(export_netlist(KICAD_CLI, Path(kicad_sch), tmp / "board.net"))


def unbound(netlist, parts, spec):
    """Stand-in for V-12's pin binding: returns the netlist unchanged."""
    return netlist


def verify_kicad_sch(kicad_sch: str, parts: ResolvedParts, spec: Spec) -> VerifyReport:
    """The old path through the .kicad_sch export (what `reflow check` does on KiCad files)."""
    sch = Path(kicad_sch)
    nl = _netlist(kicad_sch, sch.parent)
    violations = sort_violations(run_all(nl))
    errors = sum(v.severity == "error" for v in violations)
    return VerifyReport(
        schematic=sch.name,
        components=len(nl.components),
        nets=len(nl.nets),
        errors=errors,
        warnings=len(violations) - errors,
        violations=violations,
    )


def _net_of(nl, ref: str, pin_name: str) -> str:
    for number, pin in nl.components[ref].pins.items():
        if pin.name == pin_name or number == pin_name:
            return pin.net
    raise AssertionError(f"{ref} has no pin {pin_name}: {sorted(nl.components[ref].pins)}")


def _pcb_pad_nets(kicad_pcb: str) -> dict[tuple[str, str], str]:
    """{(ref, pad number): net name} read straight from the exported .kicad_pcb."""
    text = Path(kicad_pcb).read_text(encoding="utf-8")
    pads: dict[tuple[str, str], str] = {}
    for block in re.split(r"\n\s*\(footprint\s", text)[1:]:
        ref = re.search(r'\(property "Reference" "([^"]+)"', block)
        assert ref, "footprint without a Reference property"
        for number, body in re.findall(r'\(pad "([^"]+)"(.*?)\n\s*\)', block, re.S):
            net = re.search(r'\(net \d+ "([^"]*)"\)', body)
            if net:
                pads[(ref.group(1), number)] = net.group(1)
    return pads


# ---------------------------------------------------------------------------
# compile -> export -> verify
# ---------------------------------------------------------------------------

def test_blinky_compiles_and_verifies_clean(tmp_path):
    tsx = (ROOT / "boards" / "blinky" / "index.circuit.tsx").read_text(encoding="utf-8")
    result = _compile(tsx, tmp_path)
    report = verify_circuit_json(result.circuit_json, ResolvedParts([], []), None, bind=unbound)
    assert report.components >= 3
    assert report.errors == 0, report.violations


def test_pcb_export_has_the_traced_nets(tmp_path):
    """Ground truth: the PCB export keeps every trace in sensor_good.tsx."""
    result = _compile(_tsx("sensor_good.tsx"), tmp_path)
    pads = _pcb_pad_nets(result.kicad_pcb)
    # soic8 pin numbers from the pinLabels in sensor_good.tsx
    assert pads[("U1", "1")] == "SDA"
    assert pads[("U1", "2")] == "SCL"
    assert pads[("U1", "4")] == "GND"
    assert pads[("U1", "8")] == "V3_3"
    assert pads[("J1", "3")] == "SDA"
    assert pads[("R1", "1")] == "SDA"


def test_schematic_export_keeps_the_traced_nets(tmp_path):
    """The verifier reads the .kicad_sch, so it must have the same nets as the TSX.

    sensor_good.tsx traces U1.SDA, J1.pin3 and R1.pin1 to net.SDA, and U1.GND
    and C1.pin2 to net.GND. Pins on one traced net must share one KiCad net,
    and a traced pin must not be "unconnected".
    """
    result = _compile(_tsx("sensor_good.tsx"), tmp_path)
    nl = _netlist(result.kicad_sch, tmp_path)
    sda = _net_of(nl, "U1", "SDA")
    assert not nl.is_unconnected(sda), f"U1.SDA exported as {sda}"
    assert _net_of(nl, "J1", "3") == sda
    assert _net_of(nl, "R1", "1") == sda
    gnd = _net_of(nl, "U1", "GND")
    assert _net_of(nl, "C1", "2") == gnd
    assert _net_of(nl, "U1", "A0") == gnd
    assert _net_of(nl, "U1", "VDD") != gnd


def test_good_sensor_verifies_clean(tmp_path):
    result = _compile(_tsx("sensor_good.tsx"), tmp_path)
    report = verify_circuit_json(result.circuit_json, ResolvedParts([], []), None, bind=unbound)
    assert report.errors == 0, report.violations


def test_sensor_without_pullups_is_flagged(tmp_path):
    """The go/no-go board class: an I2C sensor with no pull-ups must fail verify."""
    result = _compile(_tsx("sensor_no_pullups.tsx"), tmp_path)
    report = verify_circuit_json(result.circuit_json, ResolvedParts([], []), None, bind=unbound)
    rule_ids = sorted(v.rule_id for v in report.violations)
    assert rule_ids == ["i2c.missing_pullup", "i2c.missing_pullup"], report.violations


# ---------------------------------------------------------------------------
# the design loop with real compile + verify and a scripted model
# ---------------------------------------------------------------------------

class ScriptedModel:
    """Returns one scripted reply per call and records each prompt."""

    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
        self.prompts: list[str] = []

    def complete(self, system: str, prompt: str, *, max_tokens: int = 4096) -> Completion:
        self.prompts.append(prompt)
        if not self.replies:
            raise AssertionError("model called more times than scripted")
        text = self.replies.pop(0)
        return Completion(text=text, model="scripted/integration", input_tokens=len(prompt) // 4, output_tokens=len(text) // 4)


def _fenced(tsx: str) -> str:
    return "```tsx\n" + tsx + "```\n"


def _spec() -> Spec:
    data = json.loads((EXAMPLES / "spec.json").read_text(encoding="utf-8"))
    data["confirmed"] = True
    return from_dict(Spec, data)


def _plan() -> Plan:
    return from_dict(Plan, json.loads((EXAMPLES / "plan.json").read_text(encoding="utf-8")))


def _resolved(plan: Plan) -> ResolvedParts:
    """One illustrative row per plan part, so the loop's inputs are complete."""
    rows = [
        ResolvedPart(
            request_id=part.id, lcsc=f"C{1000 + index}", mpn=part.mpn or f"TEST-{part.id}",
            manufacturer="test", package=part.package, value=part.value, stock=100,
            basic=True, unit_price_usd=0.01, source="test", fetched_at="2026-10-20T00:00:00Z",
        )
        for index, part in enumerate(plan.parts)
    ]
    return ResolvedParts(resolved=rows, unresolved=[])


def _design(tmp_path: Path, replies: list[str], verifier) -> tuple[RunResult, ScriptedModel]:
    plan = _plan()
    model = ScriptedModel(replies)
    run = run_design(
        _spec(), plan, _resolved(plan),
        model=model, compiler=compile_board, verifier=verifier,
        run_dir=tmp_path / "run", max_attempts=3, compile_cap=2,
    )
    return run, model


def _either_file(path: str, parts: ResolvedParts, spec: Spec) -> VerifyReport:
    """For tests about compiling, not verifying: accept whichever file the loop passes.

    loop.py passes the .kicad_sch until the human applies V-1-loop-HUMAN.patch,
    and circuit.json after.
    """
    if path.endswith(".kicad_sch"):
        return verify_kicad_sch(path, parts, spec)
    return verify_circuit_json(path, parts, spec, bind=unbound)


def test_loop_recovers_from_a_real_tsci_syntax_error(tmp_path):
    """Blinky, so the verify step does not depend on the I2C nets exporting correctly."""
    blinky = (ROOT / "boards" / "blinky" / "index.circuit.tsx").read_text(encoding="utf-8")
    run, model = _design(tmp_path, [
        _fenced(_tsx("blinky_syntax_error.tsx")),
        _fenced(blinky),
    ], verifier=_either_file)
    assert run.status == "passed"
    assert run.best_attempt == 1
    assert [(a.attempt, a.compile_tries, a.compiled) for a in run.attempts] == [(1, 2, True)]

    folder = tmp_path / "run"
    first = json.loads((folder / "attempts" / "01" / "compile-1.json").read_text(encoding="utf-8"))
    assert first["ok"] is False and first["errors"], first
    assert json.loads((folder / "attempts" / "01" / "compile-2.json").read_text(encoding="utf-8"))["ok"] is True
    assert from_dict(RunResult, json.loads((folder / "run.json").read_text(encoding="utf-8"))) == run

    # The fix call carries tsci's first error and the broken file, and nothing from KiCad.
    fix_prompt = model.prompts[1]
    assert first["errors"][0]["message"] in fix_prompt
    assert _tsx("blinky_syntax_error.tsx") in fix_prompt
    assert "(kicad_sch" not in fix_prompt and "(kicad_pcb" not in fix_prompt


def test_loop_fixes_missing_pullups_on_attempt_2(tmp_path):
    """Attempt 1 forgets the pull-ups, the verifier says so, attempt 2 adds them.

    Uses the design verifier, which refuses a .kicad_sch: this goes green once
    loop.py passes circuit.json (V-1-loop-HUMAN.patch).
    """
    run, model = _design(tmp_path, [
        _fenced(_tsx("sensor_no_pullups.tsx")),
        _fenced(_tsx("sensor_good.tsx")),
    ], verifier=make_verifier(bind=unbound))
    assert [a.rule_ids for a in run.attempts] == [["i2c.missing_pullup", "i2c.missing_pullup"], []]
    assert run.status == "passed"
    assert run.best_attempt == 2
    fix_prompt = model.prompts[1]
    assert "rule_id: i2c.missing_pullup" in fix_prompt
    assert "fix_hint: Add a 4.7k resistor" in fix_prompt
