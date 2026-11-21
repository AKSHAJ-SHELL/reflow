"""T-02: the live build view (docs/proposals/T-2-visual-beginner-front-door.md).

A small server beside the TUI shows a design run as it happens: each attempt,
whether it compiled, how many problems the verifier found, and the board itself.
It reads the run folder fresh on every request, shows only what the run wrote,
and never names the problems: finding them is learn mode's job.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from reflow.learn.build import build_status, create_build_app  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "tests" / "data" / "real_runs" / "learn_mcp9808_20261022"


@pytest.fixture
def run(tmp_path) -> Path:
    folder = tmp_path / "run"
    shutil.copytree(RUN, folder)
    return folder


def _dead_pid() -> int:
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


def test_a_finished_run_shows_every_attempt_with_counts_only(run):
    status = build_status(run, pid=None)
    assert status["started"] and status["finished"]
    assert status["status"] == "passed" and status["best_attempt"] == 2
    assert [(a["number"], a["compiled"], a["problems"], a["has_circuit"]) for a in status["attempts"]] == [
        (1, True, 10, True), (2, True, 0, True)]
    text = json.dumps(status)
    for rule_id in json.loads((run / "run.json").read_text())["attempts"][0]["rule_ids"]:
        assert rule_id not in text                     # spot-the-bug stays for learn mode


def test_before_the_loop_writes_anything_it_says_so(tmp_path):
    status = build_status(tmp_path / "not-yet", pid=os.getpid())
    assert status == {"started": False, "finished": False, "status": "", "title": "", "best_attempt": 0,
                      "attempts": []}


def test_finished_follows_the_design_process(run):
    assert build_status(run, pid=os.getpid())["finished"] is False   # still running: the status isn't final
    assert build_status(run, pid=os.getpid())["status"] == ""
    assert build_status(run, pid=_dead_pid())["finished"] is True


def test_an_attempt_still_compiling_has_no_board_yet(run):
    shutil.rmtree(run / "attempts" / "02" / "build")
    status = build_status(run, pid=None)
    assert status["attempts"][1]["has_circuit"] is False


def test_the_server_gives_status_boards_and_the_page(run):
    client = TestClient(create_build_app(run, pid=None))
    assert client.get("/api/build").json()["attempts"][0]["number"] == 1
    board = client.get("/api/build/circuit/2").json()
    assert isinstance(board, list) and any(e.get("type") == "pcb_component" for e in board)
    assert client.get("/api/build/circuit/9").status_code == 404
    page = client.get("/build")
    assert page.status_code == 200 and "html" in page.headers["content-type"]
    assert "connect-src 'self'" in page.headers["content-security-policy"]
    assert client.get("/", follow_redirects=False).headers["location"] == "/build"


def test_it_reads_the_run_folder_fresh_each_time(run):
    client = TestClient(create_build_app(run, pid=None))
    assert len(client.get("/api/build").json()["attempts"]) == 2
    data = json.loads((run / "run.json").read_text())
    data["attempts"] = data["attempts"][:1]
    (run / "run.json").write_text(json.dumps(data))
    assert len(client.get("/api/build").json()["attempts"]) == 1


def test_reflow_watch_is_a_command():
    out = subprocess.run([sys.executable, "-m", "reflow", "watch", "--help"], capture_output=True, text=True)
    assert out.returncode == 0 and "RUN_DIR" in out.stdout


# ---------------------------------------------------------------------------
# KiCad's own 3D render of an attempt's board (kicad-cli pcb render)
# ---------------------------------------------------------------------------

PCB = ROOT / "tests" / "data" / "circuit_json" / "sensor_good.kicad_pcb"


def _with_pcb(run: Path) -> Path:
    shutil.copyfile(PCB, run / "attempts" / "02" / "build" / "board.kicad_pcb")
    return run


def _files(folder: Path) -> dict:
    return {p: p.stat().st_mtime_ns for p in folder.rglob("*")}


def test_status_says_which_attempts_have_a_kicad_board(run):
    _with_pcb(run)
    assert [a["has_kicad_pcb"] for a in build_status(run, pid=None)["attempts"]] == [False, True]


KICAD = pytest.mark.skipif(__import__("reflow.cli", fromlist=["x"]).find_kicad_cli() is None,
                           reason="kicad-cli not found")
VIEWS = {"pcb": ("image/svg+xml", b"<svg"), "schematic": ("image/svg+xml", b"<svg"), "3d": ("image/png", b"\x89PNG")}


@KICAD
@pytest.mark.parametrize("view", sorted(VIEWS))
def test_every_view_is_kicads_own_and_the_run_is_untouched(run, view):
    """The human, 2026-11-21: "all views from kicad, no custom tscircuit or other kind of views"."""
    _with_pcb(run)
    before = _files(run)
    client = TestClient(create_build_app(run, pid=None))
    got = client.get(f"/api/build/kicad/2/{view}")
    kind, start = VIEWS[view]
    assert got.status_code == 200, got.text
    assert got.headers["content-type"].startswith(kind)
    assert start in got.content[:400]
    assert client.get(f"/api/build/kicad/2/{view}").content == got.content   # made once, then reused
    assert _files(run) == before                                            # nothing written into the run


def test_no_kicad_board_or_no_kicad_or_an_unknown_view_says_why(run, monkeypatch):
    client = TestClient(create_build_app(run, pid=None))
    missing = client.get("/api/build/kicad/1/pcb")
    assert missing.status_code == 404 and "no KiCad board" in missing.json()["detail"]
    assert client.get("/api/build/kicad/2/gerber").status_code == 404
    _with_pcb(run)
    monkeypatch.setattr("reflow.learn.build.find_kicad_cli", lambda: None)
    no_kicad = client.get("/api/build/kicad/2/3d")
    assert no_kicad.status_code == 503 and "KiCad" in no_kicad.json()["detail"]


def test_a_schematic_reflow_cant_draw_honestly_says_why(run, monkeypatch):
    from reflow.schematic import SchematicError

    _with_pcb(run)

    def refuse(*args, **kwargs):
        raise SchematicError("D1 is an LED, and tscircuit and KiCad number its pins differently")

    monkeypatch.setattr("reflow.learn.build.write_schematic", refuse)
    got = TestClient(create_build_app(run, pid=None)).get("/api/build/kicad/2/schematic")
    assert got.status_code == 422 and "LED" in got.json()["detail"]
