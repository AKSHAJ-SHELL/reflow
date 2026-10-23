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
