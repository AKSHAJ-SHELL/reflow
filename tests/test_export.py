"""O-01: fab export (gerbers, drill, pos, BOM) from a routed board, refused without its report.

The board is a real eval run (tests/data/fab/README.md). Export never runs on a
board that failed verify, isn't fully routed with 0 DRC errors, was changed
after its DRC, or carries a part number from outside the resolver
(golden rules 5 and 6).
"""
import csv
import dataclasses
import json
import os
import shutil
from pathlib import Path

import pytest

from reflow import cli
from reflow.cli import find_kicad_cli
from reflow.contracts import FabPackage, ResolvedParts, RouteResult, Spec, VerifyReport, from_dict, to_dict
from reflow.export import ExportRefused, export_fab
from reflow.route import route_report

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "tests" / "data" / "fab" / "pcf8574_run"
REFS = {"C1", "J1", "J2", "R1", "R2", "U1"}
# (designators, LCSC) per BOM row: every number is the resolver's (parts.json).
BOM_ROWS = [("C1", "C307331"), ("J1", "C32713270"), ("J2", "C492407"), ("R1,R2", "C25900"), ("U1", "C7605")]
LAYERS = {"F_Cu", "B_Cu", "F_Mask", "B_Mask", "F_Paste", "B_Paste", "F_Silkscreen", "B_Silkscreen", "Edge_Cuts"}
pytestmark = pytest.mark.skipif(find_kicad_cli() is None, reason="kicad-cli not found")


def _load(cls, path: Path):
    return from_dict(cls, json.loads(path.read_text(encoding="utf-8")))


@dataclasses.dataclass
class Board:
    run: Path
    build: Path
    verify: VerifyReport
    route: RouteResult
    parts: ResolvedParts
    spec: Spec

    def export(self, out: Path, **changes) -> FabPackage:
        args = dict(verify=self.verify, route=self.route, parts=self.parts, spec=self.spec, run_dir=self.run) | changes
        return export_fab(self.build / "board.kicad_pcb", self.build / "circuit.json", out, **args)


def _routed(tmp_path: Path) -> Board:
    """A copy of the run (kicad-cli writes board.kicad_prl next to a board it opens), routed and DRC-checked."""
    run = Path(shutil.copytree(RUN, tmp_path / "run"))
    build = run / "attempts" / "01" / "build"
    route = route_report(build / "circuit.json", build / "board.kicad_pcb", run / "route")
    return Board(run, build, _load(VerifyReport, run / "attempts" / "01" / "verify.json"), route,
                 _load(ResolvedParts, run / "parts.json"), _load(Spec, run / "spec.json"))


@pytest.fixture(scope="module")
def exported(tmp_path_factory):
    board = _routed(tmp_path_factory.mktemp("fab"))
    return board, board.export(board.run / "out")


def test_the_fixture_board_is_verify_clean_and_routed_with_no_drc_errors(exported):
    board, _ = exported
    assert board.verify.errors == 0
    assert board.route.status == "routed" and board.route.drc.errors == 0 and board.route.drc.unconnected == 0


def test_gerbers_cover_both_copper_mask_paste_silk_layers_and_the_edge(exported):
    board, package = exported
    gerbers = Path(package.gerbers_dir)
    assert gerbers == board.run / "out" / "gerbers"
    plotted = {p.stem.removeprefix("board-") for p in gerbers.iterdir() if p.suffix != ".gbrjob"}
    assert plotted == LAYERS
    assert all(p.stat().st_size > 0 for p in gerbers.iterdir())
    assert (gerbers / "board-job.gbrjob").is_file()


def test_drill_is_one_metric_excellon_file_with_the_vias_and_header_holes(exported):
    _, package = exported
    drill = Path(package.drill)
    assert drill.name == "board.drl"
    text = drill.read_text(encoding="utf-8")
    assert text.startswith("M48") and "METRIC" in text
    assert "ViaDrill" in text and "ComponentDrill" in text


