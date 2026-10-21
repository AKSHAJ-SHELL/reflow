"""V-14: .kicad_pcb -> {(ref, pad): net}.

The gerbers are made from the .kicad_pcb, so V-1 (d) compares its pad nets
with the circuit.json netlist (that comparison is V-13, HUMAN). Here the
reader is checked three ways:

- tscircuit's export (tests/data/circuit_json/*.kicad_pcb, recorded in the
  same tsci 0.0.2768 run as the .circuit.json beside it) groups pads exactly
  as circuit.json groups pins. Unnamed nets carry different names in the two
  files, so groups are compared, not names.
- A real KiCad 10 board (fixtures/real_good, read only) groups pads exactly
  as its own schematic netlist does. Needs kicad-cli; skips without it.
- Hand-written snippets cover both net syntaxes and the error cases.
"""
import shutil
from pathlib import Path

import pytest

from reflow.circuit_netlist import load_circuit_json
from reflow.cli import export_netlist, find_kicad_cli
from reflow.netlist import load_netlist
from reflow.pcb_nets import PcbNetsError, load_pcb_pad_nets

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "tests" / "data" / "circuit_json"
club = ROOT / "fixtures" / "real_good"


def _pad_groups(pads: dict[tuple[str, str], str]) -> set[frozenset]:
    by_net: dict[str, set] = {}
    for key, net in pads.items():
        if net and not net.startswith("unconnected-"):
            by_net.setdefault(net, set()).add(key)
    return {frozenset(members) for members in by_net.values()}


def _netlist_groups(nl) -> set[frozenset]:
    return {
        frozenset((p.ref, p.pin) for p in pins)
        for name, pins in nl.nets.items()
        if not nl.is_unconnected(name)
    }


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "board.kicad_pcb"
    path.write_text(text, encoding="utf-8")
    return path


def _footprint(ref_line: str, *pads: str) -> str:
    return f'(footprint "lib:fp" (layer "F.Cu") {ref_line} ' + " ".join(pads) + ")"


# ---------------------------------------------------------------------------
# recorded boards
# ---------------------------------------------------------------------------

def test_tscircuit_pcb_pad_nets_match_the_traces():
    pads = load_pcb_pad_nets(DATA / "sensor_good.kicad_pcb")
    assert pads[("U1", "1")] == "SDA"
    assert pads[("U1", "4")] == "GND"
    assert pads[("U1", "8")] == "V3_3"
    assert pads[("J1", "3")] == "SDA"
    assert pads[("R1", "1")] == "SDA"
    assert pads[("U1", "7")] == ""      # ALERT: traced nowhere
    assert len(pads) == 18              # U1 8 + J1 4 + C1, R1, R2 2 each


@pytest.mark.parametrize("board", ["sensor_good", "sensor_series_cap"])
def test_tscircuit_pcb_groups_pads_like_circuit_json(board):
    pads = load_pcb_pad_nets(DATA / f"{board}.kicad_pcb")
    nl = load_circuit_json(DATA / f"{board}.circuit.json")
    assert _pad_groups(pads) == _netlist_groups(nl)


@pytest.mark.skipif(find_kicad_cli() is None, reason="kicad-cli not found")
def test_kicad_board_groups_pads_like_its_schematic(tmp_path):
    pads = load_pcb_pad_nets(club / "real_good.kicad_pcb")
    sch = next(club.glob("*.kicad_sch"))
    nl = load_netlist(export_netlist(find_kicad_cli(), sch, tmp_path / "board.net"))
    assert len(pads) == 29
    assert _pad_groups(pads) == _netlist_groups(nl)


# ---------------------------------------------------------------------------
# syntax variants
# ---------------------------------------------------------------------------

def test_reads_kicad_10_and_numbered_net_forms(tmp_path):
    text = "(kicad_pcb (version 20260206) " + _footprint(
        '(property "Reference" "R1")',
        '(pad "1" smd rect (at 0 0) (net "+3.3V"))',
        '(pad "2" smd rect (at 1 0) (net 2 "GND"))',
    ) + ")"
    assert load_pcb_pad_nets(_write(tmp_path, text)) == {("R1", "1"): "+3.3V", ("R1", "2"): "GND"}


def test_reads_the_older_fp_text_reference(tmp_path):
    text = "(kicad_pcb " + _footprint('(fp_text reference "C3" (at 0 0))', '(pad "1" smd rect (net 1 "GND"))') + ")"
    assert load_pcb_pad_nets(_write(tmp_path, text)) == {("C3", "1"): "GND"}


def test_pad_without_a_net_and_net_zero_are_empty(tmp_path):
    text = "(kicad_pcb " + _footprint(
        '(property "Reference" "U2")', '(pad "1" smd rect)', '(pad "2" smd rect (net 0 ""))',
    ) + ")"
    assert load_pcb_pad_nets(_write(tmp_path, text)) == {("U2", "1"): "", ("U2", "2"): ""}


def test_unnumbered_pads_and_padless_footprints_are_skipped(tmp_path):
    text = "(kicad_pcb " + _footprint('(property "Reference" "H1")', '(pad "" np_thru_hole circle)') + \
        ' (footprint "lib:logo" (layer "F.Cu"))' + ")"
    assert load_pcb_pad_nets(_write(tmp_path, text)) == {}


def test_a_repeated_pad_on_the_same_net_is_one_entry(tmp_path):
    """Exposed pads are often split into several pads with one number."""
    text = "(kicad_pcb " + _footprint(
        '(property "Reference" "U3")', '(pad "9" smd rect (net "GND"))', '(pad "9" smd rect (net "GND"))',
    ) + ")"
    assert load_pcb_pad_nets(_write(tmp_path, text)) == {("U3", "9"): "GND"}


# ---------------------------------------------------------------------------
# errors
# ---------------------------------------------------------------------------

def test_a_repeated_pad_on_two_nets_raises(tmp_path):
    text = "(kicad_pcb " + _footprint(
        '(property "Reference" "U3")', '(pad "9" smd rect (net "GND"))', '(pad "9" smd rect (net "+3.3V"))',
    ) + ")"
    with pytest.raises(PcbNetsError, match="U3"):
        load_pcb_pad_nets(_write(tmp_path, text))


def test_duplicate_reference_raises(tmp_path):
    fp = _footprint('(property "Reference" "R1")', '(pad "1" smd rect (net "GND"))')
    with pytest.raises(PcbNetsError, match="R1"):
        load_pcb_pad_nets(_write(tmp_path, f"(kicad_pcb {fp} {fp})"))


def test_footprint_with_pads_and_no_reference_raises(tmp_path):
    text = '(kicad_pcb (footprint "lib:fp" (pad "1" smd rect (net "GND"))))'
    with pytest.raises(PcbNetsError, match="reference"):
        load_pcb_pad_nets(_write(tmp_path, text))


@pytest.mark.parametrize("text", ["", "not sexpr", "(kicad_sch (version 1))", "(kicad_pcb (footprint"])
def test_not_a_board_raises(tmp_path, text):
    with pytest.raises(PcbNetsError):
        load_pcb_pad_nets(_write(tmp_path, text))


def test_missing_file_raises(tmp_path):
    with pytest.raises(PcbNetsError):
        load_pcb_pad_nets(tmp_path / "nope.kicad_pcb")
