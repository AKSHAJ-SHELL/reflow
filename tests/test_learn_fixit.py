"""L-14: fix-it tools on the AI's failed draft (DECISIONS L-2a).

Edits are checked on the real draft TSX from tests/data/real_runs/learn_mcp9808_20261022
(attempt 1: mirrored MCP9808 labels; U1's SDA, SCL and GND unwired). The end-to-end
test recompiles with real tsci and re-verifies with the real binder and rules, so a
fix only counts when the same checks a run uses say so.
"""
import json
import shutil
from pathlib import Path

import pytest

from reflow.compile import find_tsci
from reflow.contracts import FixEdit, FixResult, from_dict, to_dict
from reflow.learn.fixit import EditError, apply_edits, check_fix

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "tests" / "data" / "real_runs" / "learn_mcp9808_20261022"
DRAFT = (RUN / "attempts" / "01" / "index.circuit.tsx").read_text(encoding="utf-8")
KICAD = ROOT / "tests" / "data" / "pinmaps" / "kicad"
DATASHEET = {"1": "SDA", "2": "SCL", "3": "Alert", "4": "GND", "5": "A2", "6": "A1", "7": "A0", "8": "VDD"}


def E(kind, **kw) -> FixEdit:
    return FixEdit(kind=kind, **kw)


def test_set_label_rewrites_one_pin_of_pinlabels():
    out = apply_edits(DRAFT, [E("set_label", ref="U1", pin="1", value="SDA")])
    assert 'pin1: "SDA", pin2: "GND"' in out
    assert out.count("pinLabels") == 1


def test_add_part_gets_the_next_free_reference_and_two_traces():
    out = apply_edits(DRAFT, [E("add_part", value="4.7k", part="resistor", a="U1.SDA", b="V3_3")])
    assert '<resistor name="R3" resistance="4.7k" footprint="0402" />' in out
    assert '<trace from=".R3 > .pin1" to=".U1 > .SDA" />' in out
    assert '<trace from=".R3 > .pin2" to="net.V3_3" />' in out
    assert out.rstrip().endswith("</board>\n)") or out.rstrip().endswith(")")


def test_add_a_capacitor():
    out = apply_edits(DRAFT, [E("add_part", value="100nF", part="capacitor", a="U1.VDD", b="GND")])
    assert '<capacitor name="C2" capacitance="100nF" footprint="0402" />' in out


def test_set_value_changes_only_that_part():
    out = apply_edits(DRAFT, [E("set_value", ref="R1", value="47k")])
    assert '<resistor name="R1" resistance="47k"' in out and '<resistor name="R2" resistance="4.7k"' in out


def test_connect_and_disconnect():
    out = apply_edits(DRAFT, [E("connect", a="U1.SDA", b="SDA")])
    assert '<trace from=".U1 > .SDA" to="net.SDA" />' in out
    out = apply_edits(out, [E("disconnect", a="U1.SDA")])
    assert ".U1 > .SDA" not in out
    assert '<trace from=".U1 > .A0" to="net.GND" />' in out


def test_delete_removes_the_part_and_its_traces():
    out = apply_edits(DRAFT, [E("delete", ref="R1")])
    assert 'name="R1"' not in out and ".R1 >" not in out
    assert 'name="R2"' in out and ".R2 > .pin1" in out


def test_set_trace_limit_keeps_a_decoupling_cap_close():
    out = apply_edits(DRAFT, [E("set_trace_limit", ref="C1", value="3mm")])
    assert '<capacitor name="C1" capacitance="100nF" footprint="0402"' in out
    assert out.count('maxDecouplingTraceLength="3mm"') == 1
    again = apply_edits(out, [E("set_trace_limit", ref="C1", value="2.5mm")])
    assert 'maxDecouplingTraceLength="2.5mm"' in again and 'maxDecouplingTraceLength="3mm"' not in again
    with pytest.raises(EditError, match="mm"):
        apply_edits(DRAFT, [E("set_trace_limit", ref="C1", value="3")])
    with pytest.raises(EditError, match="capacitor"):
        apply_edits(DRAFT, [E("set_trace_limit", ref="R1", value="3mm")])


