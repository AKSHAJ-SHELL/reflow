"""H-01..H-04: feedback conversion, the design loop, and termination.

Fakes stand in for the model, the compiler, and the verifier. No network,
no KiCad, no SDK.
"""
import json
from pathlib import Path

import pytest

from reflow.contracts import (
    CompileError,
    CompileResult,
    Plan,
    ResolvedPart,
    ResolvedParts,
    RetryFeedback,
    RunResult,
    Spec,
    Unresolved,
    VerifyReport,
    from_dict,
    to_dict,
)
from reflow.llm import Completion
from reflow.violation import Violation

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "docs" / "examples"


def _spec(**overrides) -> Spec:
    data = json.loads((EXAMPLES / "spec.json").read_text(encoding="utf-8"))
    data.update(overrides)
    return from_dict(Spec, data)


def _plan() -> Plan:
    return from_dict(Plan, json.loads((EXAMPLES / "plan.json").read_text(encoding="utf-8")))


def _part() -> ResolvedPart:
    return ResolvedPart(
        request_id="p1",
        lcsc="C12345",
        mpn="MCP9808",
        manufacturer="Microchip",
        package="soic8",
        value="",
        stock=100,
        basic=True,
        unit_price_usd=0.5,
        source="jlcsearch",
        fetched_at="2026-10-19T00:00:00Z",
    )


def _parts(*, unresolved: list[Unresolved] | None = None) -> ResolvedParts:
    return ResolvedParts(resolved=[_part()], unresolved=list(unresolved or []))


def _violation(
    rule_id: str,
    refs: list[str],
    *,
    nets: list[str] | None = None,
    message: str = "bad connection",
    fix_hint: str = "rewire it",
    severity: str = "error",
    why: str = "SECRET_WHY_NOT_FOR_THE_MODEL",
) -> Violation:
    return Violation(rule_id, severity, message, why, fix_hint, list(refs), list(nets or ["GND"]))


def _report(errors: int, warnings: int, violations: list[Violation]) -> VerifyReport:
    return VerifyReport("board.kicad_sch", 3, 4, errors, warnings, violations)


def _fence(body: str) -> str:
    return f"```tsx\n{body}\n```"


def _ok_compile(workdir: Path) -> CompileResult:
    sch = workdir / "board.kicad_sch"
    pcb = workdir / "board.kicad_pcb"
    sch.write_text("KICAD_SCH_BODY_SECRET\n", encoding="utf-8")
    pcb.write_text("KICAD_PCB_BODY_SECRET\n", encoding="utf-8")
    return CompileResult(True, [], "", str(sch), str(pcb), "circuit.json")


def _bad_compile() -> CompileResult:
    return CompileResult(
        False,
        [
            CompileError("first compile error", 3, 1),
            CompileError("SECOND_COMPILE_ERROR_NOT_FOR_THE_MODEL", 9, 1),
        ],
        "STDERR_TAIL_SECRET",
        "",
        "",
        "",
    )


class FakeModel:
    def __init__(self, replies: list[str]):
        self.replies = list(replies)
        self.prompts: list[str] = []
        self.systems: list[str] = []

    def complete(self, system: str, prompt: str, *, max_tokens: int = 4096) -> Completion:
        self.systems.append(system)
        self.prompts.append(prompt)
        if not self.replies:
            raise AssertionError("fake model ran out of replies")
        return Completion(
            text=self.replies.pop(0),
            model="fake/model",
            input_tokens=11,
            output_tokens=7,
        )


class FakeCompiler:
    """Each entry is True (write dummy KiCad paths) or False (syntax errors)."""

    def __init__(self, results: list[bool]):
        self.results = list(results)
        self.calls: list[str] = []

    def __call__(self, tsx: str, workdir: Path) -> CompileResult:
        self.calls.append(tsx)
        if not self.results:
            raise AssertionError("fake compiler ran out of results")
        ok = self.results.pop(0)
        workdir.mkdir(parents=True, exist_ok=True)
        if ok:
            return _ok_compile(workdir)
        return _bad_compile()


class FakeVerifier:
    def __init__(self, reports: list[VerifyReport]):
        self.reports = list(reports)
        self.calls: list[str] = []

    def __call__(self, schematic: str, parts: ResolvedParts, spec: Spec) -> VerifyReport:
        self.calls.append(schematic)
        if not self.reports:
            raise AssertionError("fake verifier ran out of reports")
        report = self.reports.pop(0)
        # Reading the schematic would leak into a prompt only if the loop did it.
        if schematic and Path(schematic).is_file():
            self.last_body = Path(schematic).read_text(encoding="utf-8")
        return report


