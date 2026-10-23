"""L-12: read a testbench's inputs from a real board (DECISIONS L-2a).

The board gives the cap value, the pull-up value, the supply voltage and, on the
PCB, the cap-to-pin distance. A board the testbench can't represent (the chip's
supply pin connected to nothing, an I2C pin on no bus) is refused with a reason,
never simulated with a guess.
"""
from pathlib import Path

import pytest

from reflow.learn.board_values import decoupling_board, i2c_board, supply_volts
from reflow.learn.engine import load_run
from reflow.learn.fixit import bound_netlist

ROOT = Path(__file__).resolve().parents[1]
LEARN = ROOT / "tests" / "data" / "real_runs" / "learn_mcp9808_20261022"
CORRECTED = ROOT / "tests" / "data" / "real_runs" / "mcp9808_nemotron_20261022" / "corrected.circuit.json"
KICAD = ROOT / "tests" / "data" / "pinmaps" / "kicad"


@pytest.fixture(autouse=True)
def _symbols(monkeypatch):
    monkeypatch.setenv("REFLOW_KICAD_SYMBOL_DIR", str(KICAD))


def _netlist(circuit: Path):
    return bound_netlist(load_run(LEARN), circuit)


def test_supply_voltage_comes_from_the_spec():
    assert supply_volts("3.3V from the I2C header") == 3.3
    assert supply_volts("5 V USB") == 5.0
    assert supply_volts("battery") is None


def test_the_corrected_board_has_a_100nf_cap_at_vdd_and_4k7_pull_ups():
    netlist = _netlist(CORRECTED)
    dec = decoupling_board(netlist, CORRECTED, ic_ref="U1", supply_v=3.3)
    assert dec.board.cap_f == pytest.approx(100e-9) and dec.board.cap_in_series is False
    assert dec.refs == ["C1", "U1"]
    i2c = i2c_board(netlist, ic_ref="U1", line="SDA", supply_v=3.3)
    assert i2c.board.pullup_ohm == pytest.approx(4.7e3) and i2c.refs == ["R1", "U1"]


def test_the_pcb_distance_from_the_cap_pad_to_the_pin_is_measured():
    """The learn fixture's final board keeps its pcb_port positions; it isn't routed, so the
    straight-line distance is a labelled lower bound."""
    final = LEARN / "attempts" / "02" / "build" / "circuit.json"
    dec = decoupling_board(_netlist(final), final, ic_ref="U1", supply_v=3.3, pcb=True)
    assert dec.board.path_estimated is True
    assert 0.5 < dec.board.path_mm < 30


def test_a_supply_pin_connected_to_nothing_is_refused():
    """The AI's draft (attempt 1) left the real VDD pin 8 unconnected: no supply, no testbench."""
    draft = LEARN / "attempts" / "01" / "build" / "circuit.json"
    dec = decoupling_board(_netlist(draft), draft, ic_ref="U1", supply_v=3.3)
    assert dec.board is None and "VDD" in dec.reason and "not connected" in dec.reason


def test_an_i2c_pin_on_no_bus_is_refused():
    final = LEARN / "attempts" / "02" / "build" / "circuit.json"
    i2c = i2c_board(_netlist(final), ic_ref="U1", line="SDA", supply_v=3.3)
    assert i2c.board is None and "SDA" in i2c.reason


def test_no_pull_up_on_a_connected_line_is_simulated_as_none(tmp_path):
    import json
    import shutil

    board = tmp_path / "no_pullups.circuit.json"
    elements = json.loads(CORRECTED.read_text(encoding="utf-8"))
    drop = {e["source_component_id"] for e in elements if e["type"] == "source_component" and e["name"] in ("R1", "R2")}
    kept = [e for e in elements if e.get("source_component_id") not in drop]
    board.write_text(json.dumps(kept), encoding="utf-8")
    i2c = i2c_board(_netlist(board), ic_ref="U1", line="SDA", supply_v=3.3)
    assert i2c.board is not None and i2c.board.pullup_ohm is None
