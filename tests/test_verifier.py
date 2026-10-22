"""V-16: the design verifier, circuit.json -> VerifyReport (docs/04-contracts.md §5).

Uses the recorded boards in tests/data/circuit_json/. Binding IC pins to a
trusted pin map is V-12 (`reflow.pinbind`, tested in tests/test_pinbind.py), so
every call here passes a `bind` step explicitly. `unbound` returns the netlist
unchanged, which means no pin is typed power and the decoupling rules cannot fire.
"""
import json
from pathlib import Path

import pytest

from reflow.circuit_netlist import MergedNetsError
from reflow.contracts import ResolvedParts, Spec, VerifyReport, from_dict, to_dict
from reflow.verifier import VerifierInputError, make_verifier, verify_circuit_json

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "tests" / "data" / "circuit_json"
PARTS = ResolvedParts(resolved=[], unresolved=[])


def _spec() -> Spec:
    return from_dict(Spec, json.loads((ROOT / "docs" / "examples" / "spec.json").read_text(encoding="utf-8")))


def unbound(netlist, parts, spec, part_numbers):
    return netlist


def test_good_sensor_is_clean():
    report = verify_circuit_json(DATA / "sensor_good.circuit.json", PARTS, _spec(), bind=unbound)
    assert (report.errors, report.warnings, report.violations) == (0, 0, [])
    assert report.schematic == "sensor_good.circuit.json"
    assert (report.components, report.nets) == (5, 5)


def test_missing_pullups_are_errors_in_reflow_checks_order():
    """Same order as `reflow check`: severity, rule id, then the order the rule reports
    (the I2C rule walks U1's pins, so SDA on pin 1 comes before SCL on pin 2)."""
    report = verify_circuit_json(DATA / "sensor_no_pullups.circuit.json", PARTS, _spec(), bind=unbound)
    assert report.errors == 2 and report.warnings == 0
    assert [(v.rule_id, v.nets) for v in report.violations] == [
        ("i2c.missing_pullup", ["SDA"]), ("i2c.missing_pullup", ["SCL"]),
    ]
    again = verify_circuit_json(DATA / "sensor_no_pullups.circuit.json", PARTS, _spec(), bind=unbound)
    assert again == report


def test_report_is_a_strict_verify_report():
    report = verify_circuit_json(DATA / "sensor_no_pullups.circuit.json", PARTS, _spec(), bind=unbound)
    assert from_dict(VerifyReport, json.loads(json.dumps(to_dict(report)))) == report


def test_the_rules_see_the_netlist_bind_returns():
    """A bind step that types U1 pin 8 as power is what lets decoupling.series fire."""
    calls = []

    def power_on_vdd(netlist, parts, spec, part_numbers):
        calls.append((parts, spec.title))
        netlist.components["U1"].pins["8"].pintype = "power_in"
        return netlist

    spec = _spec()
    without = verify_circuit_json(DATA / "sensor_series_cap.circuit.json", PARTS, spec, bind=unbound)
    with_map = verify_circuit_json(DATA / "sensor_series_cap.circuit.json", PARTS, spec, bind=power_on_vdd)
    assert "decoupling.series" not in {v.rule_id for v in without.violations}
    assert [v.rule_id for v in with_map.violations] == ["decoupling.series"]
    assert calls == [(PARTS, spec.title)]


def test_bind_is_required():
    with pytest.raises(TypeError):
        verify_circuit_json(DATA / "sensor_good.circuit.json", PARTS, _spec())


def test_bind_must_return_a_netlist():
    with pytest.raises(VerifierInputError, match="bind"):
        verify_circuit_json(DATA / "sensor_good.circuit.json", PARTS, _spec(), bind=lambda nl, p, s, ids: None)


def test_a_kicad_schematic_is_refused():
    """tscircuit's .kicad_sch loses connectivity (V-1); never verify it on the design path."""
    with pytest.raises(VerifierInputError, match="circuit.json"):
        verify_circuit_json("attempts/01/build/board.kicad_sch", PARTS, _spec(), bind=unbound)


def test_shorted_named_nets_are_not_hidden():
    with pytest.raises(MergedNetsError):
        verify_circuit_json(DATA / "sensor_shorted_rails.circuit.json", PARTS, _spec(), bind=unbound)


def test_make_verifier_has_the_loop_signature():
    verifier = make_verifier(bind=unbound)
    report = verifier(str(DATA / "sensor_no_pullups.circuit.json"), PARTS, _spec())
    assert report.errors == 2


def test_make_verifier_requires_bind():
    with pytest.raises(TypeError):
        make_verifier()