def _run(tmp_path, model, compiler, verifier, **kwargs):
    from reflow.harness.loop import run_design

    spec = kwargs.pop("spec", _spec())
    plan = kwargs.pop("plan", _plan())
    parts = kwargs.pop("parts", _parts())
    return run_design(
        spec,
        plan,
        parts,
        model=model,
        compiler=compiler,
        verifier=verifier,
        run_dir=tmp_path / "run",
        **kwargs,
    )


def _read_run(tmp_path) -> RunResult:
    data = json.loads((tmp_path / "run" / "run.json").read_text(encoding="utf-8"))
    return from_dict(RunResult, data)


def test_signatures_use_contract_types():
    import typing

    from reflow.harness.feedback import render_feedback, to_feedback
    from reflow.harness.loop import pick_best, run_design
    from reflow.contracts import AttemptRecord, CompileResult, VerifyReport

    feedback_hints = typing.get_type_hints(to_feedback)
    assert RetryFeedback in (feedback_hints["return"],)
    source = feedback_hints["source"]
    assert set(typing.get_args(source)) == {VerifyReport, CompileResult}

    render_hints = typing.get_type_hints(render_feedback)
    assert render_hints["feedback"] is RetryFeedback
    assert render_hints["return"] is str

    hints = typing.get_type_hints(run_design)
    assert hints["spec"] is Spec
    assert set(typing.get_args(hints["plan"])) == {Plan, type(None)}
    assert hints["parts"] is ResolvedParts
    assert hints["return"] is RunResult

    best_hints = typing.get_type_hints(pick_best)
    assert typing.get_args(best_hints["attempts"])[0] is AttemptRecord
    assert best_hints["return"] is int


def test_verify_feedback_drops_why_and_copies_fields():
    from reflow.harness.feedback import render_feedback, to_feedback

    violation = _violation(
        "decoupling.series",
        ["C1", "U1"],
        nets=["+3V3", "GND"],
        message="C1 sits in series",
        fix_hint="put C1 from +3V3 to GND",
    )
    report = _report(1, 0, [violation])
    feedback = to_feedback(report, attempt=1, max_attempts=3, history=[])
    parsed = from_dict(RetryFeedback, to_dict(feedback))
    assert parsed.kind == "verify"
    assert parsed.violations[0].rule_id == "decoupling.series"
    assert parsed.violations[0].message == "C1 sits in series"
    assert parsed.violations[0].fix_hint == "put C1 from +3V3 to GND"
    assert parsed.violations[0].refs == ["C1", "U1"]
    assert parsed.violations[0].nets == ["+3V3", "GND"]
    blob = json.dumps(to_dict(parsed))
    assert "why" not in blob
    assert "SECRET_WHY" not in blob

    text = render_feedback(parsed, tsx="export const MARKER = 1\n")
    assert "SECRET_WHY_NOT_FOR_THE_MODEL" not in text
    assert "decoupling.series" in text
    assert "C1 sits in series" in text
    assert "put C1 from +3V3 to GND" in text
    assert "C1" in text and "U1" in text
    assert "+3V3" in text
    assert ".kicad_sch" not in text
    assert ".kicad_pcb" not in text
    assert "rule_id:" in text and "fix_hint:" in text
    assert len(text) < 8000


def test_compile_feedback_keeps_the_first_error_and_skips_kicad_bodies(tmp_path):
    from reflow.harness.feedback import render_feedback, to_feedback

    sch = tmp_path / "board.kicad_sch"
    pcb = tmp_path / "board.kicad_pcb"
    sch.write_text("KICAD_SCH_BODY_SECRET\n", encoding="utf-8")
    pcb.write_text("KICAD_PCB_BODY_SECRET\n", encoding="utf-8")
    result = CompileResult(
        False,
        [
            CompileError("first compile error", 4, 2, "index.circuit.tsx"),
            CompileError("SECOND_COMPILE_ERROR_NOT_FOR_THE_MODEL", 8, 1),
        ],
        "STDERR_TAIL_SECRET",
        str(sch),
        str(pcb),
        "circuit.json",
    )
    feedback = to_feedback(result, attempt=1, max_attempts=3, history=["attempt 0: none"])
    parsed = from_dict(RetryFeedback, to_dict(feedback))
    assert parsed.kind == "compile"
    assert len(parsed.compile_errors) == 1
    assert parsed.compile_errors[0].message == "first compile error"
    assert parsed.violations == []
    text = render_feedback(parsed, tsx="export const MARKER = 1\n")
    assert "first compile error" in text
    assert "SECOND_COMPILE_ERROR_NOT_FOR_THE_MODEL" not in text
    assert "STDERR_TAIL_SECRET" not in text
    assert "KICAD_SCH_BODY_SECRET" not in text
    assert "KICAD_PCB_BODY_SECRET" not in text
    assert ".kicad_sch" not in text
    assert ".kicad_pcb" not in text
    assert "why" not in text


