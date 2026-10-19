"""H-06 / H-07: spec checkpoint and `reflow design` plumbing.

Pure Python. No KiCad, no network, no model call, no design loop.
The scripted fake-model run stays parked until H-03 exists.
"""
import json
from pathlib import Path

import pytest

from reflow.checkpoint import (
    CheckpointError,
    load_plan,
    load_spec,
    reject_foreign_mpn,
    require_confirmed,
)
from reflow.cli import main
from reflow.contracts import ContractError, Plan, Spec, from_dict

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "docs" / "examples"


def _write(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _spec_data() -> dict:
    return json.loads((EXAMPLES / "spec.json").read_text(encoding="utf-8"))


def _plan_data() -> dict:
    return json.loads((EXAMPLES / "plan.json").read_text(encoding="utf-8"))


def test_design_help_exits_zero(capsys):
    assert main(["design", "--help"]) == 0
    out = capsys.readouterr().out
    assert "--spec" in out
    assert "--plan" in out


def test_check_help_still_exits_zero(capsys):
    assert main(["check", "--help"]) == 0
    out = capsys.readouterr().out
    assert "kicad" in out.lower()


def test_load_spec_round_trips_through_from_dict(tmp_path):
    data = _spec_data()
    loaded = load_spec(_write(tmp_path / "spec.json", data))
    assert loaded == from_dict(Spec, data)
    assert loaded == from_dict(Spec, json.loads(json.dumps({
        "request": loaded.request,
        "title": loaded.title,
        "power": loaded.power,
        "interfaces": loaded.interfaces,
        "constraints": loaded.constraints,
        "named_parts": loaded.named_parts,
        "open_questions": [
            {"id": q.id, "question": q.question, "answer": q.answer}
            for q in loaded.open_questions
        ],
        "confirmed": loaded.confirmed,
    })))
    assert loaded.confirmed is True
    assert loaded.named_parts == ["MCP9808"]


def test_load_spec_rejects_unknown_field(tmp_path):
    data = _spec_data()
    data["lcsc"] = "C25744"
    path = _write(tmp_path / "spec.json", data)
    with pytest.raises(ContractError, match="unknown field"):
        load_spec(path)


def test_confirmed_spec_calls_injected_codegen(tmp_path, capsys):
    path = _write(tmp_path / "spec.json", _spec_data())
    seen = []
    code = main(
        ["design", "--spec", str(path)],
        codegen=lambda spec, plan: seen.append((spec, plan)),
    )
    out, err = capsys.readouterr()
    assert code == 0
    assert err == ""
    assert len(seen) == 1
    spec, plan = seen[0]
    assert spec == from_dict(Spec, _spec_data())
    assert plan is None
    assert "AI-designed" not in out
    assert "routed" not in out.lower()


def test_unconfirmed_spec_exits_2_and_skips_codegen(tmp_path, capsys):
    data = _spec_data()
    data["confirmed"] = False
    spec_path = _write(tmp_path / "spec.json", data)
    plan_path = tmp_path / "no-such-plan.json"
    seen = []
    code = main(
        ["design", "--spec", str(spec_path), "--plan", str(plan_path)],
        codegen=lambda spec, plan: seen.append((spec, plan)),
    )
    _out, err = capsys.readouterr()
    assert code == 2
    assert seen == []
    assert "confirm" in err.lower()
    assert "no-such-plan" not in err
    with pytest.raises(CheckpointError, match="confirm"):
        require_confirmed(from_dict(Spec, data))


def test_request_without_spec_does_not_call_codegen(capsys):
    seen = []
    code = main(
        ["design", "MCP9808 breakout, I2C header, 3.3V"],
        codegen=lambda spec, plan: seen.append((spec, plan)),
    )
    _out, err = capsys.readouterr()
    assert code == 2
    assert seen == []
    assert "--spec" in err


def test_matching_request_is_accepted(tmp_path):
    data = _spec_data()
    path = _write(tmp_path / "spec.json", data)
    seen = []
    code = main(
        ["design", data["request"], "--spec", str(path)],
        codegen=lambda spec, plan: seen.append(spec.request),
    )
    assert code == 0
    assert seen == [data["request"]]


def test_request_must_match_spec(tmp_path, capsys):
    path = _write(tmp_path / "spec.json", _spec_data())
    seen = []
    code = main(
        ["design", "a different board", "--spec", str(path)],
        codegen=lambda spec, plan: seen.append((spec, plan)),
    )
    assert code == 2
    assert seen == []
    assert "Spec.request" in capsys.readouterr().err


def test_plan_mpn_outside_named_parts_fails(tmp_path, capsys):
    spec = from_dict(Spec, _spec_data())
    plan_data = _plan_data()
    plan_data["parts"].append({
        "id": "p9",
        "role": "invented regulator",
        "category": "regulator",
        "mpn": "AMS1117-3.3",
        "notes": "also C25744 must stay a note",
    })
    plan = from_dict(Plan, plan_data)
    named_before = list(spec.named_parts)
    mpns_before = [part.mpn for part in plan.parts]
    try:
        reject_foreign_mpn(plan, spec)
    except CheckpointError as exc:
        message = str(exc)
    else:
        raise AssertionError("foreign mpn was accepted")
    assert "AMS1117-3.3" in message
    assert spec.named_parts == named_before
    assert [part.mpn for part in plan.parts] == mpns_before
    assert plan.parts[-1].notes.startswith("also C25744")
    assert not hasattr(plan.parts[-1], "lcsc")

    spec_path = _write(tmp_path / "spec.json", _spec_data())
    plan_path = _write(tmp_path / "plan.json", plan_data)
    seen = []
    code = main(
        ["design", "--spec", str(spec_path), "--plan", str(plan_path)],
        codegen=lambda spec, plan: seen.append((spec, plan)),
    )
    assert code == 2
    assert seen == []
    assert "AMS1117-3.3" in capsys.readouterr().err


def test_named_part_mpn_is_allowed(tmp_path):
    spec = load_spec(_write(tmp_path / "spec.json", _spec_data()))
    plan = load_plan(_write(tmp_path / "plan.json", _plan_data()))
    assert plan == from_dict(Plan, _plan_data())
    reject_foreign_mpn(plan, spec)
    assert plan.parts[0].mpn == "MCP9808"
    assert all(part.mpn == "" or part.mpn in spec.named_parts for part in plan.parts)


def test_mpn_match_is_exact(tmp_path, capsys):
    spec = from_dict(Spec, _spec_data())
    plan_data = _plan_data()
    plan_data["parts"][0]["mpn"] = "mcp9808"
    plan = from_dict(Plan, plan_data)
    try:
        reject_foreign_mpn(plan, spec)
    except CheckpointError as exc:
        assert "mcp9808" in str(exc)
    else:
        raise AssertionError("case-shifted mpn was accepted")

    spec_path = _write(tmp_path / "spec.json", _spec_data())
    plan_path = _write(tmp_path / "plan.json", plan_data)
    seen = []
    code = main(
        ["design", "--spec", str(spec_path), "--plan", str(plan_path)],
        codegen=lambda *args: seen.append(args),
    )
    assert code == 2
    assert seen == []


def test_legal_plan_reaches_codegen_with_parsed_plan(tmp_path, capsys):
    spec_path = _write(tmp_path / "spec.json", _spec_data())
    plan_path = _write(tmp_path / "plan.json", _plan_data())
    seen = []
    code = main(
        ["design", "--spec", str(spec_path), "--plan", str(plan_path)],
        codegen=lambda spec, plan: seen.append((spec, plan)),
    )
    out, err = capsys.readouterr()
    assert code == 0
    assert err == ""
    assert "AI-designed" not in out
    spec, plan = seen[0]
    assert spec.confirmed is True
    assert plan == from_dict(Plan, _plan_data())


def test_bad_plan_json_exits_2(tmp_path, capsys):
    spec_path = _write(tmp_path / "spec.json", _spec_data())
    plan_path = tmp_path / "plan.json"
    plan_path.write_text("{", encoding="utf-8")
    seen = []
    code = main(
        ["design", "--spec", str(spec_path), "--plan", str(plan_path)],
        codegen=lambda *args: seen.append(args),
    )
    assert code == 2
    assert seen == []
    assert capsys.readouterr().err


def test_design_without_codegen_does_not_claim_a_board(tmp_path, capsys):
    path = _write(tmp_path / "spec.json", _spec_data())
    code = main(["design", "--spec", str(path)])
    out, err = capsys.readouterr()
    assert code == 0
    assert err == ""
    assert "H-03" in out
    assert "AI-designed" not in out
    assert "routed" not in out.lower()
