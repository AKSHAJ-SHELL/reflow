"""V-12: bind IC pins to trusted pin maps by physical number (DECISIONS V-1, V-2, O-1b).

The main input is the first real board (tests/data/real_runs/mcp9808_nemotron_20261022/):
a free model wrote MCP9808 pinLabels with pins 3, 7 and 8 wrong, wired the real
VDD (pin 8) to GND, and the unbound verifier passed it. Pin maps come from the
test pin data in tests/data/pinmaps/.
"""
import json
from pathlib import Path

import pytest

from reflow.circuit_netlist import load_circuit_json, part_numbers
from reflow.contracts import ProjectRules, RulePart, ResolvedPart, ResolvedParts, Spec, from_dict
from reflow.netlist import Component, Netlist, Pin
from reflow.parts.pinmap import from_kicad_symbol
from reflow.pinbind import BindResult, PinBinder, binder_for_spec
from reflow.verifier import verify_circuit_json

ROOT = Path(__file__).resolve().parents[1]
REAL = ROOT / "tests" / "data" / "real_runs" / "mcp9808_nemotron_20261022"
KICAD = ROOT / "tests" / "data" / "pinmaps" / "kicad"
ST = ROOT / "tests" / "data" / "pinmaps" / "st"
RULES = ROOT / "docs" / "proposals" / "examples" / "rules.toml"


def _parts() -> ResolvedParts:
    return from_dict(ResolvedParts, json.loads((REAL / "parts.json").read_text(encoding="utf-8")))


def _spec(**changes) -> Spec:
    data = json.loads((ROOT / "evals" / "mcp9808_breakout" / "spec.json").read_text(encoding="utf-8"))
    data.update(changes)
    return from_dict(Spec, data)


def _mcp9808_binder() -> PinBinder:
    pin_map = from_kicad_symbol("Sensor_Temperature:MCP9808_MSOP", symbols_dir=KICAD)
    return PinBinder(lambda ref, part: pin_map if part.mpn.startswith("MCP9808") else None)


def _bind(circuit: Path, binder=None) -> BindResult:
    binder = binder or _mcp9808_binder()
    return binder(load_circuit_json(circuit), _parts(), _spec(), part_numbers(circuit))


# ---------------------------------------------------------------------------
# reading the part numbers the design carries
# ---------------------------------------------------------------------------

def test_part_numbers_come_from_circuit_json():
    ids = part_numbers(REAL / "circuit.json")
    assert ids["U1"] == {"mpn": "MCP9808T-E/MS", "lcsc": ["C129490"]}
    assert ids["J1"]["lcsc"] == ["C32713270"]


# ---------------------------------------------------------------------------
# the real board
# ---------------------------------------------------------------------------

def test_the_real_boards_wrong_pinout_is_reported_pin_by_pin():
    result = _bind(REAL / "circuit.json")
    found = {v.message.split(" is labelled")[0]: v for v in result.violations}
    assert {v.rule_id for v in result.violations} == {"pinout.mismatch"}
    assert sorted(found) == ["U1 pin 3", "U1 pin 7", "U1 pin 8"]
    pin8 = found["U1 pin 8"]
    assert pin8.severity == "error" and "A0" in pin8.message and "VDD" in pin8.message
    assert "MCP9808_MSOP" in pin8.message
    assert "pin8" in pin8.fix_hint and '"VDD"' in pin8.fix_hint
    assert pin8.refs == ["U1"] and pin8.nets == ["GND"] and pin8.why.strip()


def test_pins_are_relabelled_and_typed_from_the_pin_map():
    pins = _bind(REAL / "circuit.json").netlist.components["U1"].pins
    assert (pins["8"].name, pins["8"].pintype, pins["8"].net) == ("VDD", "power_in", "GND")
    assert (pins["7"].name, pins["7"].net) == ("A0", "V3_3")
    assert pins["4"].pintype == "power_in"            # GND
    assert pins["1"].pintype == "bidirectional"       # SDA


def test_the_verifier_now_fails_the_real_board():
    report = verify_circuit_json(REAL / "circuit.json", _parts(), _spec(), bind=_mcp9808_binder())
    assert report.errors >= 3
    assert [v.rule_id for v in report.violations].count("pinout.mismatch") == 3


def test_the_corrected_board_binds_clean():
    result = _bind(REAL / "corrected.circuit.json")
    assert result.violations == []
    report = verify_circuit_json(REAL / "corrected.circuit.json", _parts(), _spec(), bind=_mcp9808_binder())
    assert (report.errors, report.violations) == (0, [])


def test_bound_power_pins_let_the_decoupling_rule_run():
    report = verify_circuit_json(REAL / "corrected_no_cap.circuit.json", _parts(), _spec(), bind=_mcp9808_binder())
    assert [v.rule_id for v in report.violations] == ["decoupling.missing"]


def test_passives_are_left_alone():
    before = load_circuit_json(REAL / "circuit.json").components["R1"].pins
    after = _bind(REAL / "circuit.json").netlist.components["R1"].pins
    assert [(p.pin, p.name, p.pintype) for p in after.values()] == [(p.pin, p.name, p.pintype) for p in before.values()]