def test_rendered_rule_block_repeats_once_per_violation():
    from reflow.harness.feedback import render_feedback, to_feedback

    report = _report(2, 0, [
        _violation("decoupling.series", ["C1"], message="series cap"),
        _violation("i2c.missing_pullup", ["SDA"], message="missing pullup"),
    ])
    feedback = to_feedback(report, attempt=2, max_attempts=3, history=["attempt 1: decoupling.series C1"])
    text = render_feedback(feedback, tsx="file")
    assert text.count("rule_id:") == 2
    assert "decoupling.series" in text and "i2c.missing_pullup" in text
    assert "attempt 1: decoupling.series C1" in text


def test_passes_on_attempt_2_and_keeps_attempt_1(tmp_path):
    model = FakeModel([_fence("tsx-attempt-1"), _fence("tsx-attempt-2")])
    compiler = FakeCompiler([True, True])
    verifier = FakeVerifier([
        _report(1, 0, [_violation("decoupling.series", ["C1", "U1"])]),
        _report(0, 0, []),
    ])
    result = _run(tmp_path, model, compiler, verifier)
    assert result.status == "passed"
    assert result.best_attempt == 2
    saved = _read_run(tmp_path)
    assert saved.status == "passed"
    assert saved.best_attempt == 2
    attempt1 = tmp_path / "run" / "attempts" / "01"
    assert (attempt1 / "index.circuit.tsx").is_file()
    assert (attempt1 / "verify.json").is_file()
    assert (attempt1 / "prompt.md").is_file()
    assert (attempt1 / "response.md").is_file()
    assert "tsx-attempt-1" in (attempt1 / "index.circuit.tsx").read_text(encoding="utf-8")
    assert len(model.prompts) == 2
    assert result.attempts[0].attempt == 1
    assert result.attempts[0].compiled is True
    assert result.attempts[0].errors == 1


def test_second_compile_try_stays_on_attempt_1_then_verifies(tmp_path):
    model = FakeModel([_fence("bad-tsx"), _fence("good-tsx")])
    compiler = FakeCompiler([False, True])
    verifier = FakeVerifier([_report(0, 0, [])])
    result = _run(tmp_path, model, compiler, verifier)
    assert result.status == "passed"
    assert [record.attempt for record in result.attempts] == [1]
    assert result.attempts[0].compile_tries == 2
    assert result.attempts[0].compiled is True
    attempt = tmp_path / "run" / "attempts" / "01"
    first = json.loads((attempt / "compile-1.json").read_text(encoding="utf-8"))
    second = json.loads((attempt / "compile-2.json").read_text(encoding="utf-8"))
    assert first["ok"] is False
    assert second["ok"] is True
    assert (attempt / "verify.json").is_file()
    assert len(compiler.calls) == 2
    assert len(verifier.calls) == 1
    retry_prompt = model.prompts[1]
    assert "first compile error" in retry_prompt
    assert "SECOND_COMPILE_ERROR_NOT_FOR_THE_MODEL" not in retry_prompt
    assert "KICAD_SCH_BODY_SECRET" not in retry_prompt
    assert "KICAD_PCB_BODY_SECRET" not in retry_prompt


def test_compile_cap_with_nothing_compiled_is_failed_compile(tmp_path):
    model = FakeModel([_fence("bad-1"), _fence("bad-2")])
    compiler = FakeCompiler([False, False])
    verifier = FakeVerifier([])
    result = _run(tmp_path, model, compiler, verifier, compile_cap=2)
    assert result.status == "failed_compile"
    assert result.best_attempt == 0
    assert len(result.attempts) == 1
    assert result.attempts[0].compiled is False
    assert result.attempts[0].compile_tries == 2
    assert verifier.calls == []
    assert len(model.prompts) == 2