def test_pos_lists_every_part_in_mm(exported):
    _, package = exported
    with open(package.pos_csv, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert {r["Ref"] for r in rows} == REFS
    assert set(rows[0]) == {"Ref", "Val", "Package", "PosX", "PosY", "Rot", "Side"}
    assert all(r["Side"] == "top" for r in rows)


def test_bom_groups_parts_and_takes_every_part_number_from_the_resolver(exported):
    board, package = exported
    with open(package.bom_csv, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert list(rows[0]) == ["Comment", "Designator", "Footprint", "LCSC Part #", "MPN"]
    assert [(r["Designator"], r["LCSC Part #"]) for r in rows] == BOM_ROWS
    resolved = {(p.lcsc, p.mpn) for p in board.parts.resolved}
    assert all((r["LCSC Part #"], r["MPN"]) in resolved for r in rows)
    resistors = next(r for r in rows if r["Designator"] == "R1,R2")
    assert resistors["Comment"] == "4.7kΩ" and resistors["Footprint"]
    assert next(r for r in rows if r["Designator"] == "U1")["Comment"] == "PCF8574T/3,518"


def test_the_package_carries_the_run_report_with_the_verify_and_drc_reports(exported):
    board, package = exported
    report = json.loads(Path(package.report_json).read_text(encoding="utf-8"))
    assert report["verify"] == to_dict(board.verify)
    assert [a["attempt"] for a in report["attempts"]] == [1]
    assert report["attempts"][0]["verify"] == to_dict(board.verify)
    assert report["route"]["status"] == "routed" and report["route"]["drc"]["errors"] == 0
    drc = board.run / "out" / "drc.json"
    assert json.loads(drc.read_text(encoding="utf-8")) == json.loads(Path(board.route.drc.report_path).read_text(encoding="utf-8"))
    assert report["route"]["drc"]["report_path"] == str(drc)
    md = Path(package.design_md)
    assert md == board.run / "out" / "report.md"
    assert md.read_text(encoding="utf-8").startswith("# PCF8574 GPIO expander\n")
    assert "12/12 nets in copper" in md.read_text(encoding="utf-8")
    assert from_dict(FabPackage, to_dict(package)) == package
    assert package.report_html == ""


def test_refuses_a_verify_report_that_is_not_the_runs_best_attempt(exported, tmp_path):
    board, _ = exported
    other = dataclasses.replace(board.verify, components=board.verify.components + 1)
    assert any("best attempt" in r for r in _refused(board, tmp_path / "out", verify=other))


def _refused(board: Board, out: Path, **changes) -> list[str]:
    with pytest.raises(ExportRefused) as caught:
        board.export(out, **changes)
    assert not out.exists() or not any(out.iterdir()), "a refused export wrote files"
    return caught.value.reasons


def test_refuses_a_board_that_failed_verify(exported, tmp_path):
    board, _ = exported
    failed = dataclasses.replace(board.verify, errors=1)
    assert any("verify" in r for r in _refused(board, tmp_path / "out", verify=failed))


@pytest.mark.parametrize("change, says", [
    (dict(status="partial", unrouted_nets=["SDA"]), "SDA"),
    (dict(status="failed", routed_nets=0), "failed"),
])
def test_refuses_a_board_that_is_not_fully_routed(exported, tmp_path, change, says):
    board, _ = exported
    reasons = _refused(board, tmp_path / "out", route=dataclasses.replace(board.route, **change))
    assert any(says in r for r in reasons)


def test_refuses_a_board_with_drc_errors_even_if_called_routed(exported, tmp_path):
    board, _ = exported
    drc = dataclasses.replace(board.route.drc, errors=2)
    reasons = _refused(board, tmp_path / "out", route=dataclasses.replace(board.route, drc=drc))
    assert any("2 DRC errors" in r for r in reasons)


def test_refuses_when_the_drc_was_run_on_a_different_board(exported, tmp_path):
    board, _ = exported
    other = dataclasses.replace(board.route, kicad_pcb=str(tmp_path / "other.kicad_pcb"))
    assert any("different board" in r for r in _refused(board, tmp_path / "out", route=other))


def test_refuses_without_the_drc_report_file(tmp_path):
    board = _routed(tmp_path)
    Path(board.route.drc.report_path).unlink()
    assert any("DRC report" in r for r in _refused(board, tmp_path / "out"))


def test_refuses_a_board_changed_after_its_drc(tmp_path):
    board = _routed(tmp_path)
    pcb = board.build / "board.kicad_pcb"
    later = Path(board.route.drc.report_path).stat().st_mtime + 10
    os.utime(pcb, (later, later))
    assert any("changed after" in r for r in _refused(board, tmp_path / "out"))


def test_refuses_a_part_number_from_outside_the_resolver(tmp_path):
    board = _routed(tmp_path)
    circuit = board.build / "circuit.json"
    elements = json.loads(circuit.read_text(encoding="utf-8"))
    r1 = next(e for e in elements if e["type"] == "source_component" and e["name"] == "R1")
    r1["supplier_part_numbers"] = {"jlcpcb": ["C99999"]}
    circuit.write_text(json.dumps(elements), encoding="utf-8")
    assert any("R1" in r and "C99999" in r for r in _refused(board, tmp_path / "out"))


def test_refuses_into_a_folder_that_already_holds_files(exported, tmp_path):
    board, _ = exported
    out = tmp_path / "out"
    out.mkdir()
    (out / "old.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ExportRefused) as caught:
        board.export(out)
    assert any("not empty" in r for r in caught.value.reasons)
    assert sorted(p.name for p in out.iterdir()) == ["old.txt"]


# --- reflow export RUN_DIR ---------------------------------------------------

def test_cli_routes_the_best_attempt_and_exports_into_the_run_folder(tmp_path, capsys):
    run = Path(shutil.copytree(RUN, tmp_path / "run"))
    assert cli.main(["export", str(run)]) == 0
    route = _load(RouteResult, run / "route" / "route.json")
    assert route.status == "routed" and route.drc.errors == 0
    package = _load(FabPackage, run / "out" / "fab_package.json")
    for path in (package.drill, package.pos_csv, package.bom_csv, package.report_json, package.design_md):
        assert Path(path).is_file() and Path(path).parent == run / "out"
    out = capsys.readouterr().out
    assert "routed" in out and str(run / "out") in out


def test_cli_refuses_a_run_whose_best_attempt_failed_verify(tmp_path, capsys):
    run = Path(shutil.copytree(RUN, tmp_path / "run"))
    violation = {"rule_id": "i2c.missing_pullup", "severity": "error", "message": "SDA has no pull-up",
                 "why": "w", "fix_hint": "f", "refs": [], "nets": ["SDA"]}
    verify = run / "attempts" / "01" / "verify.json"
    data = json.loads(verify.read_text(encoding="utf-8"))
    data |= {"errors": 1, "violations": [violation]}
    verify.write_text(json.dumps(data), encoding="utf-8")
    record = json.loads((run / "run.json").read_text(encoding="utf-8"))
    record["status"] = "failed_verify"
    record["attempts"][0] |= {"errors": 1, "rule_ids": ["i2c.missing_pullup"]}
    (run / "run.json").write_text(json.dumps(record), encoding="utf-8")
    assert cli.main(["export", str(run)]) == 1
    assert "verify" in capsys.readouterr().err
    assert not (run / "out").exists()
    report = json.loads((run / "report.json").read_text(encoding="utf-8"))
    assert report["route"]["status"] == "routed" and report["verify"]["errors"] == 1
    assert (run / "report.md").is_file()


def test_cli_rejects_a_folder_that_is_not_a_run(tmp_path, capsys):
    assert cli.main(["export", str(tmp_path)]) == 2
    assert "run.json" in capsys.readouterr().err


def test_cli_refuses_a_run_with_nothing_compiled(tmp_path, capsys):
    run = Path(shutil.copytree(RUN, tmp_path / "run"))
    data = json.loads((run / "run.json").read_text(encoding="utf-8"))
    data["best_attempt"] = 0
    (run / "run.json").write_text(json.dumps(data), encoding="utf-8")
    assert cli.main(["export", str(run)]) == 1
    assert "no attempt compiled" in capsys.readouterr().err
