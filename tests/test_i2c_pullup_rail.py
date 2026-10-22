"""An I2C pull-up must go to the chip's supply, not just to any rail (gap found 2026-10-22).

Input: tests/data/real_runs/mcp9808_lightning_pullup_rail_20261022/, attempt 2 of a
real eval run. Its pinout is right, so V-12 binds it clean, but the pull-ups R1/R2
go to V3_3, which nothing else is on, while U1.VDD sits on Net-(C1-pin1) with C1
and the header. i2c.missing_pullup accepts any non-ground net at the resistor's
far end, so the verifier passes a board whose bus is pulled up to nothing.

These tests fix the behaviour, not the rule's name: any `i2c.*` error will do.
The rule is the human's (reflow/rules/). The first test fails until it exists.
"""
import json
from pathlib import Path

from reflow.contracts import ResolvedParts, Spec, from_dict
from reflow.parts.pinmap import from_kicad_symbol
from reflow.pinbind import PinBinder
from reflow.verifier import verify_circuit_json

ROOT = Path(__file__).resolve().parents[1]
REAL = ROOT / "tests" / "data" / "real_runs"
FLOATING = REAL / "mcp9808_lightning_pullup_rail_20261022"
CORRECTED = REAL / "mcp9808_nemotron_20261022" / "corrected.circuit.json"
KICAD = ROOT / "tests" / "data" / "pinmaps" / "kicad"


def _parts(folder: Path) -> ResolvedParts:
    return from_dict(ResolvedParts, json.loads((folder / "parts.json").read_text(encoding="utf-8")))


def _spec() -> Spec:
    return from_dict(Spec, json.loads((ROOT / "evals" / "mcp9808_breakout" / "spec.json").read_text(encoding="utf-8")))


def _binder() -> PinBinder:
    pin_map = from_kicad_symbol("Sensor_Temperature:MCP9808_MSOP", symbols_dir=KICAD)
    return PinBinder(lambda ref, part: pin_map if part.mpn.startswith("MCP9808") else None)


def _verify(circuit: Path, parts_from: Path):
    return verify_circuit_json(circuit, _parts(parts_from), _spec(), bind=_binder())


def test_pullups_to_an_unpowered_rail_fail_verify():
    report = _verify(FLOATING / "circuit.json", FLOATING)
    assert not [v for v in report.violations if v.rule_id.startswith("pinout.")], report.violations
    i2c = [v for v in report.violations if v.rule_id.startswith("i2c.") and v.severity == "error"]
    for line in ("SDA", "SCL"):
        hits = [v for v in i2c if line in v.nets]
        assert hits, f"no i2c error on {line}: its pull-up goes to V3_3, which U1 isn't powered from"
        # The hint goes back to the model, so it must name both the rail and the chip's supply.
        assert "V3_3" in hits[0].fix_hint and "Net-(C1-pin1)" in hits[0].fix_hint, hits[0]
    assert report.errors >= 2


def test_pullups_to_the_chips_supply_stay_clean():
    """The corrected first real board: R1/R2 go to V3_3, and U1.VDD is on V3_3."""
    report = _verify(CORRECTED, REAL / "mcp9808_nemotron_20261022")
    assert [v for v in report.violations if v.rule_id.startswith("i2c.")] == []
    assert report.errors == 0, report.violations