def test_later_compile_cap_keeps_the_earlier_board(tmp_path):
    model = FakeModel([
        _fence("tsx-attempt-1"),
        _fence("tsx-attempt-2-try-1"),
        _fence("tsx-attempt-2-try-2"),
    ])
    compiler = FakeCompiler([True, False, False])
    verifier = FakeVerifier([
        _report(2, 1, [
            _violation("decoupling.series", ["C1"]),
            _violation("i2c.missing_pullup", ["R1"]),
        ]),
    ])
    result = _run(tmp_path, model, compiler, verifier, compile_cap=2)
    assert result.status == "failed_verify"
    assert result.best_attempt == 1
    assert result.attempts[0].compiled is True
    assert result.attempts[0].errors == 2
    assert result.attempts[1].attempt == 2
    assert result.attempts[1].compiled is False
    assert len(verifier.calls) == 1
    assert len(model.prompts) == 3


def test_regression_restarts_from_the_best_tsx(tmp_path):
    model = FakeModel([
        _fence("TSX_ATTEMPT_1"),
        _fence("TSX_ATTEMPT_2"),
        _fence("TSX_ATTEMPT_3"),
    ])
    compiler = FakeCompiler([True, True, True])
    verifier = FakeVerifier([
        _report(2, 0, [_violation("decoupling.series", ["C1"])]),
        _report(4, 0, [_violation("i2c.missing_pullup", ["R1", "R2"])]),
        _report(3, 0, [_violation("decoupling.series", ["C2"])]),
    ])
    result = _run(tmp_path, model, compiler, verifier)
    assert result.status == "failed_verify"
    assert result.best_attempt == 1
    assert "TSX_ATTEMPT_1" in model.prompts[2]
    assert "TSX_ATTEMPT_2" not in model.prompts[2]
    assert "regress" in model.prompts[2].lower()
    assert len(model.prompts) == 3


def test_equal_errors_continue_from_the_latest_tsx(tmp_path):
    model = FakeModel([
        _fence("TSX_ATTEMPT_1"),
        _fence("TSX_ATTEMPT_2"),
        _fence("TSX_ATTEMPT_3"),
    ])
    compiler = FakeCompiler([True, True, True])
    verifier = FakeVerifier([
        _report(2, 0, [_violation("decoupling.series", ["C1"])]),
        _report(2, 0, [_violation("i2c.missing_pullup", ["R1"])]),
        _report(2, 0, [_violation("address.floating", ["A0"])]),
    ])
    result = _run(tmp_path, model, compiler, verifier)
    assert "TSX_ATTEMPT_2" in model.prompts[2]
    assert "TSX_ATTEMPT_1" not in model.prompts[2]
    assert result.best_attempt == 3
    assert result.status == "failed_verify"


def test_same_rule_and_refs_still_runs_attempt_3(tmp_path):
    same = _violation("decoupling.series", ["C1", "U1"])
    model = FakeModel([
        _fence("TSX_ATTEMPT_1"),
        _fence("TSX_ATTEMPT_2"),
        _fence("TSX_ATTEMPT_3"),
    ])
    compiler = FakeCompiler([True, True, True])
    verifier = FakeVerifier([
        _report(1, 0, [same]),
        _report(1, 0, [_violation("decoupling.series", ["U1", "C1"])]),
        _report(1, 0, [_violation("decoupling.series", ["C1", "U1"])]),
    ])
    result = _run(tmp_path, model, compiler, verifier)
    assert len(model.prompts) == 3
    assert result.attempts[-1].attempt == 3
    assert "same rule_ids" in model.prompts[2]
    assert result.status == "failed_verify"


def test_missing_code_fence_counts_as_a_compile_try(tmp_path):
    model = FakeModel(["there is no fence here", _fence("TSX_RECOVERED")])
    compiler = FakeCompiler([True])
    verifier = FakeVerifier([_report(0, 0, [])])
    result = _run(tmp_path, model, compiler, verifier, compile_cap=2)
    assert result.status == "passed"
    assert [record.attempt for record in result.attempts] == [1]
    assert result.attempts[0].compile_tries == 2
    assert len(compiler.calls) == 1
    assert compiler.calls[0].strip() == "TSX_RECOVERED"
    first = json.loads(
        (tmp_path / "run" / "attempts" / "01" / "compile-1.json").read_text(encoding="utf-8")
    )
    assert first["ok"] is False


