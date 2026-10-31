"""L-01: pick what to teach from a real run, and grade the click (L-2, O-1c).

Inputs are real run folders reduced to what learn mode reads
(tests/data/real_runs/learn_*; see their READMEs). Spot-the-bug comes from the
first failed attempt's violations, never from a question bank.
"""
import json
import shutil
from pathlib import Path

import pytest

from reflow.contracts import LearnInteraction, from_dict, to_dict
from reflow.learn.engine import concept_of, grade, load_run, pick

ROOT = Path(__file__).resolve().parents[1]
FAILED_FIRST = ROOT / "tests" / "data" / "real_runs" / "learn_mcp9808_20261022"
PASSED_FIRST = ROOT / "tests" / "data" / "real_runs" / "learn_at24c02_first_pass_20261022"


def _without_pinout(tmp_path: Path) -> Path:
    """The same run, with attempt 1's pinout errors removed: decoupling and I2C are left."""
    run = tmp_path / "run"
    shutil.copytree(FAILED_FIRST, run)
    verify = run / "attempts" / "01" / "verify.json"
    report = json.loads(verify.read_text(encoding="utf-8"))
    report["violations"] = [v for v in report["violations"] if not v["rule_id"].startswith("pinout.")]
    report["errors"] = len(report["violations"])
    verify.write_text(json.dumps(report), encoding="utf-8")
    return run


def test_the_root_cause_is_taught_and_its_consequences_are_not():
    """Attempt 1 mirrored U1's pinout. Its decoupling and I2C errors follow from the wrong
    labels (one decoupling error is on the real GND pin), so only the pinout is taught."""
    selection = pick(load_run(FAILED_FIRST))
    assert [(p.kind, p.concept, p.rule_id, p.attempt, p.answer_refs) for p in selection.interactions] == [
        ("spot_bug", "pinout", "pinout.mismatch", 1, ["U1"]),
    ]
    assert any("decoupling" in note and "U1" in note for note in selection.notes)
    assert any("i2c" in note for note in selection.notes)


def test_the_prompt_does_not_give_the_answer_away():
    pending = pick(load_run(FAILED_FIRST)).interactions[0]
    assert "U1" not in pending.prompt and "pinout" not in pending.prompt.lower()
    assert pending.hint and "U1" not in pending.hint
    assert pending.why and pending.fix_hint


def test_each_concept_once_and_a_violation_without_refs_is_answered_by_its_net(tmp_path):
    selection = pick(load_run(_without_pinout(tmp_path)))
    assert [(p.concept, p.rule_id, p.answer_refs) for p in selection.interactions] == [
        ("decoupling", "decoupling.missing", ["U1"]),
        ("i2c-pullup", "i2c.missing_pullup", ["C1", "U1"]),  # the parts on Net-(C1-pin1)
    ]
    ids = [p.id for p in selection.interactions]
    assert len(set(ids)) == len(ids)


def test_every_interaction_comes_from_a_real_violation_of_the_run(tmp_path):
    run = load_run(_without_pinout(tmp_path))
    first_failed = next(a for a in run.attempts if a.verify and a.verify.errors)
    real = {(v.rule_id, v.message) for v in first_failed.verify.violations}
    for pending in pick(run).interactions:
        assert (pending.rule_id, pending.message) in real


def test_known_concepts_are_skipped_and_the_skip_is_shown(tmp_path):
    selection = pick(load_run(_without_pinout(tmp_path)), skip={"decoupling"})
    assert [p.concept for p in selection.interactions] == ["i2c-pullup"]
    assert selection.skipped == ["decoupling"]


def test_at_most_limit_interactions(tmp_path):
    assert len(pick(load_run(_without_pinout(tmp_path)), limit=1).interactions) == 1
    with pytest.raises(ValueError):
        pick(load_run(FAILED_FIRST), limit=0)


def test_a_first_draft_that_passed_has_no_bug_to_spot():
    selection = pick(load_run(PASSED_FIRST))
    assert selection.interactions == []
    assert "passed" in selection.reason


def test_the_failed_draft_and_the_final_board_are_both_found():
    run = load_run(FAILED_FIRST)
    assert [a.number for a in run.attempts] == [1, 2]
    assert run.best_attempt == 2
    for attempt in run.attempts:
        assert attempt.circuit_json.is_file()
        assert attempt.circuit_json.is_relative_to(FAILED_FIRST)


# ---------------------------------------------------------------------------
# grading: by the part clicked; wrong answers teach, never block
# ---------------------------------------------------------------------------

def _pending():
    return pick(load_run(FAILED_FIRST)).interactions[0]


def test_the_right_part_first_time_is_good():
    result = grade(_pending(), "U1", "the pin labels don't match the datasheet", tries=1, hinted=False)
    assert (result.outcome, result.rating) == ("correct", "good")
    record = result.interaction
    assert record.correct is True and record.kind == "spot_bug" and record.rule_id == "pinout.mismatch"
    assert record.user_answer == "U1: the pin labels don't match the datasheet"
    assert record.explanation == _pending().why
    assert from_dict(LearnInteraction, json.loads(json.dumps(to_dict(record)))) == record


def test_a_wrong_first_click_gets_the_hint_and_one_more_try():
    pending = _pending()
    first = grade(pending, "C1", "", tries=1, hinted=False)
    assert first.outcome == "try_again" and first.interaction is None and first.hint == pending.hint
    second = grade(pending, "U1", "pinout", tries=2, hinted=True)
    assert (second.outcome, second.rating, second.interaction.correct) == ("correct", "hard", True)


def test_wrong_twice_shows_the_answer_and_moves_on():
    result = grade(_pending(), "R1", "no idea", tries=2, hinted=True)
    assert (result.outcome, result.rating) == ("wrong", "again")
    assert result.interaction.correct is False
    assert result.answer_refs == ["U1"] and result.why and result.fix_hint


def test_asking_for_the_hint_then_getting_it_right_is_hard():
    assert grade(_pending(), "U1", "", tries=1, hinted=True).rating == "hard"


def test_a_click_is_matched_without_caring_about_case_or_spaces():
    assert grade(_pending(), " u1 ", "", tries=1, hinted=False).outcome == "correct"


def test_concepts_come_from_the_rule_id():
    assert concept_of("decoupling.missing") == concept_of("decoupling.series") == "decoupling"
    assert concept_of("i2c.missing_pullup") == concept_of("i2c.duplicate_pullup") == "i2c-pullup"
    assert concept_of("address.floating") == "address-strap"
    assert concept_of("pinout.mismatch") == "pinout"
    assert concept_of("project.cap") == "project-cap"
