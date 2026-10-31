"""Fab design rules for the exported KiCad board: JLCPCB standard 2-layer.

Source: https://jlcpcb.com/capabilities/pcb-capabilities (read 2026-10-23):
  "Min. track width and spacing (1 oz)": "0.10 / 0.10 mm (4 / 4 mil)"
  "Min. Via hole size/diameter": "0.15/0.25mm (0.1mm/0.2mm only available for board thickness <=1mm; ENIG/OSP ...)"
  "Drill Diameter": "2-layer: 0.15 - 6.3 mm"
  "Pad to track clearance (1oz)": "0.1mm"
  "Via Hole-to-Hole Spacing": "0.2mm"
  Routed outline: "Copper clearance from routed board edges: >=0.2 mm"
  "Via diameter should be 0.1mm (0.15mm preferred) larger than Via hole size" -> via annular ring 0.05 mm
  Silkscreen: "Minimum line width >=0.15mm", "Minimum text height 40 mil (1.0mm)"
"""
import json
from pathlib import Path

import pytest

from reflow.fab_rules import JLCPCB_2LAYER, write_kicad_project


def test_the_numbers_are_jlcpcbs_published_2_layer_minimums():
    r = JLCPCB_2LAYER.rules
    assert (r["min_track_width"], r["min_clearance"]) == (0.10, 0.10)
    assert (r["min_through_hole_diameter"], r["min_via_diameter"], r["min_via_annular_width"]) == (0.15, 0.25, 0.05)
    assert (r["min_hole_to_hole"], r["min_copper_edge_clearance"]) == (0.20, 0.20)
    assert (r["min_text_height"], r["min_text_thickness"]) == (1.0, 0.15)
    assert JLCPCB_2LAYER.netclass_clearance == 0.10
    assert JLCPCB_2LAYER.source_url == "https://jlcpcb.com/capabilities/pcb-capabilities"
    assert JLCPCB_2LAYER.read_on == "2026-10-23"


def test_the_project_file_sits_next_to_the_board_and_carries_the_rules(tmp_path):
    board = tmp_path / "board.kicad_pcb"
    board.write_text("(kicad_pcb)\n", encoding="utf-8")
    pro = write_kicad_project(board)
    assert pro == tmp_path / "board.kicad_pro"
    data = json.loads(pro.read_text(encoding="utf-8"))
    assert data["board"]["design_settings"]["rules"] == JLCPCB_2LAYER.rules
    default = next(c for c in data["net_settings"]["classes"] if c["name"] == "Default")
    assert default["clearance"] == 0.10
    assert data["meta"]["filename"] == "board.kicad_pro"
    assert "jlcpcb.com/capabilities/pcb-capabilities" in data["reflow"]["fab_rules_source"]


# ---------------------------------------------------------------------------
# hole to copper: JLCPCB "Via hole to Track" 0.2mm, "PTH to Track" 0.28mm
# ("0.35mm is recommended, minimum 0.28mm"); same page, re-read 2026-10-27.
# KiCad's base rules have one hole clearance, so the two live in board.kicad_dru.
# ---------------------------------------------------------------------------

from reflow.cli import find_kicad_cli  # noqa: E402

ROUTING = Path(__file__).resolve().parent / "data" / "routing"
needs_kicad = pytest.mark.skipif(find_kicad_cli() is None, reason="kicad-cli not found")


def test_the_hole_clearances_are_jlcpcbs():
    assert JLCPCB_2LAYER.via_hole_clearance == 0.20
    assert JLCPCB_2LAYER.pth_hole_clearance == 0.28
    assert JLCPCB_2LAYER.rules["min_hole_clearance"] == 0.20


def test_the_rules_file_next_to_the_board_has_both_hole_rules(tmp_path):
    board = tmp_path / "board.kicad_pcb"
    board.write_text("(kicad_pcb)\n", encoding="utf-8")
    write_kicad_project(board)
    dru = (tmp_path / "board.kicad_dru").read_text(encoding="utf-8")
    assert dru.startswith("(version 1)")
    assert "(constraint hole_clearance (min 0.2mm))" in dru and "A.Type == 'Via'" in dru
    assert "(constraint hole_clearance (min 0.28mm))" in dru and "A.Pad_Type == 'Through-hole'" in dru


def _drc(tmp_path, fixture: str, rules=JLCPCB_2LAYER) -> list[dict]:
    import shutil

    from reflow.route import _drc as run_drc

    tmp_path.mkdir(parents=True, exist_ok=True)
    board = tmp_path / "board.kicad_pcb"
    shutil.copy(ROUTING / fixture, board)
    write_kicad_project(board, rules)
    summary = run_drc(board, tmp_path / "drc")
    return [v for v in json.loads(Path(summary.report_path).read_text())["violations"] if v["severity"] == "error"]


@needs_kicad
def test_a_via_0_198mm_from_a_track_fails_jlcpcbs_via_rule(tmp_path):
    errors = _drc(tmp_path, "at24c02_via_0198mm.kicad_pcb")
    assert [e["type"] for e in errors] == ["hole_clearance"]
    assert "JLCPCB via hole to track" in errors[0]["description"]


@needs_kicad
def test_a_via_0_216mm_from_a_pad_passes(tmp_path):
    """KiCad's 0.25 mm default flagged it; JLCPCB's via minimum is 0.2 mm."""
    assert _drc(tmp_path, "ams1117_via_0216mm.kicad_pcb") == []


@needs_kicad
def test_the_pth_rule_applies_to_plated_through_holes(tmp_path):
    """With the PTH limit raised to 2 mm, J1's header holes (1.25 mm and up from tracks) must fail
    under the PTH rule's name; at JLCPCB's 0.28 mm the same board passes."""
    import dataclasses

    strict = dataclasses.replace(JLCPCB_2LAYER, pth_hole_clearance=2.0)
    errors = _drc(tmp_path / "strict", "mcp9808_routed_headers.kicad_pcb", strict)
    assert errors and all("JLCPCB PTH hole to track" in e["description"] for e in errors)
    assert _drc(tmp_path / "jlc", "mcp9808_routed_headers.kicad_pcb") == []
