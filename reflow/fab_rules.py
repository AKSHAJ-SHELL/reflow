"""Fab design rules for the exported KiCad board.  OWNER: AGENT (X-04 follow-up, 2026-10-23).

Contract
--------
    JLCPCB_2LAYER: FabRules
    write_kicad_project(kicad_pcb, rules=JLCPCB_2LAYER) -> Path    # board.kicad_pro (+ board.kicad_dru) next to the board

`tsci export` writes only a .kicad_pcb, so KiCad (and `kicad-cli pcb drc`)
falls back to its own default rules: a 0.2 mm minimum track, 0.2 mm
clearance and a 0.5 mm via. Those flag tscircuit's 0.15 mm tracks and 0.2/0.3 mm
vias, which JLCPCB makes. `write_kicad_project` puts a KiCad project file
next to the board with the fab's published minimums, so DRC (ours and the
user's in KiCad) checks the board against what the fab can actually build.

JLCPCB standard 2-layer, from https://jlcpcb.com/capabilities/pcb-capabilities
(read 2026-10-23; quotes in tests/test_fab_rules.py):

- track width / spacing (1 oz) 0.10 / 0.10 mm; pad-to-track clearance 0.1 mm;
- via hole / diameter 0.15 / 0.25 mm (0.1/0.2 mm only for boards ≤ 1 mm thick
  with ENIG/OSP, so not used here); via diameter 0.1 mm larger than the hole,
  so a 0.05 mm via annular ring;
- 2-layer drill 0.15–6.3 mm; via hole-to-hole 0.2 mm;
- copper to a routed board edge ≥ 0.2 mm;
- silkscreen line width ≥ 0.15 mm, text height ≥ 1.0 mm;
- hole to copper: "Via hole to Track" 0.2 mm, "PTH to Track" 0.28 mm
  ("0.35mm is recommended, minimum 0.28mm"; re-read 2026-10-27).

KiCad's board rules have a single hole clearance, so `min_hole_clearance` is
the via figure (0.2 mm), and `board.kicad_dru` (KiCad custom rules, read
from the board's folder) adds one rule per hole kind: vias 0.2 mm and plated
through-hole pads 0.28 mm.

Rules the page doesn't give a 2-layer number for keep KiCad's defaults. These
are JLCPCB's minimums; some sizes near them cost extra (smaller vias), which
the page notes and this file doesn't model.

Must never
----------
- loosen a rule beyond the fab's published minimum,
- change the board itself (only the project file next to it is written).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class FabRules:
    name: str
    source_url: str
    read_on: str
    rules: dict = field(default_factory=dict)      # KiCad board.design_settings.rules keys, mm
    netclass_clearance: float = 0.2
    via_hole_clearance: float = 0.0                # mm, via hole to copper (custom rule)
    pth_hole_clearance: float = 0.0                # mm, plated through-hole to copper (custom rule)


JLCPCB_2LAYER = FabRules(
    name="JLCPCB standard 2-layer",
    source_url="https://jlcpcb.com/capabilities/pcb-capabilities",
    read_on="2026-10-23",
    rules={
        "min_track_width": 0.10,
        "min_clearance": 0.10,
        "min_through_hole_diameter": 0.15,
        "min_via_diameter": 0.25,
        "min_via_annular_width": 0.05,
        "min_hole_to_hole": 0.20,
        "min_copper_edge_clearance": 0.20,
        "min_text_height": 1.0,
        "min_text_thickness": 0.15,
        "min_hole_clearance": 0.20,
    },
    netclass_clearance=0.10,
    via_hole_clearance=0.20,
    pth_hole_clearance=0.28,
)


def write_kicad_project(kicad_pcb, rules: FabRules = JLCPCB_2LAYER) -> Path:
    board = Path(kicad_pcb)
    project = board.with_suffix(".kicad_pro")
    data = {
        "board": {"design_settings": {"rules": dict(rules.rules)}},
        "net_settings": {"classes": [{
            "name": "Default", "clearance": rules.netclass_clearance, "track_width": 0.15,
            "via_diameter": 0.3, "via_drill": 0.2, "priority": 2147483647,
        }]},
        "meta": {"filename": project.name, "version": 3},
        "reflow": {"fab_rules": rules.name, "fab_rules_source": f"{rules.source_url} (read {rules.read_on})"},
    }
    project.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    board.with_suffix(".kicad_dru").write_text(_custom_rules(rules), encoding="utf-8")
    return project


def _custom_rules(rules: FabRules) -> str:
    lines = ["(version 1)", f"# {rules.name}: {rules.source_url} (read {rules.read_on})"]
    if rules.via_hole_clearance:
        lines += [f'(rule "{rules.name.split()[0]} via hole to track"',
                  f"  (constraint hole_clearance (min {rules.via_hole_clearance:g}mm))",
                  "  (condition \"A.Type == 'Via' || B.Type == 'Via'\"))"]
    if rules.pth_hole_clearance:
        lines += [f'(rule "{rules.name.split()[0]} PTH hole to track"',
                  f"  (constraint hole_clearance (min {rules.pth_hole_clearance:g}mm))",
                  "  (condition \"A.Pad_Type == 'Through-hole' || B.Pad_Type == 'Through-hole'\"))"]
    return "\n".join(lines) + "\n"
