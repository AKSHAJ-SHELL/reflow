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


def _client(run_dir: Path, *, vault: Path | None = None, now=None) -> TestClient:
    """Each test gets its own vault next to its run copy, never the user's ~/.reflow/vault."""
    return TestClient(create_app(run_dir, vault=vault or run_dir.parent / "vault", now=now))


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
    assert "U1" not in json.dumps(nxt), "the pending response must not name the part anywhere (notes included)"


def test_answering_right_reveals_the_why_and_records_it(run):
    client = _client(run)
    nxt = client.get("/api/learn/next").json()
    item = nxt["interaction"]
    assert (nxt["index"], nxt["total"]) == (1, 1)
    assert "notes" not in nxt
    result = client.post("/api/learn/answer", json={"id": item["id"], "ref": "U1", "why": "labels are wrong"}).json()
    assert result["outcome"] == "correct" and result["rating"] == "good"
    assert result["answer_refs"] == ["U1"] and result["why"] and result["fix_hint"]
    record = from_dict(LearnRecord, json.loads((run / "learn.json").read_text(encoding="utf-8")))
    assert [(i.rule_id, i.correct, i.user_answer) for i in record.interactions] == [
        ("pinout.mismatch", True, "U1: labels are wrong"),
    ]
    done = client.get("/api/learn/next").json()
    assert (done["done"], done["reason"], done["skipped"]) == (True, "all done", [])
    assert any("consequence" in note for note in done["notes"])


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



# ---------------------------------------------------------------------------
# L-11: concept cards, skip logic and the vault
# ---------------------------------------------------------------------------

from datetime import datetime, timedelta, timezone  # noqa: E402

T0 = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)


def _answer_right(client):
    item = client.get("/api/learn/next").json()["interaction"]
    return client.post("/api/learn/answer", json={"id": item["id"], "ref": "U1", "why": "labels"}).json()


def test_an_answer_updates_the_concept_card_and_writes_the_notes(run):
    vault = run.parent / "vault"
    _answer_right(_client(run, vault=vault, now=lambda: T0))
    concept = (vault / "concepts" / "pinout.md").read_text(encoding="utf-8")
    assert '"2026-10-22T12:00:00Z good"' in concept
    mistakes = list((vault / "mistakes").glob("*.md"))
    assert [m.name for m in mistakes] == ["2026-10-22-mcp9808-breakout-pinout.md"]
    assert "U1: labels" in mistakes[0].read_text(encoding="utf-8")
    board = (vault / "boards" / "mcp9808-breakout.md").read_text(encoding="utf-8")
    assert "[[concepts/pinout]]" in board and "[[mistakes/2026-10-22-mcp9808-breakout-pinout]]" in board


def test_a_known_concept_is_skipped_next_time_and_can_be_asked_anyway(run, tmp_path):
    vault = tmp_path / "vault"
    _answer_right(_client(run, vault=vault, now=lambda: T0))
    again = tmp_path / "run2"
    shutil.copytree(FAILED_FIRST, again)
    client = _client(again, vault=vault, now=lambda: T0 + timedelta(days=1))
    nxt = client.get("/api/learn/next").json()
    assert nxt["done"] is True and nxt["skipped"] == ["pinout"]
    assert nxt["recall"]["pinout"] > 0.9
    assert client.post("/api/learn/unskip", json={"concept": "pinout"}).json()["skipped"] == []
    asked = client.get("/api/learn/next").json()
    assert asked["done"] is False and asked["interaction"]["concept"] == "pinout"


def test_a_wrong_answer_keeps_the_concept_asked(run, tmp_path):
    vault = tmp_path / "vault"
    client = _client(run, vault=vault, now=lambda: T0)
    item = client.get("/api/learn/next").json()["interaction"]
    client.post("/api/learn/answer", json={"id": item["id"], "ref": "C1", "why": ""})
    client.post("/api/learn/answer", json={"id": item["id"], "ref": "R1", "why": ""})
    again = tmp_path / "run2"
    shutil.copytree(FAILED_FIRST, again)
    nxt = _client(again, vault=vault, now=lambda: T0 + timedelta(days=1)).get("/api/learn/next").json()
    assert nxt["done"] is False and nxt["skipped"] == []


def test_sign_off_is_recorded_on_the_board_note(run):
    vault = run.parent / "vault"
    client = _client(run, vault=vault, now=lambda: T0)
    client.post("/api/signoff", json={"accepted": False, "overrides": []})
    board = (vault / "boards" / "mcp9808-breakout.md").read_text(encoding="utf-8")
    assert "signed_off: false" in board and "**Signed off:** no" in board


def test_the_vault_graph_endpoint(run):
    vault = run.parent / "vault"
    client = _client(run, vault=vault, now=lambda: T0)
    _answer_right(client)
    graph = client.get("/api/vault/graph").json()
    assert {n["kind"] for n in graph["nodes"]} == {"concept", "mistake", "board"}
    assert {"source": "boards/mcp9808-breakout", "target": "concepts/pinout"} in graph["links"]


def test_without_a_vault_argument_it_uses_reflow_vault(run, tmp_path, monkeypatch):
    monkeypatch.setenv("REFLOW_VAULT", str(tmp_path / "env-vault"))
    _answer_right(TestClient(create_app(run, now=lambda: T0)))
    assert (tmp_path / "env-vault" / "concepts" / "pinout.md").is_file()


# ---------------------------------------------------------------------------
# L-14 / L-12: fix-it and simulation through the server
# ---------------------------------------------------------------------------

from reflow.compile import find_tsci  # noqa: E402