def test_edits_never_carry_a_part_number():
    """Rule 5: a part the user adds has no MPN or supplier id."""
    out = apply_edits(DRAFT, [E("add_part", value="4.7k", part="resistor", a="U1.SDA", b="V3_3")])
    added = [line for line in out.splitlines() if 'name="R3"' in line][0]
    assert "PartNumber" not in added and "jlcpcb" not in added


@pytest.mark.parametrize("edit, message", [
    (E("set_value", ref="R9", value="1k"), "R9"),
    (E("set_label", ref="R1", pin="1", value="X"), "pinLabels"),
    (E("add_part", value="1k", part="inductor", a="U1.SDA", b="GND"), "resistor or capacitor"),
    (E("add_part", value="banana", part="resistor", a="U1.SDA", b="GND"), "banana"),
    (E("connect", a="U1.SDA", b='GND" onClick="x'), "net or pin"),
    (E("explode"), "explode"),
])
def test_bad_edits_are_refused(edit, message):
    with pytest.raises(EditError, match=message):
        apply_edits(DRAFT, [edit])


def test_fix_edit_and_result_are_strict_contracts():
    edit = E("connect", a="U1.SDA", b="SDA")
    assert from_dict(FixEdit, json.loads(json.dumps(to_dict(edit)))) == edit


@pytest.mark.skipif(find_tsci() is None, reason="tsci not installed")
def test_relabelling_and_wiring_the_real_draft_verifies_clean(tmp_path, monkeypatch):
    """The user's fix of the AI's real draft, checked by tsci + pin binding + rules."""
    from reflow.learn.engine import load_run

    monkeypatch.setenv("REFLOW_KICAD_SYMBOL_DIR", str(KICAD))
    run_dir = tmp_path / "run"
    shutil.copytree(RUN, run_dir)
    edits = [E("set_label", ref="U1", pin=n, value=label) for n, label in DATASHEET.items()]
    edits += [E("connect", a="U1.SDA", b="SDA"), E("connect", a="U1.SCL", b="SCL"),
              E("connect", a="U1.VDD", b="V3_3"), E("connect", a="U1.GND", b="GND")]
    result = check_fix(load_run(run_dir), base_attempt=1, edits=edits, number=1)
    assert from_dict(FixResult, json.loads(json.dumps(to_dict(result)))) == result
    assert result.compiled, result.compile_errors
    assert result.errors == 0 and not result.refused, [v.message for v in result.violations]
    folder = run_dir / "learn" / "fix" / "01"
    assert (folder / "index.circuit.tsx").is_file() and (folder / "verify.json").is_file()
    assert result.circuit_json.endswith("circuit.json")


@pytest.mark.skipif(find_tsci() is None, reason="tsci not installed")
def test_a_partial_fix_still_reports_what_is_wrong(tmp_path, monkeypatch):
    from reflow.learn.engine import load_run

    monkeypatch.setenv("REFLOW_KICAD_SYMBOL_DIR", str(KICAD))
    run_dir = tmp_path / "run"
    shutil.copytree(RUN, run_dir)
    edits = [E("set_label", ref="U1", pin=n, value=label) for n, label in DATASHEET.items()]
    result = check_fix(load_run(run_dir), base_attempt=1, edits=edits, number=1)
    assert result.compiled
    rules = {v.rule_id for v in result.violations if v.severity == "error"}
    assert "pinout.mismatch" not in rules and rules, rules


@pytest.mark.skipif(find_tsci() is None, reason="tsci not installed")
def test_shorting_two_named_nets_is_refused_not_hidden(tmp_path, monkeypatch):
    from reflow.learn.engine import load_run

    monkeypatch.setenv("REFLOW_KICAD_SYMBOL_DIR", str(KICAD))
    run_dir = tmp_path / "run"
    shutil.copytree(RUN, run_dir)
    result = check_fix(load_run(run_dir), base_attempt=1, edits=[E("connect", a="J1.pin1", b="GND")], number=1)
    assert result.refused and "V3_3" in result.refused and "GND" in result.refused