def test_unresolved_parts_never_call_codegen(tmp_path):
    model = FakeModel([_fence("should-not-be-used")])
    compiler = FakeCompiler([True])
    verifier = FakeVerifier([])
    parts = _parts(unresolved=[Unresolved("p5", "no in-stock header")])
    result = _run(tmp_path, model, compiler, verifier, parts=parts)
    assert result.status == "aborted"
    assert result.attempts == []
    assert result.best_attempt == 0
    assert model.prompts == []
    assert compiler.calls == []
    saved = json.loads((tmp_path / "run" / "parts.json").read_text(encoding="utf-8"))
    assert saved["unresolved"][0]["reason"] == "no in-stock header"


def test_plan_json_invalid_twice_aborts_with_no_design_attempt(tmp_path):
    model = FakeModel(["this is not json", "{}"])
    compiler = FakeCompiler([True])
    verifier = FakeVerifier([])
    result = _run(tmp_path, model, compiler, verifier, plan=None)
    assert result.status == "aborted"
    assert result.attempts == []
    assert result.best_attempt == 0
    assert len(model.prompts) == 2
    assert compiler.calls == []
    assert verifier.calls == []
    assert not (tmp_path / "run" / "attempts").exists()


def test_unconfirmed_spec_does_not_call_codegen(tmp_path):
    model = FakeModel([_fence("nope")])
    compiler = FakeCompiler([True])
    verifier = FakeVerifier([])
    result = _run(tmp_path, model, compiler, verifier, spec=_spec(confirmed=False))
    assert result.status == "aborted"
    assert result.attempts == []
    assert model.prompts == []
    assert compiler.calls == []


def test_pick_best_orders_errors_then_warnings_then_latest():
    from reflow.contracts import AttemptRecord
    from reflow.harness.loop import pick_best

    def record(attempt, errors, warnings, compiled=True):
        return AttemptRecord(attempt, 1, compiled, errors, warnings, [], f"attempts/{attempt:02d}")

    assert pick_best([record(1, 2, 0), record(2, 4, 0), record(3, 3, 0)]) == 1
    assert pick_best([record(1, 1, 0), record(2, 1, 2)]) == 1
    assert pick_best([record(1, 1, 1), record(2, 1, 1)]) == 2
    assert pick_best([record(1, 0, 3, compiled=False)]) == 0


def test_warnings_do_not_roll_back_the_tsx(tmp_path):
    model = FakeModel([
        _fence("TSX_ATTEMPT_1"),
        _fence("TSX_ATTEMPT_2"),
        _fence("TSX_ATTEMPT_3"),
    ])
    compiler = FakeCompiler([True, True, True])
    verifier = FakeVerifier([
        _report(2, 0, [_violation("decoupling.series", ["C1"])]),
        _report(2, 5, [_violation("i2c.missing_pullup", ["R1"])]),
        _report(2, 5, [_violation("address.floating", ["A0"])]),
    ])
    result = _run(tmp_path, model, compiler, verifier)
    assert result.best_attempt == 1
    assert "TSX_ATTEMPT_2" in model.prompts[2]
    assert "TSX_ATTEMPT_1" not in model.prompts[2]


def test_loop_source_does_not_import_an_sdk_learn_mode_or_the_router():
    root = Path(__file__).resolve().parents[1]
    blob = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            root / "reflow" / "harness" / "loop.py",
            root / "reflow" / "harness" / "feedback.py",
        )
    )
    lowered = blob.lower()
    for banned in (
        "litellm",
        "pydantic",
        "anthropic",
        "openai",
        "search_parts",
        "reflow.rules",
        "reflow.route",
        "reflow.learn",
    ):
        assert banned not in lowered


def test_prompt_for_attempt_3_has_no_kicad_bodies(tmp_path):
    model = FakeModel([
        _fence("TSX_ATTEMPT_1"),
        _fence("TSX_ATTEMPT_2"),
        _fence("TSX_ATTEMPT_3"),
    ])
    compiler = FakeCompiler([True, True, True])
    verifier = FakeVerifier([
        _report(1, 0, [_violation("decoupling.series", ["C1"])]),
        _report(1, 0, [_violation("i2c.missing_pullup", ["R2"])]),
        _report(1, 0, [_violation("address.floating", ["A0"])]),
    ])
    _run(tmp_path, model, compiler, verifier)
    for prompt in model.prompts:
        assert "KICAD_SCH_BODY_SECRET" not in prompt
        assert "KICAD_PCB_BODY_SECRET" not in prompt
        assert "SECRET_WHY_NOT_FOR_THE_MODEL" not in prompt
        assert ".kicad_sch" not in prompt
        assert ".kicad_pcb" not in prompt