needs_tsci = pytest.mark.skipif(find_tsci() is None, reason="tsci not installed")
DATASHEET = {"1": "SDA", "2": "SCL", "3": "Alert", "4": "GND", "5": "A2", "6": "A1", "7": "A0", "8": "VDD"}
WIRING = [{"kind": "connect", "a": "U1.SDA", "b": "SDA"}, {"kind": "connect", "a": "U1.SCL", "b": "SCL"},
          {"kind": "connect", "a": "U1.VDD", "b": "V3_3"}, {"kind": "connect", "a": "U1.GND", "b": "GND"}]


@pytest.fixture
def symbols(monkeypatch):
    monkeypatch.setenv("REFLOW_KICAD_SYMBOL_DIR", str(ROOT / "tests" / "data" / "pinmaps" / "kicad"))


@needs_tsci
def test_a_fix_is_compiled_and_verified_and_its_board_is_served(run, symbols):
    client = _client(run)
    edits = [{"kind": "set_label", "ref": "U1", "pin": n, "value": l} for n, l in DATASHEET.items()] + WIRING
    result = client.post("/api/fix", json={"edits": edits}).json()
    assert result["number"] == 1 and result["base_attempt"] == 1
    assert result["compiled"] and result["errors"] == 0 and not result["refused"], result["violations"]
    circuit = client.get("/api/fix/1/circuit").json()
    assert any(e["type"] == "source_component" and e["name"] == "U1" for e in circuit)


def test_a_bad_edit_is_a_400_with_the_reason(run):
    response = _client(run).post("/api/fix", json={"edits": [{"kind": "set_value", "ref": "R9", "value": "1k"}]})
    assert response.status_code == 400 and "R9" in response.json()["detail"]


@needs_tsci
def test_the_ais_fix_is_shown_only_after_the_user_tries(run, symbols):
    client = _client(run)
    assert client.get("/api/fix/ai").status_code == 403
    client.post("/api/fix", json={"edits": [{"kind": "set_label", "ref": "U1", "pin": "1", "value": "SDA"}]})
    ai = client.get("/api/fix/ai").json()
    assert ai["attempt"] == 2 and ai["diff"]
    assert any(line.startswith("+") and 'pin1: "SDA"' in line for line in ai["diff"])


def test_simulating_a_concept_without_a_testbench_says_so(run, symbols):
    result = _client(run).post("/api/sim", json={"concept": "pinout", "attempt": 1}).json()
    assert result["ran"] is False and "can't simulate" in result["notes"][0]


def test_simulating_a_board_the_testbench_cant_represent_says_why(run, symbols):
    """The AI's draft left the real VDD pin unconnected: no supply to simulate."""
    pytest.importorskip("reflow.learn.sim").find_ngspice() or pytest.skip("ngspice not installed")
    result = _client(run).post("/api/sim", json={"concept": "decoupling", "attempt": 1}).json()
    assert result["ran"] is False and "not connected" in result["notes"][0]


@needs_tsci
def test_the_users_fix_and_the_ais_final_are_simulated(run, symbols):
    from reflow.learn import sim

    if sim.find_ngspice() is None:
        pytest.skip("ngspice not installed")
    client = _client(run)
    edits = [{"kind": "set_label", "ref": "U1", "pin": n, "value": l} for n, l in DATASHEET.items()] + WIRING
    client.post("/api/fix", json={"edits": edits})
    yours = client.post("/api/sim", json={"concept": "decoupling", "fix": 1}).json()
    assert yours["ran"] and yours["variant"] == "yours" and yours["verdict"] == "good"
    assert yours["signals"][0]["name"] == "V(chip)" and yours["refs"] == ["C1", "U1"]
    pcb = client.post("/api/sim", json={"concept": "decoupling", "fix": 1, "pcb": True}).json()
    assert pcb["ran"] and any("mm" in a for a in pcb["assumptions"])
    i2c = client.post("/api/sim", json={"concept": "i2c-pullup", "fix": 1}).json()
    assert i2c["ran"] and i2c["verdict"] == "good" and "rise time" in i2c["notes"][0]



@needs_tsci
def test_route_status_of_a_fix_comes_from_our_drc(run, symbols):
    from reflow.cli import find_kicad_cli

    if find_kicad_cli() is None:
        pytest.skip("kicad-cli not found")
    client = _client(run)
    edits = [{"kind": "set_label", "ref": "U1", "pin": n, "value": l} for n, l in DATASHEET.items()] + WIRING
    client.post("/api/fix", json={"edits": edits})
    unrouted = client.post("/api/route", json={"fix": 1}).json()
    assert unrouted["status"] == "failed" and unrouted["routed_nets"] == 0
    client.post("/api/fix", json={"edits": edits + [{"kind": "set_trace_limit", "ref": "C1", "value": "3mm"}]})
    routed = client.post("/api/route", json={"fix": 2}).json()
    assert routed["unrouted_nets"] == [] and routed["drc"]["unconnected"] == 0
    pcb = client.post("/api/sim", json={"concept": "decoupling", "fix": 2, "pcb": True}).json()
    assert pcb["ran"] and any("routed trace length" in a for a in pcb["assumptions"])


def test_route_status_needs_a_board_with_a_pcb(run):
    assert _client(run).post("/api/route", json={"attempt": 1}).status_code == 404



@needs_tsci
def test_fixes_made_this_session_are_listed_for_a_reloaded_page(run, symbols):
    client = _client(run)
    assert client.get("/api/fixes").json() == []
    client.post("/api/fix", json={"edits": [{"kind": "set_label", "ref": "U1", "pin": "1", "value": "SDA"}]})
    listed = client.get("/api/fixes").json()
    assert [f["number"] for f in listed] == [1] and listed[0]["edits"][0]["kind"] == "set_label"