# ---------------------------------------------------------------------------
# chips that can't be checked are errors, not passes (V-1: no trusted pin map -> verify error)
# ---------------------------------------------------------------------------

def test_a_chip_without_a_part_number_is_an_error():
    circuit = ROOT / "tests" / "data" / "circuit_json" / "sensor_good.circuit.json"
    result = _mcp9808_binder()(load_circuit_json(circuit), _parts(), _spec(), part_numbers(circuit))
    (v,) = result.violations
    assert (v.rule_id, v.refs, v.severity) == ("pinout.unidentified", ["U1"], "error")


def test_a_chip_whose_part_number_isnt_resolved_is_an_error():
    parts = ResolvedParts(resolved=[p for p in _parts().resolved if p.lcsc != "C129490"], unresolved=[])
    circuit = REAL / "circuit.json"
    result = _mcp9808_binder()(load_circuit_json(circuit), parts, _spec(), part_numbers(circuit))
    assert [v.rule_id for v in result.violations] == ["pinout.unidentified"]
    assert "C129490" in result.violations[0].message


def test_a_chip_with_no_pin_map_is_an_error():
    circuit = REAL / "circuit.json"
    result = PinBinder(lambda ref, part: None)(load_circuit_json(circuit), _parts(), _spec(), part_numbers(circuit))
    (v,) = result.violations
    assert v.rule_id == "pinout.no_pin_map" and "MCP9808T-E/MS" in v.message


def _chip(labels: dict[str, str]) -> Netlist:
    comp = Component(ref="U1", value="", footprint="", lib="tscircuit", part="simple_chip")
    nets: dict[str, list[Pin]] = {}
    for number, label in labels.items():
        pin = Pin(ref="U1", pin=number, net=f"N{number}", pintype="", function=label)
        comp.pins[number] = pin
        nets[pin.net] = [pin]
    return Netlist(components={"U1": comp}, nets=nets)


def _stm32_parts() -> ResolvedParts:
    return ResolvedParts(resolved=[ResolvedPart(
        request_id="p1", lcsc="C8734", mpn="STM32F103C8T6", manufacturer="ST", package="LQFP-48", value="",
        stock=10, basic=False, unit_price_usd=1.0, source="jlcparts", fetched_at="2026-10-21T00:00:00Z")], unresolved=[])


def test_generic_labels_are_relabelled_without_a_mismatch():
    binder = PinBinder(lambda ref, part: from_kicad_symbol("Sensor_Temperature:MCP9808_MSOP", symbols_dir=KICAD))
    result = binder(_chip({"1": "pin1", "8": "VDD"}), _parts(), _spec(), {"U1": {"mpn": "MCP9808T-E/MS", "lcsc": ["C129490"]}})
    assert result.violations == []
    assert result.netlist.components["U1"].pins["1"].name == "SDA"


def test_a_pin_number_the_package_doesnt_have_is_an_error():
    binder = PinBinder(lambda ref, part: from_kicad_symbol("Sensor_Temperature:MCP9808_MSOP", symbols_dir=KICAD))
    result = binder(_chip({"9": "EP"}), _parts(), _spec(), {"U1": {"mpn": "MCP9808T-E/MS", "lcsc": ["C129490"]}})
    assert [v.rule_id for v in result.violations] == ["pinout.mismatch"]
    assert "pin 9" in result.violations[0].message


# ---------------------------------------------------------------------------
# where pin maps come from
# ---------------------------------------------------------------------------

def test_binder_for_spec_uses_the_rules_part_symbol(tmp_path, monkeypatch):
    monkeypatch.setenv("REFLOW_KICAD_SYMBOL_DIR", str(KICAD))
    rules = tmp_path / "rules.toml"
    rules.write_text(RULES.read_text(encoding="utf-8").replace('mpn    = "MCP9808"', 'mpn    = "MCP9808"'), encoding="utf-8")
    binder = binder_for_spec(_spec(rules_file=str(rules)))
    circuit = REAL / "circuit.json"
    result = binder(load_circuit_json(circuit), _parts(), _spec(), part_numbers(circuit))
    assert [v.rule_id for v in result.violations].count("pinout.mismatch") == 3


def test_binder_for_spec_falls_back_to_vendor_pin_data(monkeypatch):
    monkeypatch.setenv("REFLOW_ST_PIN_DATA", str(ST))
    binder = binder_for_spec(_spec(rules_file=""))
    result = binder(_chip({"24": "VDD", "23": "VSS", "44": "PB8"}), _stm32_parts(), _spec(),
                    {"U1": {"mpn": "STM32F103C8T6", "lcsc": ["C8734"]}})
    assert [(v.rule_id, "pin 44" in v.message) for v in result.violations] == [("pinout.mismatch", True)]
    assert result.netlist.components["U1"].pins["24"].pintype == "power_in"


def test_binder_for_spec_without_any_source_reports_no_pin_map(monkeypatch):
    monkeypatch.delenv("REFLOW_ST_PIN_DATA", raising=False)
    circuit = REAL / "circuit.json"
    result = binder_for_spec(_spec(rules_file=""))(load_circuit_json(circuit), _parts(), _spec(), part_numbers(circuit))
    assert [v.rule_id for v in result.violations] == ["pinout.no_pin_map"]
