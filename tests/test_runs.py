"""H-05: run-folder I/O. Failing test first.

The writer persists contract objects under runs/<id>/ exactly as docs/02
describes. It does not resume, pick a best attempt, or turn model text
into a part number.
"""
import dataclasses
import json
import os
from pathlib import Path

import pytest

from reflow import contracts as c
from reflow.harness.runs import RunExistsError, create_run

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "docs" / "examples"

SNEAKY_LCSC = "C99999"
SNEAKY_MPN = "ZZ-FAKE-1"
SNEAKY_TSX_LCSC = "C1234567"


def example(name, cls):
    return c.from_dict(cls, json.loads((EXAMPLES / name).read_text(encoding="utf-8")))


def files_under(root: Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


def read_run(store):
    return c.from_dict(c.RunResult, json.loads((store.path / "run.json").read_text(encoding="utf-8")))


def step(run, tokens):
    return dataclasses.replace(run, input_tokens=tokens)


@pytest.fixture
def run():
    base = example("run_result.json", c.RunResult)
    # A value the writer must not "correct". Choosing the best attempt is not this module.
    return dataclasses.replace(base, status="aborted", attempts=[], best_attempt=7, input_tokens=0, output_tokens=0)


def test_layout_files_parse_and_run_json_tracks_each_step(tmp_path, run):
    spec = example("spec.json", c.Spec)
    plan = example("plan.json", c.Plan)
    parts = example("resolved_parts.json", c.ResolvedParts)
    code = example("generated_code.json", c.GeneratedCode)
    compile_fail = example("compile_result.json", c.CompileResult)
    compile_ok = c.CompileResult(
        ok=True, errors=[], stderr_tail="", kicad_sch="board.kicad_sch",
        kicad_pcb="board.kicad_pcb", circuit_json="circuit.json",
    )
    report = example("verify_report.json", c.VerifyReport)
    feedback = example("retry_feedback.json", c.RetryFeedback)
    prompt = "exactly the prompt\nline 2\n"
    response = f"model said {SNEAKY_MPN} and {SNEAKY_LCSC}\n"

    run_dir = tmp_path / "runs" / run.run_id
    store = create_run(run_dir, run)
    assert store.path == run_dir
    assert read_run(store) == run

    store.write_spec(spec, step(run, 1))
    assert c.from_dict(c.Spec, json.loads((run_dir / "spec.json").read_text(encoding="utf-8"))) == spec
    assert read_run(store).input_tokens == 1

    store.write_plan(plan, step(run, 2))
    assert c.from_dict(c.Plan, json.loads((run_dir / "plan.json").read_text(encoding="utf-8"))) == plan
    assert read_run(store).input_tokens == 2

    store.write_parts(parts, step(run, 3))
    assert c.from_dict(c.ResolvedParts, json.loads((run_dir / "parts.json").read_text(encoding="utf-8"))) == parts
    assert read_run(store).input_tokens == 3

    store.write_prompt(1, prompt, step(run, 4))
    assert (run_dir / "attempts" / "01" / "prompt.md").read_text(encoding="utf-8") == prompt
    assert read_run(store).input_tokens == 4

    store.write_response(1, response, step(run, 5))
    assert (run_dir / "attempts" / "01" / "response.md").read_text(encoding="utf-8") == response
    assert read_run(store).input_tokens == 5

    store.write_tsx(1, code, step(run, 6))
    assert (run_dir / "attempts" / "01" / "index.circuit.tsx").read_text(encoding="utf-8") == code.tsx
    assert read_run(store).input_tokens == 6

    store.write_compile(1, 1, compile_fail, step(run, 7))
    assert c.from_dict(
        c.CompileResult,
        json.loads((run_dir / "attempts" / "01" / "compile-1.json").read_text(encoding="utf-8")),
    ) == compile_fail
    assert read_run(store).input_tokens == 7

    store.write_compile(1, 2, compile_ok, step(run, 8))
    assert c.from_dict(
        c.CompileResult,
        json.loads((run_dir / "attempts" / "01" / "compile-2.json").read_text(encoding="utf-8")),
    ) == compile_ok
    # the earlier compile try is still there
    assert (run_dir / "attempts" / "01" / "compile-1.json").is_file()
    assert read_run(store).input_tokens == 8

    store.write_verify(1, report, step(run, 9))
    verify = json.loads((run_dir / "attempts" / "01" / "verify.json").read_text(encoding="utf-8"))
    assert c.from_dict(c.VerifyReport, verify) == report
    assert verify["violations"][0]["why"] == report.violations[0].why
    assert read_run(store).input_tokens == 9

    store.write_feedback(1, feedback, step(run, 10))
    feedback_on_disk = json.loads((run_dir / "attempts" / "01" / "feedback.json").read_text(encoding="utf-8"))
    assert c.from_dict(c.RetryFeedback, feedback_on_disk) == feedback
    assert "why" not in json.dumps(feedback_on_disk)
    assert read_run(store).input_tokens == 10

    # Caller-supplied attempt record, including a nonsense error count. Not derived here.
    record = c.AttemptRecord(
        attempt=1, compile_tries=2, compiled=True, errors=99, warnings=5,
        rule_ids=["not.a.real.rule"], dir="runs/example/attempts/01",
    )
    final = dataclasses.replace(step(run, 11), attempts=[record], output_tokens=4)
    store.write_prompt(2, "attempt two prompt\n", final)

    loaded = read_run(store)
    assert loaded == final
    assert loaded.best_attempt == 7
    assert loaded.status == "aborted"
    assert loaded.attempts[0].errors == 99
    assert loaded.run_dir == run.run_dir

    assert files_under(run_dir) == [
        "attempts/01/compile-1.json",
        "attempts/01/compile-2.json",
        "attempts/01/feedback.json",
        "attempts/01/index.circuit.tsx",
        "attempts/01/prompt.md",
        "attempts/01/response.md",
        "attempts/01/verify.json",
        "attempts/02/prompt.md",
        "parts.json",
        "plan.json",
        "run.json",
        "spec.json",
    ]
    # nothing else landed beside the run folder
    assert files_under(tmp_path) == [f"runs/{run.run_id}/{rel}" for rel in files_under(run_dir)]


def test_model_text_is_not_turned_into_part_ids(tmp_path, run):
    parts = example("resolved_parts.json", c.ResolvedParts)
    code = example("generated_code.json", c.GeneratedCode)
    code = dataclasses.replace(
        code,
        tsx=code.tsx + f'\nconst sneak = "{SNEAKY_TSX_LCSC}"; // {SNEAKY_MPN}\n',
    )
    response = f"please buy {SNEAKY_MPN} lcsc {SNEAKY_LCSC}\n"

    store = create_run(tmp_path / "runs" / "sneak", run)
    store.write_response(1, response, run)
    store.write_tsx(1, code, run)
    store.write_parts(parts, run)

    parts_text = (store.path / "parts.json").read_text(encoding="utf-8")
    spec_absent = store.path / "spec.json"
    assert SNEAKY_LCSC not in parts_text
    assert SNEAKY_MPN not in parts_text
    assert SNEAKY_TSX_LCSC not in parts_text
    assert not spec_absent.exists()
    assert (store.path / "attempts" / "01" / "response.md").read_text(encoding="utf-8") == response
    assert (store.path / "attempts" / "01" / "index.circuit.tsx").read_text(encoding="utf-8") == code.tsx
    assert c.from_dict(c.ResolvedParts, json.loads(parts_text)) == parts


def test_failed_replace_leaves_new_file_absent(tmp_path, run, monkeypatch):
    spec = example("spec.json", c.Spec)
    plan = example("plan.json", c.Plan)
    store = create_run(tmp_path / "runs" / "kill", run)
    store.write_spec(spec, step(run, 1))

    def killed(src, dst):
        raise OSError("killed before replace")

    monkeypatch.setattr(os, "replace", killed)
    with pytest.raises(OSError, match="killed before replace"):
        store.write_plan(plan, step(run, 2))

    assert not (store.path / "plan.json").exists()
    assert c.from_dict(c.Spec, json.loads((store.path / "spec.json").read_text(encoding="utf-8"))) == spec
    assert read_run(store) == step(run, 1)
    assert files_under(store.path) == ["run.json", "spec.json"]


def test_failed_run_json_replace_keeps_the_previous_snapshot(tmp_path, run, monkeypatch):
    spec = example("spec.json", c.Spec)
    store = create_run(tmp_path / "runs" / "between", run)
    real = os.replace

    def fail_run_json(src, dst):
        if Path(dst).name == "run.json":
            raise OSError("killed before run.json replace")
        return real(src, dst)

    monkeypatch.setattr(os, "replace", fail_run_json)
    with pytest.raises(OSError, match="killed before run.json replace"):
        store.write_spec(spec, step(run, 1))

    assert c.from_dict(c.Spec, json.loads((store.path / "spec.json").read_text(encoding="utf-8"))) == spec
    assert read_run(store) == run
    assert files_under(store.path) == ["run.json", "spec.json"]


def test_writes_use_a_temp_file_then_replace_in_the_same_directory(tmp_path, run, monkeypatch):
    seen = []
    real = os.replace

    def spy(src, dst):
        src, dst = Path(src), Path(dst)
        assert src.parent == dst.parent
        assert src.name != dst.name
        assert src.name.startswith(".")
        seen.append(dst.name)
        return real(src, dst)

    monkeypatch.setattr(os, "replace", spy)
    store = create_run(tmp_path / "runs" / "atomic", run)
    store.write_spec(example("spec.json", c.Spec), step(run, 1))
    assert seen == ["run.json", "spec.json", "run.json"]


def test_create_refuses_an_existing_run_and_there_is_no_resume(tmp_path, run):
    store = create_run(tmp_path / "runs" / "once", run)
    with pytest.raises(RunExistsError):
        create_run(store.path, run)

    import reflow.harness.runs as runs

    public = [name for name in dir(runs) if not name.startswith("_")]
    assert "resume" not in {name.lower() for name in public}
    assert "pick_best" not in public
    assert "should_stop" not in public
    for banned in ("pick_best", "should_stop", "to_feedback"):
        assert banned not in Path(runs.__file__).read_text(encoding="utf-8")


def test_create_failure_leaves_run_json_absent(tmp_path, run, monkeypatch):
    def killed(src, dst):
        raise OSError("killed before replace")

    monkeypatch.setattr(os, "replace", killed)
    run_dir = tmp_path / "runs" / "never"
    with pytest.raises(OSError, match="killed before replace"):
        create_run(run_dir, run)
    assert not (run_dir / "run.json").exists()
    assert files_under(run_dir) == []

    monkeypatch.undo()
    store = create_run(run_dir, run)
    assert read_run(store) == run


def test_rejects_wrong_types_and_bad_attempt_numbers(tmp_path, run):
    store = create_run(tmp_path / "runs" / "types", run)
    with pytest.raises(TypeError):
        store.write_spec({"title": "nope"}, run)
    with pytest.raises(TypeError):
        store.write_prompt(1, b"bytes", run)
    with pytest.raises(ValueError):
        store.write_prompt(0, "x", run)
    with pytest.raises(ValueError):
        store.write_prompt(True, "x", run)  # bool is an int subclass
    with pytest.raises(ValueError):
        store.write_compile(1, 0, example("compile_result.json", c.CompileResult), run)
    assert files_under(store.path) == ["run.json"]
