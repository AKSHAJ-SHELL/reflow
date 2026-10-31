"""O-04: our own KiCad schematic from circuit.json, held to 0 ERC errors and 0 warnings, then `reflow check`.

tscircuit's own .kicad_sch export fails KiCad ERC on every eval board (wire
ends off the grid, short of their pins; invented symbol libraries), and
`reflow check` on it is wrong both ways (PROGRESS 2026-10-29). The boards
here are real Sonnet eval runs (tests/data/schematic/README.md).
"""
import json
import re
import shutil
from pathlib import Path

import pytest

from reflow.circuit_netlist import load_circuit_json
from reflow.cli import find_kicad_cli
from reflow.schematic import SchematicError, check_schematic, symbols_from_rules, write_schematic

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "tests" / "data" / "schematic"
CLEAN = ["mcp9808", "pcf8574", "at24c02"]
pytestmark = pytest.mark.skipif(find_kicad_cli() is None, reason="kicad-cli not found")


def _board(name: str, tmp_path: Path) -> Path:
    """A copy: kicad-cli writes .kicad_prl next to what it opens."""
    return Path(shutil.copytree(DATA / name, tmp_path / name))


def _write(board: Path) -> Path:
    return write_schematic(board / "circuit.json", board / "out", symbols=symbols_from_rules(board / "rules.toml"),
                           project=board / "board.kicad_pro")


def test_symbols_come_from_the_rules_toml_parts():
    assert symbols_from_rules(DATA / "mcp9808" / "rules.toml") == {"U1": "Sensor_Temperature:MCP9808_MSOP"}


@pytest.mark.parametrize("name", CLEAN)
def test_a_real_board_gets_a_schematic_with_no_erc_errors_or_warnings(name, tmp_path):
    board = _board(name, tmp_path)
    result = check_schematic(_write(board), board / "circuit.json", board / "board.kicad_pcb")
    assert result["erc"] == {"errors": 0, "warnings": 0, "items": []}
    assert result["problems"] == []


@pytest.mark.parametrize("name", CLEAN)
def test_reflow_check_on_it_is_clean_and_its_nets_are_the_boards(name, tmp_path):
    board = _board(name, tmp_path)
    result = check_schematic(_write(board), board / "circuit.json", board / "board.kicad_pcb")
    assert result["check"]["errors"] == 0, result["check"]["violations"]
    assert result["nets"] == {"circuit_json": True, "pcb": True, "differences": []}


@pytest.mark.parametrize("name", CLEAN)
def test_it_uses_real_kicad_symbols_on_the_grid(name, tmp_path):
    board = _board(name, tmp_path)
    text = _write(board).read_text(encoding="utf-8")
    lib_ids = set(re.findall(r'\(lib_id "([^"]+)"\)', text))
    assert lib_ids <= {"Device:R", "Device:C", "power:PWR_FLAG", *symbols_from_rules(board / "rules.toml").values()} | {
        f"Connector_Generic:Conn_01x{n:02d}" for n in range(1, 41)}
    placed = text[text.index("(lib_symbols"):]
    placed = placed[_block_end(placed):]  # what's drawn on the sheet, not KiCad's own symbol artwork
    points = (re.findall(r"\(xy ([-\d.]+) ([-\d.]+)\)", placed)
              + re.findall(r'\(label "[^"]*"\s*\(at ([-\d.]+) ([-\d.]+)', placed)
              + re.findall(r"\(no_connect\s*\(at ([-\d.]+) ([-\d.]+)", placed)
              + re.findall(r'\(lib_id "[^"]*"\)\s*\(at ([-\d.]+) ([-\d.]+)', placed))
    assert len(points) > 20
    for x, y in points:  # every connection point and symbol origin on KiCad's 1.27 mm grid
        assert abs(float(x) / 1.27 - round(float(x) / 1.27)) < 1e-6 and abs(float(y) / 1.27 - round(float(y) / 1.27)) < 1e-6


def _block_end(text: str) -> int:
    depth = 0
    for i, ch in enumerate(text):
        depth += {"(": 1, ")": -1}.get(ch, 0)
        if depth == 0:
            return i + 1
    raise AssertionError("unbalanced")


def test_a_pin_the_board_leaves_open_gets_a_no_connect_flag(tmp_path):
    board = _board("mcp9808", tmp_path)
    text = _write(board).read_text(encoding="utf-8")
    open_pins = [n for n, pins in load_circuit_json(board / "circuit.json").nets.items() if len(pins) == 1]
    assert open_pins == ["unconnected-(U1-Alert-Pad3)"]
    assert text.count("(no_connect") == 1


def test_tscircuits_own_export_fails_the_same_check(tmp_path):
    """Why we write our own: tscircuit's export of the same PCF8574 board."""
    board = _board("pcf8574", tmp_path)
    result = check_schematic(board / "tscircuit.kicad_sch", board / "circuit.json", board / "board.kicad_pcb")
    assert result["erc"]["errors"] == 21
    assert result["nets"]["circuit_json"] is False and result["problems"]


def test_an_led_is_refused_because_tscircuit_puts_the_anode_on_pad_1(tmp_path):
    board = _board("led", tmp_path)
    with pytest.raises(SchematicError, match=r"D1.*anode.*pad 1"):
        write_schematic(board / "circuit.json", board / "out", symbols={}, project=board / "board.kicad_pro")


def test_a_pin_the_kicad_symbol_lacks_is_refused(tmp_path):
    board = _board("ams1117", tmp_path)
    with pytest.raises(SchematicError, match=r"U1 pin 4.*Regulator_Linear:AMS1117-3.3"):
        _write(board)


def test_a_chip_with_no_kicad_symbol_is_refused(tmp_path):
    board = _board("mcp9808", tmp_path)
    with pytest.raises(SchematicError, match=r"U1.*rules.toml"):
        write_schematic(board / "circuit.json", board / "out", symbols={}, project=board / "board.kicad_pro")


def test_a_schematic_whose_nets_differ_from_the_board_is_a_problem(tmp_path):
    board = _board("mcp9808", tmp_path)
    sch = _write(board)
    text = sch.read_text(encoding="utf-8")
    first = re.search(r'\(label "SDA"', text)
    sch.write_text(text[:first.start()] + '(label "SDA_X"' + text[first.end():], encoding="utf-8")
    result = check_schematic(sch, board / "circuit.json", board / "board.kicad_pcb")
    assert result["nets"]["circuit_json"] is False and result["nets"]["pcb"] is True  # the PCB still matches
    assert any("SDA" in d for d in result["nets"]["differences"]) and result["problems"]
