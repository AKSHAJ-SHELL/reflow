"""O-02: report.json / report.md for a run, with every attempt's compile errors and violations and the final DRC.

Both inputs are real run folders (tests/data/real_runs/*/README.md). A failed
run gets the same report as a passed one (golden rule 6), and nothing says
"routed" without our DRC result.
"""
import json
import shutil
from pathlib import Path

import pytest

from reflow import cli
from reflow.contracts import RouteResult, SignOff, from_dict, to_dict
from reflow.report import ReportError, build_report, render_markdown, write_report

ROOT = Path(__file__).resolve().parents[1]
MCP = ROOT / "tests" / "data" / "real_runs" / "learn_mcp9808_20261022"
AMS = ROOT / "tests" / "data" / "real_runs" / "ams1117_compile_fail_20261022"
EXAMPLES = ROOT / "docs" / "examples"


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _copy(run: Path, tmp_path: Path) -> Path:
    return Path(shutil.copytree(run, tmp_path / run.name, ignore=shutil.ignore_patterns("build")))


def _route(**changes) -> RouteResult:
    data = _json(EXAMPLES / "route_result.json") | changes
    return from_dict(RouteResult, data)


def test_every_attempts_violations_are_in_the_report_as_verify_wrote_them():
    report = build_report(MCP)
    assert (report["run_id"], report["status"], report["best_attempt"]) == ("mcp9808_breakout", "passed", 2)
    assert [a["attempt"] for a in report["attempts"]] == [1, 2]
    for attempt in report["attempts"]:
        assert attempt["verify"] == _json(MCP / "attempts" / f"{attempt['attempt']:02d}" / "verify.json")
    assert len(report["attempts"][0]["verify"]["violations"]) == 10
    assert report["verify"] == report["attempts"][1]["verify"]
    assert report["tokens"] == {"input": 5579, "output": 41320}
    assert report["parts"] == _json(MCP / "parts.json")
    assert report["route"] is None and report["signoff"] is None


def test_compile_tries_are_listed_with_their_errors_and_an_uncompiled_attempt_has_no_verify():
    report = build_report(AMS)
    assert report["status"] == "failed_verify" and report["best_attempt"] == 1
    first, second = report["attempts"]
    assert [t["ok"] for t in first["compile_tries"]] == [False, True]
    assert first["compile_tries"][0]["errors"][0]["message"].startswith('Invalid footprint prop on chip "U1"')
    assert [v["rule_id"] for v in first["verify"]["violations"]] == ["pinout.mismatch"]
    assert second["compiled"] is False and second["verify"] is None
    assert [t["errors"][0]["message"] for t in second["compile_tries"]][0] == "model response contained no code fence"
    assert report["verify"] == first["verify"]


def test_markdown_shows_every_violation_and_compile_error_and_says_it_was_not_routed():
    md = render_markdown(build_report(AMS))
    assert md.startswith("# AMS1117 3.3V regulator\n")
    assert "**failed verify**" in md
    assert "pinout.mismatch" in md and "U1 pin 4 is labelled pin4" in md
    assert "model response contained no code fence" in md
    assert md.count('Invalid footprint prop on chip "U1"') == 2
    assert "Not routed or DRC-checked" in md
    assert "C1.pin" not in md  # nothing from the example route leaks in

    mcp = render_markdown(build_report(MCP))
    for violation in _json(MCP / "attempts" / "01" / "verify.json")["violations"]:
        assert violation["message"] in mcp
    assert "**passed verify**" in mcp and "doesn't check everything" in mcp


def test_routing_and_drc_are_reported_from_the_route_result_with_over_length_traces():
    route = _route()
    report = build_report(MCP, route=route)
    assert report["route"] == to_dict(route)
    md = render_markdown(report)
    assert f"{route.routed_nets}/{route.total_nets} nets in copper" in md
    assert f"KiCad DRC (JLCPCB 2-layer rules): {route.drc.errors} errors, {route.drc.unconnected} unconnected" in md
    assert "over length: GND C1.pin2–U1.A0 14.01 mm (limit 5.0 mm)" in md


def test_unrouted_nets_are_named(tmp_path):
    md = render_markdown(build_report(MCP, route=_route(status="partial", unrouted_nets=["SDA", "SCL"], too_long=[])))
    assert "partly routed" in md and "unrouted: SDA, SCL" in md


def test_a_saved_route_and_signoff_in_the_run_folder_are_read(tmp_path):
    run = _copy(MCP, tmp_path)
    (run / "route").mkdir()
    shutil.copy(EXAMPLES / "route_result.json", run / "route" / "route.json")
    shutil.copy(EXAMPLES / "signoff.json", run / "signoff.json")
    report = build_report(run)
    assert report["route"] == _json(EXAMPLES / "route_result.json")
    assert report["signoff"] == to_dict(from_dict(SignOff, _json(EXAMPLES / "signoff.json")))
    assert "Signed off: accepted" in render_markdown(report)


def test_a_verify_report_that_disagrees_with_run_json_fails_loudly(tmp_path):
    run = _copy(MCP, tmp_path)
    verify = run / "attempts" / "01" / "verify.json"
    data = _json(verify)
    data["violations"].pop()
    data["errors"] = 9
    verify.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ReportError, match="attempt 1"):
        build_report(run)


def test_a_compiled_attempt_without_its_verify_report_fails_loudly(tmp_path):
    run = _copy(MCP, tmp_path)
    (run / "attempts" / "02" / "verify.json").unlink()
    with pytest.raises(ReportError, match="verify.json"):
        build_report(run)


def test_an_uncompiled_attempt_without_its_compile_record_fails_loudly(tmp_path):
    run = _copy(AMS, tmp_path)
    for f in (run / "attempts" / "02").glob("compile-*.json"):
        f.unlink()
    with pytest.raises(ReportError, match="compile"):
        build_report(run)


def test_write_report_puts_both_files_in_the_run_folder(tmp_path):
    run = _copy(AMS, tmp_path)
    json_path, md_path = write_report(run)
    assert (json_path, md_path) == (run / "report.json", run / "report.md")
    assert _json(json_path) == build_report(run)
    assert md_path.read_text(encoding="utf-8") == render_markdown(build_report(run))


def test_cli_report_writes_the_files_and_says_the_status(tmp_path, capsys):
    run = _copy(AMS, tmp_path)
    assert cli.main(["report", str(run)]) == 0
    assert (run / "report.json").is_file() and (run / "report.md").is_file()
    assert "failed verify" in capsys.readouterr().out


def test_cli_report_rejects_a_folder_that_is_not_a_run(tmp_path, capsys):
    assert cli.main(["report", str(tmp_path)]) == 2
    assert "run.json" in capsys.readouterr().err
