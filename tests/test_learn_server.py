"""L-10: the learn server reads a run folder and serves spot-the-bug (DECISIONS L-2).

Runs against a copy of a real run (tests/data/real_runs/learn_mcp9808_20261022)
through FastAPI's test client. Needs the optional `[learn]` extra; without it
these tests skip, like the tsci-backed ones skip without tsci.
"""
import json
import shutil
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from reflow.contracts import LearnRecord, SignOff, from_dict  # noqa: E402
from reflow.learn.server import create_app  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FAILED_FIRST = ROOT / "tests" / "data" / "real_runs" / "learn_mcp9808_20261022"
PASSED_FIRST = ROOT / "tests" / "data" / "real_runs" / "learn_at24c02_first_pass_20261022"


@pytest.fixture
def run(tmp_path) -> Path:
    folder = tmp_path / "run"
    shutil.copytree(FAILED_FIRST, folder)
    return folder


def _client(run_dir: Path) -> TestClient:
    return TestClient(create_app(run_dir))


def test_run_gives_the_viewers_what_they_need(run):
    data = _client(run).get("/api/run").json()
    assert data["spec"]["title"] and data["best_attempt"] == 2
    assert [a["number"] for a in data["attempts"]] == [1, 2]
    assert data["attempts"][0]["errors"] == 10 and data["attempts"][1]["errors"] == 0
    assert data["attempts"][0]["violations"][0]["rule_id"]


def test_circuit_json_per_attempt(run):
    client = _client(run)
    first = client.get("/api/circuit/1").json()
    assert any(e["type"] == "schematic_component" for e in first)
    assert first == json.loads((run / "attempts" / "01" / "build" / "circuit.json").read_text(encoding="utf-8"))
    assert client.get("/api/circuit/9").status_code == 404


def test_next_interaction_hides_the_answer(run):
    nxt = _client(run).get("/api/learn/next").json()
    assert nxt["done"] is False
    item = nxt["interaction"]
    assert item["kind"] == "spot_bug" and item["attempt"] == 1
    assert "answer_refs" not in item and "why" not in item and "fix_hint" not in item and "message" not in item
    assert "U1" not in json.dumps(item)


def test_answering_right_reveals_the_why_and_records_it(run):
    client = _client(run)
    nxt = client.get("/api/learn/next").json()
    item = nxt["interaction"]
    assert (nxt["index"], nxt["total"]) == (1, 1)
    assert any("consequence" in note for note in nxt["notes"])
    result = client.post("/api/learn/answer", json={"id": item["id"], "ref": "U1", "why": "labels are wrong"}).json()
    assert result["outcome"] == "correct" and result["rating"] == "good"
    assert result["answer_refs"] == ["U1"] and result["why"] and result["fix_hint"]
    record = from_dict(LearnRecord, json.loads((run / "learn.json").read_text(encoding="utf-8")))
    assert [(i.rule_id, i.correct, i.user_answer) for i in record.interactions] == [
        ("pinout.mismatch", True, "U1: labels are wrong"),
    ]
    assert client.get("/api/learn/next").json() == {"done": True, "reason": "all done", "skipped": [], "notes": nxt["notes"]}


def test_a_wrong_click_gets_the_hint_then_the_answer(run):
    client = _client(run)
    item = client.get("/api/learn/next").json()["interaction"]
    first = client.post("/api/learn/answer", json={"id": item["id"], "ref": "C1", "why": ""}).json()
    assert first == {"outcome": "try_again", "hint": item["hint"]}
    assert not (run / "learn.json").exists()
    second = client.post("/api/learn/answer", json={"id": item["id"], "ref": "R1", "why": "guess"}).json()
    assert second["outcome"] == "wrong" and second["rating"] == "again" and second["answer_refs"] == ["U1"]


def test_asking_for_the_hint_counts(run):
    client = _client(run)
    item = client.get("/api/learn/next").json()["interaction"]
    assert client.post("/api/learn/hint", json={"id": item["id"]}).json() == {"hint": item["hint"]}
    result = client.post("/api/learn/answer", json={"id": item["id"], "ref": "U1", "why": ""}).json()
    assert result["rating"] == "hard"


def test_an_unknown_or_finished_interaction_is_refused(run):
    client = _client(run)
    assert client.post("/api/learn/answer", json={"id": "nope", "ref": "U1", "why": ""}).status_code == 404
    item = client.get("/api/learn/next").json()["interaction"]
    client.post("/api/learn/answer", json={"id": item["id"], "ref": "U1", "why": ""})
    assert client.post("/api/learn/answer", json={"id": item["id"], "ref": "U1", "why": ""}).status_code == 409


def test_a_first_draft_that_passed_has_nothing_to_spot(tmp_path):
    folder = tmp_path / "run"
    shutil.copytree(PASSED_FIRST, folder)
    nxt = _client(folder).get("/api/learn/next").json()
    assert nxt["done"] is True and "passed" in nxt["reason"]


def test_sign_off_writes_a_strict_sign_off_and_the_learn_record(run):
    client = _client(run)
    assert client.get("/api/signoff").json() == {"signed": False, "warnings": []}
    response = client.post("/api/signoff", json={"accepted": True, "overrides": ["kept soic8 footprint"]})
    signoff = from_dict(SignOff, json.loads((run / "signoff.json").read_text(encoding="utf-8")))
    assert signoff.accepted is True and signoff.overrides == ["kept soic8 footprint"]
    assert signoff.warnings_acknowledged == [] and signoff.at.endswith("Z")
    assert response.json()["accepted"] is True
    assert (run / "learn.json").is_file()
    assert client.get("/api/signoff").json()["signed"] is True


def test_sign_off_needs_a_yes_or_no(run):
    assert _client(run).post("/api/signoff", json={"overrides": []}).status_code == 422


def test_the_page_and_its_assets_are_served(run):
    client = _client(run)
    page = client.get("/")
    assert page.status_code == 200 and "<div id=\"root\">" in page.text
    for asset in __import__("re").findall(r'(?:src|href)="(/assets/[^"]+)"', page.text):
        assert client.get(asset).status_code == 200, asset


def test_the_server_only_listens_on_localhost():
    from reflow.learn.server import HOST

    assert HOST == "127.0.0.1"


def test_the_page_may_only_talk_to_this_server(run):
    """Nothing leaves the user's machine (L-2): the viewers' optional part lookups and CDN
    imports are blocked by the browser, whatever the bundle contains."""
    policy = _client(run).get("/").headers["content-security-policy"]
    directives = dict(d.strip().split(" ", 1) for d in policy.split(";") if d.strip())
    assert directives["default-src"] == "'self'"
    assert directives["connect-src"] == "'self'"
    assert "https:" not in policy and "*" not in policy


def test_the_shipped_bundle_does_not_fetch_parts_or_code_from_the_internet():
    from reflow.learn.server import STATIC

    bundle = "".join(p.read_text(encoding="utf-8") for p in (STATIC / "assets").glob("*.js"))
    assert "reflow learn runs offline" in bundle          # the CDN importer is replaced
    assert "reflow learn makes no network requests" in bundle  # the part-availability fetch is replaced
