"""X-01 / X-04: what tscircuit's router did, checked by our own KiCad DRC (DECISIONS L-2a).

tscircuit routes inside `tsci export`, so the router's outcome is read from the
exported circuit.json and .kicad_pcb, and DRC always comes from our own
`kicad-cli pcb drc` run, never from the router (golden rule 6).
"""
import json
from pathlib import Path

import pytest

from reflow.cli import find_kicad_cli
from reflow.compile import compile_board, find_tsci
from reflow.contracts import RouteResult, from_dict, to_dict
from reflow.route import route_report

ROOT = Path(__file__).resolve().parents[1]
FIXED = (ROOT / "tests" / "data" / "routing" / "mcp9808_fixed.tsx").read_text(encoding="utf-8")
pytestmark = [
    pytest.mark.skipif(find_tsci() is None, reason="tsci not installed"),
    pytest.mark.skipif(find_kicad_cli() is None, reason="kicad-cli not found"),
]


def _report(tsx: str, tmp_path: Path) -> RouteResult:
    built = compile_board(tsx, tmp_path / "build", timeout_s=240)
    assert built.ok, built.errors
    return route_report(built.circuit_json, built.kicad_pcb, tmp_path / "route")


def test_a_skipped_autoroute_is_reported_as_failed_with_every_net_unrouted(tmp_path):
    result = _report(FIXED, tmp_path)
    assert result.status == "failed" and result.router == "tscircuit"
    assert result.routed_nets == 0 and result.total_nets > 0
    assert sorted(result.unrouted_nets) == sorted(set(result.unrouted_nets)) and len(result.unrouted_nets) == result.total_nets
    assert result.drc.unconnected > 0


def test_with_a_3mm_decoupling_limit_every_connection_is_copper(tmp_path):
    tsx = FIXED.replace('<capacitor name="C1"', '<capacitor name="C1" maxDecouplingTraceLength="3mm"')
    result = _report(tsx, tmp_path)
    assert result.unrouted_nets == [] and result.routed_nets == result.total_nets > 0
    assert result.drc.unconnected == 0
    assert Path(result.drc.report_path).is_file()
    report = json.loads(Path(result.drc.report_path).read_text(encoding="utf-8"))
    errors = sum(v["severity"] == "error" for v in report["violations"])
    assert result.drc.errors == errors
    # "routed" only when every connection is copper and our DRC has no errors
    assert result.status == ("routed" if errors == 0 else "partial")


def test_the_result_is_a_strict_route_result(tmp_path):
    result = _report(FIXED, tmp_path)
    assert from_dict(RouteResult, json.loads(json.dumps(to_dict(result)))) == result



def test_exported_boards_carry_jlcpcb_rules_and_the_routed_board_passes_them(tmp_path):
    """With the 3 mm decoupling limit the board routes, and under JLCPCB's 2-layer minimums
    (0.10 mm track/space, 0.15/0.25 mm via) tscircuit's 0.15 mm tracks and 0.2/0.3 mm vias pass."""
    tsx = FIXED.replace('<capacitor name="C1"', '<capacitor name="C1" maxDecouplingTraceLength="3mm"')
    built = compile_board(tsx, tmp_path / "build", timeout_s=240)
    assert (Path(built.kicad_pcb).parent / "board.kicad_pro").is_file()
    result = route_report(built.circuit_json, built.kicad_pcb, tmp_path / "route")
    assert result.drc.errors == 0 and result.drc.unconnected == 0, result.drc.report_path
    assert result.status == "routed"


def test_a_track_thinner_than_jlcpcbs_minimum_still_fails_drc(tmp_path):
    """Known-bad: the rules are applied, not switched off. A 0.05 mm track is under JLCPCB's 0.10 mm."""
    import re

    tsx = FIXED.replace('<capacitor name="C1"', '<capacitor name="C1" maxDecouplingTraceLength="3mm"')
    built = compile_board(tsx, tmp_path / "build", timeout_s=240)
    pcb = Path(built.kicad_pcb)
    text = pcb.read_text(encoding="utf-8")
    thin, n = re.subn(r"(\(segment\b.*?\(width )0\.15(\))", r"\g<1>0.05\2", text, count=1, flags=re.S)
    assert n == 1
    pcb.write_text(thin, encoding="utf-8")
    result = route_report(built.circuit_json, built.kicad_pcb, tmp_path / "route")
    report = json.loads(Path(result.drc.report_path).read_text(encoding="utf-8"))
    assert any(v["type"] == "track_width" and v["severity"] == "error" for v in report["violations"])
    assert result.status == "partial"
