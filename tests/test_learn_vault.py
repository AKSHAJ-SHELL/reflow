"""L-11: concept cards (fsrs), skip logic and the Obsidian-compatible vault (DECISIONS L-2).

Cards and notes go to a temporary vault; time is passed in, so recall is exact.
Needs the optional `[learn]` extra (fsrs); without it these tests skip.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

pytest.importorskip("fsrs")

from reflow.contracts import ConceptCard, VaultNote, from_dict  # noqa: E402
from reflow.learn.vault import KNOWN_RECALL, Vault  # noqa: E402

T0 = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)


def _vault(tmp_path: Path, when=T0) -> Vault:
    return Vault(tmp_path / "vault", now=lambda: when)


def test_a_concept_never_seen_has_no_recall_and_is_not_known(tmp_path):
    vault = _vault(tmp_path)
    assert vault.recall("decoupling") == 0.0
    assert vault.known(["decoupling", "pinout"]) == set()


def test_a_good_answer_makes_the_concept_known_the_next_day(tmp_path):
    _vault(tmp_path).review("pinout", "good", rule_id="pinout.mismatch", why="Labels decide which pin a trace reaches.")
    later = _vault(tmp_path, T0 + timedelta(days=1))
    assert later.recall("pinout") > KNOWN_RECALL == 0.9
    assert later.known(["pinout", "decoupling"]) == {"pinout"}


def test_again_keeps_the_concept_asked(tmp_path):
    _vault(tmp_path).review("pinout", "again", rule_id="pinout.mismatch", why="w")
    assert _vault(tmp_path, T0 + timedelta(days=1)).known(["pinout"]) == set()


def test_the_card_is_a_strict_concept_card_in_the_concept_notes_frontmatter(tmp_path):
    _vault(tmp_path).review("i2c-pullup", "hard", rule_id="i2c.missing_pullup", why="Open-drain lines need a pull-up.")
    note = tmp_path / "vault" / "concepts" / "i2c-pullup.md"
    text = note.read_text(encoding="utf-8")
    assert text.startswith("---\n") and "\n---\n" in text
    card = _vault(tmp_path).card("i2c-pullup")
    assert from_dict(ConceptCard, json.loads(json.dumps(card.__dict__))) == card
    assert card.ratings == ["2026-10-22T12:00:00Z hard"]
    assert card.last_reviewed == "2026-10-22T12:00:00Z"
    assert json.loads(card.fsrs)["stability"] > 0
    assert "Open-drain lines need a pull-up." in text and "`i2c.missing_pullup`" in text


def test_the_users_own_notes_survive_a_rewrite(tmp_path):
    vault = _vault(tmp_path)
    vault.review("pinout", "good", rule_id="pinout.mismatch", why="w")
    note = tmp_path / "vault" / "concepts" / "pinout.md"
    note.write_text(note.read_text(encoding="utf-8") + "Check the MSOP column, not SOIC.\n", encoding="utf-8")
    vault.review("pinout", "hard", rule_id="pinout.mismatch", why="w")
    text = note.read_text(encoding="utf-8")
    assert "## My notes" in text and "Check the MSOP column, not SOIC." in text
    assert len(vault.card("pinout").ratings) == 2


def test_a_mistake_and_a_board_link_to_their_concept(tmp_path):
    vault = _vault(tmp_path)
    vault.review("pinout", "again", rule_id="pinout.mismatch", why="Labels decide which pin a trace reaches.")
    mistake = vault.write_mistake(
        board="MCP9808 breakout", concept="pinout", rule_id="pinout.mismatch",
        found="U1 pin 1 is labelled VDD, but the pin map says SDA", answer="R1: no idea", right_refs=["U1"],
        correct=False, why="Labels decide which pin a trace reaches.", fix="Set pin1: \"SDA\".",
    )
    board = vault.write_board(
        board="MCP9808 breakout", request="MCP9808 breakout, I2C header, 3.3V", run_dir="/runs/x", status="passed",
        parts=["U1 MCP9808T-E/MS (C129490)"], concepts=["pinout"], mistakes=[mistake.path], signed_off=None,
    )
    assert mistake.path == "mistakes/2026-10-22-mcp9808-breakout-pinout.md" and mistake.kind == "mistake"
    assert set(mistake.links) == {"concepts/pinout", "boards/mcp9808-breakout"}
    assert board.path == "boards/mcp9808-breakout.md" and "concepts/pinout" in board.links
    concept = (tmp_path / "vault" / "concepts" / "pinout.md").read_text(encoding="utf-8")
    assert "[[mistakes/2026-10-22-mcp9808-breakout-pinout]]" in concept
    assert "[[boards/mcp9808-breakout]]" in concept
    for note in (mistake, board):
        assert from_dict(VaultNote, json.loads(json.dumps(note.__dict__))) == note


def test_a_second_mistake_on_the_same_day_gets_its_own_note(tmp_path):
    vault = _vault(tmp_path)
    kw = dict(board="B", concept="pinout", rule_id="pinout.mismatch", found="f", answer="a", right_refs=["U1"],
              correct=True, why="w", fix="x")
    assert vault.write_mistake(**kw).path != vault.write_mistake(**kw).path


def test_the_graph_has_every_note_and_its_links(tmp_path):
    vault = _vault(tmp_path)
    vault.review("pinout", "good", rule_id="pinout.mismatch", why="w")
    mistake = vault.write_mistake(board="B", concept="pinout", rule_id="pinout.mismatch", found="f", answer="a",
                                  right_refs=["U1"], correct=True, why="w", fix="x")
    vault.write_board(board="B", request="r", run_dir="d", status="passed", parts=[], concepts=["pinout"],
                      mistakes=[mistake.path], signed_off=True)
    graph = vault.graph()
    ids = {n["id"]: n["kind"] for n in graph["nodes"]}
    assert ids == {"concepts/pinout": "concept", mistake.path[:-3]: "mistake", "boards/b": "board"}
    pairs = {(l["source"], l["target"]) for l in graph["links"]}
    assert ("boards/b", "concepts/pinout") in pairs and (mistake.path[:-3], "concepts/pinout") in pairs
    assert all(n["obsidian"].startswith("obsidian://open?path=") for n in graph["nodes"])


def test_the_vault_location_comes_from_reflow_vault(monkeypatch, tmp_path):
    from reflow.learn.vault import default_vault_dir

    monkeypatch.setenv("REFLOW_VAULT", str(tmp_path / "v"))
    assert default_vault_dir() == tmp_path / "v"
    monkeypatch.delenv("REFLOW_VAULT")
    assert default_vault_dir() == Path.home() / ".reflow" / "vault"
