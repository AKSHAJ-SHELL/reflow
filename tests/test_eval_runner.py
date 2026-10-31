"""E-01: the eval runner over evals/ (TASKS.md go/no-go).

A scripted model stands in for the LLM; parts come from the 27-row snapshot
fixture (tests/data/parts_db/), and compile + verify are the real tsci and
design verifier, so these tests skip without tsci. Each eval folder here is a
copy of evals/mcp9808_breakout with a different name and, sometimes, an edit.
"""
import json
import re
import shutil
import tomllib
from pathlib import Path

import pytest

import reflow.cli as cli
from reflow.compile import compile_board, find_tsci
from reflow.evals import run_evals
from reflow.llm import Completion

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "tests" / "data" / "parts_db" / "cache.sqlite3"
TSX = ROOT / "tests" / "data" / "integration"
pytestmark = pytest.mark.skipif(find_tsci() is None, reason="tsci not installed")


def _tsx(name: str, **replace: str) -> str:
    text = (TSX / name).read_text(encoding="utf-8")
    for old, new in replace.items():
        assert old in text
        text = text.replace(old, new)
    return "```tsx\n" + text + "```\n"


class Scripted:
    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)

    def complete(self, system, prompt, *, max_tokens=4096):
        if not self.replies:
            raise AssertionError("model called more times than scripted")
        return Completion(text=self.replies.pop(0), model="scripted/eval", input_tokens=100, output_tokens=40)


def _evals(tmp_path: Path, names: list[str]) -> Path:
    root = tmp_path / "evals"
    for name in names:
        shutil.copytree(ROOT / "evals" / "mcp9808_breakout", root / name)
        # The real eval is checked; each copy starts as a draft, so tests choose the status.
        path = root / name / "expected.toml"
        text = re.sub(r'^status = ".*"\nchecked_by = ".*"$', 'status = "draft"\nchecked_by = ""',
                      path.read_text(encoding="utf-8"), count=1, flags=re.M)
        assert 'status = "draft"\nchecked_by = ""' in text
        path.write_text(text, encoding="utf-8")
    return root


def _set(folder: Path, file: str, old: str, new: str) -> None:
    text = (folder / file).read_text(encoding="utf-8")
    assert old in text
    (folder / file).write_text(text.replace(old, new), encoding="utf-8")


def _run(tmp_path, evals_dir, replies: dict[str, list[str]], **kw):
    models = {name: Scripted(r) for name, r in replies.items()}
    return run_evals(
        evals_dir,
        make_model=lambda name: models[name],
        compiler=compile_board,
        bind=None,
        db_path=DB,
        runs_dir=tmp_path / "runs",
        out_dir=tmp_path / "results",
        **kw,
    )


GOOD = "sensor_good.tsx"
NO_PULLUPS = "sensor_no_pullups.tsx"
U1 = '<chip name="U1" footprint="soic8"'


# ---------------------------------------------------------------------------
# per-board results
# ---------------------------------------------------------------------------

def test_first_pass_retry_and_counts(tmp_path):
    evals = _evals(tmp_path, ["a_first", "b_retry"])
    summary = _run(tmp_path, evals, {"a_first": [_tsx(GOOD)], "b_retry": [_tsx(NO_PULLUPS), _tsx(GOOD)]})
    by = {b["name"]: b for b in summary["boards"]}

    assert (by["a_first"]["status"], by["a_first"]["first_pass"], by["a_first"]["attempts"]) == ("passed", True, 1)
    assert (by["b_retry"]["status"], by["b_retry"]["first_pass"], by["b_retry"]["attempts"]) == ("passed", False, 2)
    assert by["b_retry"]["rule_ids_by_attempt"] == [["i2c.missing_pullup", "i2c.missing_pullup"], []]
    for board in by.values():
        assert board["foreign_part_numbers"] == []
        assert board["expectation_misses"] == []
        assert board["expectations"] == "draft"
    assert (by["a_first"]["input_tokens"], by["b_retry"]["input_tokens"]) == (100, 200)

    totals = summary["totals"]
    assert totals["boards"] == 2 and totals["passed"] == 2 and totals["first_pass"] == 1
    assert totals["pass_rate_first"] == 0.5 and totals["pass_rate_after_retry"] == 1.0
    assert totals["input_tokens"] == 300 and totals["output_tokens"] == 120


def test_a_part_number_from_the_model_is_counted_and_spoils_the_board(tmp_path):
    evals = _evals(tmp_path, ["made_up"])
    reply = _tsx(GOOD, **{U1: U1 + ' manufacturerPartNumber="LM75AD" supplierPartNumbers={{ jlcpcb: ["C99999"] }}'})
    board = _run(tmp_path, evals, {"made_up": [reply]})["boards"][0]
    assert board["status"] == "passed"                       # the verifier has no provenance rule yet (R-03)
    assert sorted(f["value"] for f in board["foreign_part_numbers"]) == ["C99999", "LM75AD"]
    assert board["clean"] is False


def test_part_numbers_from_the_resolver_are_allowed(tmp_path):
    evals = _evals(tmp_path, ["resolved_ids"])
    reply = _tsx(GOOD, **{U1: U1 + ' manufacturerPartNumber="MCP9808T-E/MS" supplierPartNumbers={{ jlcpcb: ["C129490"] }}'})
    board = _run(tmp_path, evals, {"resolved_ids": [reply]})["boards"][0]
    assert board["foreign_part_numbers"] == [] and board["clean"] is True


def test_a_board_that_misses_its_expectations_is_not_clean(tmp_path):
    evals = _evals(tmp_path, ["wrong_count"])
    _set(evals / "wrong_count", "expected.toml", "resistor = 2", "resistor = 3")
    _set(evals / "wrong_count", "expected.toml", 'pins = ["ic.ALERT"]', 'pins = ["ic.SDA"]')
    board = _run(tmp_path, evals, {"wrong_count": [_tsx(GOOD)]})["boards"][0]
    assert board["status"] == "passed" and board["clean"] is False
    misses = " | ".join(board["expectation_misses"])
    assert "resistor" in misses and "ic.SDA" in misses


def test_an_unresolved_part_aborts_before_the_model_and_the_run_continues(tmp_path):
    evals = _evals(tmp_path, ["no_such_ic", "ok"])
    _set(evals / "no_such_ic", "plan.json", '"package": "MSOP-8"', '"package": "SOT-23"')
    summary = _run(tmp_path, evals, {"no_such_ic": [], "ok": [_tsx(GOOD)]})
    by = {b["name"]: b for b in summary["boards"]}
    assert by["no_such_ic"]["status"] == "aborted"
    assert "MCP9808" in by["no_such_ic"]["abort_reason"]
    assert by["ok"]["status"] == "passed"


def test_a_model_error_is_recorded_and_the_run_continues(tmp_path):
    from reflow.llm import ModelError

    class Down:
        def complete(self, *a, **k):
            raise ModelError("HTTP 529: overloaded")

    evals = _evals(tmp_path, ["down", "ok"])
    models = {"down": Down(), "ok": Scripted([_tsx(GOOD)])}
    summary = run_evals(evals, make_model=lambda n: models[n], compiler=compile_board, bind=None,
                        db_path=DB, runs_dir=tmp_path / "runs", out_dir=tmp_path / "results")
    by = {b["name"]: b for b in summary["boards"]}
    assert by["down"]["status"] == "error" and "overloaded" in by["down"]["error"]
    assert by["ok"]["status"] == "passed"


# ---------------------------------------------------------------------------
# go / no-go and the results file
# ---------------------------------------------------------------------------

def test_go_no_go_is_undecided_while_any_eval_is_a_draft(tmp_path):
    evals = _evals(tmp_path, ["a", "b", "c"])
    summary = _run(tmp_path, evals, {n: [_tsx(GOOD)] for n in ("a", "b", "c")})
    assert summary["go_no_go"]["decision"] == "undecided"
    assert "draft" in summary["go_no_go"]["reason"]


def test_go_needs_three_clean_boards_out_of_five_checked_evals(tmp_path):
    names = ["a", "b", "c", "d", "e"]
    evals = _evals(tmp_path, names)
    for name in names:
        _set(evals / name, "expected.toml", 'status = "draft"\nchecked_by = ""', 'status = "checked"\nchecked_by = "tester"')
    replies = {"a": [_tsx(GOOD)], "b": [_tsx(GOOD)], "c": [_tsx(NO_PULLUPS), _tsx(GOOD)],
               "d": [_tsx(NO_PULLUPS)] * 3, "e": [_tsx(NO_PULLUPS)] * 3}
    summary = _run(tmp_path, evals, replies)
    assert summary["totals"]["clean"] == 3
    assert summary["go_no_go"]["decision"] == "go"


def test_results_file_records_what_the_run_used(tmp_path):
    evals = _evals(tmp_path, ["a"])
    summary = _run(tmp_path, evals, {"a": [_tsx(GOOD)]})
    files = list((tmp_path / "results").glob("*.json"))
    assert len(files) == 1
    saved = json.loads(files[0].read_text(encoding="utf-8"))
    assert saved == summary
    run = saved["run"]
    assert run["model"] == "scripted/eval"
    assert run["pin_binding"] == "none (pins not bound to pin maps)"
    assert run["parts_db"] == str(DB)
    assert run["commit"] and run["tsci"]
    assert Path(saved["boards"][0]["run_dir"]).is_dir()


def test_only_runs_the_named_boards(tmp_path):
    evals = _evals(tmp_path, ["a", "b"])
    summary = _run(tmp_path, evals, {"b": [_tsx(GOOD)]}, only=["b"])
    assert [b["name"] for b in summary["boards"]] == ["b"]


# ---------------------------------------------------------------------------
# the command
# ---------------------------------------------------------------------------

def test_reflow_eval_without_an_api_key_exits_2(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("REFLOW_API_KEY", raising=False)
    assert cli.main(["eval", "--evals", str(ROOT / "evals")]) == 2
    assert "REFLOW_API_KEY" in capsys.readouterr().err


def test_reflow_eval_runs_from_config(tmp_path, monkeypatch, capsys):
    evals = _evals(tmp_path, ["a"])
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("REFLOW_API_KEY", "test-key")
    monkeypatch.setenv("REFLOW_PROVIDER", "anthropic")
    monkeypatch.setenv("REFLOW_MODEL", "test-model")
    monkeypatch.setenv("REFLOW_BASE_URL", "https://example.invalid")
    monkeypatch.setenv("REFLOW_PARTS_DB", str(DB))
    # Pins are bound for real here (V-12): the board's own rules file names the
    # MCP9808's KiCad symbol, and the model replies with the corrected first-real-run board.
    assert '"rules_file": "rules.toml"' in (evals / "a" / "spec.json").read_text(encoding="utf-8")
    assert 'symbol = "Sensor_Temperature:MCP9808_MSOP"' in (evals / "a" / "rules.toml").read_text(encoding="utf-8")
    monkeypatch.setenv("REFLOW_KICAD_SYMBOL_DIR", str(ROOT / "tests" / "data" / "pinmaps" / "kicad"))
    corrected = (ROOT / "tests" / "data" / "real_runs" / "mcp9808_nemotron_20261022" / "corrected.tsx").read_text(encoding="utf-8")
    monkeypatch.setattr(cli, "load_model", lambda config: Scripted(["```tsx\n" + corrected + "```\n"]))
    code = cli.main(["eval", "--evals", str(evals), "--out", str(tmp_path / "results")])
    out, err = capsys.readouterr()
    assert code == 0, err
    assert "1/1 passed" in out and "undecided" in out
    saved = json.loads(next((tmp_path / "results").glob("*.json")).read_text(encoding="utf-8"))
    assert saved["run"]["pin_binding"] == "reflow.pinbind.binder_for_spec"


# ---------------------------------------------------------------------------
# where each board stopped, model retries, repeated runs, prompt hashes
# ---------------------------------------------------------------------------

class Flaky:
    """Raises ModelError `fails` times, then answers from `replies`."""

    def __init__(self, fails: int, replies: list[str]) -> None:
        self.fails, self.calls, self.inner = fails, 0, Scripted(replies)

    def complete(self, system, prompt, *, max_tokens=None):
        from reflow.llm import ModelError

        self.calls += 1
        if self.calls <= self.fails:
            raise ModelError(f"Upstream idle timeout exceeded (code 504), call {self.calls}")
        return self.inner.complete(system, prompt)


def _quiet(**kw):
    """No real waiting between model retries in tests."""
    waits = []
    return waits, dict(sleep=waits.append, **kw)


def test_each_board_reports_the_stage_it_stopped_at(tmp_path):
    names = ["clean", "rules", "expectations", "compile", "parts"]
    evals = _evals(tmp_path, names)
    _set(evals / "expectations", "expected.toml", "resistor = 2", "resistor = 3")
    _set(evals / "parts", "plan.json", '"package": "MSOP-8"', '"package": "SOT-23"')
    replies = {"clean": [_tsx(GOOD)], "rules": [_tsx(NO_PULLUPS)] * 3, "expectations": [_tsx(GOOD)],
               "compile": ["no code here"] * 6, "parts": []}
    _, kw = _quiet()
    by = {b["name"]: b for b in _run(tmp_path, evals, replies, **kw)["boards"]}
    assert {n: by[n]["stage"] for n in names} == {
        "clean": "none", "rules": "rules", "expectations": "expectations", "compile": "compile", "parts": "parts",
    }


def test_a_pinout_error_stops_at_pin_binding(tmp_path):
    from reflow.pinbind import BindResult
    from reflow.violation import Violation

    def wrong_pin(netlist, parts, spec, part_numbers):
        bad = Violation("pinout.mismatch", "error", "U1 pin 8 is labelled A0, but the pin map says VDD",
                        "why", "fix", ["U1"], ["GND"])
        return BindResult(netlist=netlist, violations=[bad])

    evals = _evals(tmp_path, ["pins"])
    _, kw = _quiet(bind=wrong_pin)
    models = {"pins": Scripted([_tsx(GOOD)] * 3)}
    board = run_evals(evals, make_model=lambda n: models[n], compiler=compile_board, db_path=DB,
                      runs_dir=tmp_path / "runs", out_dir=tmp_path / "results", **kw)["boards"][0]
    assert board["status"] == "failed_verify"
    assert board["stage"] == "pin_binding"


def test_a_failed_model_call_is_retried(tmp_path):
    evals = _evals(tmp_path, ["flaky"])
    flaky = Flaky(2, [_tsx(GOOD)])
    waits, kw = _quiet()
    summary = run_evals(evals, make_model=lambda n: flaky, compiler=compile_board, bind=None, db_path=DB,
                        runs_dir=tmp_path / "runs", out_dir=tmp_path / "results", model_retries=2,
                        retry_wait_s=10, **kw)
    board = summary["boards"][0]
    assert board["status"] == "passed" and board["stage"] == "none"
    assert board["model_retries"] == 2
    assert [e.startswith("ModelError: Upstream idle timeout") for e in board["model_errors_retried"]] == [True, True]
    assert waits == [10, 20]
    assert summary["totals"]["model_errors"] == 0


def test_a_model_that_keeps_failing_is_a_model_error_not_a_design_failure(tmp_path):
    evals = _evals(tmp_path, ["down", "bad_design"])
    models = {"down": Flaky(99, []), "bad_design": Scripted([_tsx(NO_PULLUPS)] * 3)}
    _, kw = _quiet()
    summary = run_evals(evals, make_model=lambda n: models[n], compiler=compile_board, bind=None, db_path=DB,
                        runs_dir=tmp_path / "runs", out_dir=tmp_path / "results", model_retries=2, **kw)
    by = {b["name"]: b for b in summary["boards"]}
    assert by["down"]["status"] == "error" and by["down"]["stage"] == "model"
    assert models["down"].calls == 3
    totals = summary["totals"]
    assert totals["model_errors"] == 1
    assert totals["design_failures"] == 1
    assert totals["by_stage"] == {"model": 1, "rules": 1}


def test_repeats_run_each_board_n_times_and_report_rates(tmp_path):
    evals = _evals(tmp_path, ["a"])
    runs = iter([Scripted([_tsx(GOOD)]), Scripted([_tsx(NO_PULLUPS)] * 3), Scripted([_tsx(NO_PULLUPS), _tsx(GOOD)])])
    _, kw = _quiet()
    summary = run_evals(evals, make_model=lambda n: next(runs), compiler=compile_board, bind=None, db_path=DB,
                        runs_dir=tmp_path / "runs", out_dir=tmp_path / "results", repeats=3, **kw)
    boards = summary["boards"]
    assert [(b["name"], b["repeat"], b["status"]) for b in boards] == [
        ("a", 1, "passed"), ("a", 2, "failed_verify"), ("a", 3, "passed"),
    ]
    assert len({b["run_dir"] for b in boards}) == 3 and all(Path(b["run_dir"]).is_dir() for b in boards)
    rates = summary["by_board"]["a"]
    assert rates["runs"] == 3 and rates["passed"] == 2 and rates["first_pass"] == 1
    assert rates["pass_rate"] == pytest.approx(2 / 3)
    assert rates["stages"] == {"none": 2, "rules": 1}
    assert rates["clean"] == 2 and rates["clean_rate"] == pytest.approx(2 / 3) and rates["clean_majority"] is True
    assert summary["run"]["repeats"] == 3


def test_with_repeats_a_board_counts_clean_when_most_of_its_runs_are(tmp_path):
    names = ["a", "b", "c", "d", "e"]
    evals = _evals(tmp_path, names)
    for name in names:
        _set(evals / name, "expected.toml", 'status = "draft"\nchecked_by = ""', 'status = "checked"\nchecked_by = "tester"')
    good, bad = (lambda: Scripted([_tsx(GOOD)])), (lambda: Scripted([_tsx(NO_PULLUPS)] * 3))
    plan = {"a": [good, good, bad], "b": [good, bad, good], "c": [bad, good, good],
            "d": [good, bad, bad], "e": [bad, bad, bad]}
    queues = {n: iter(f() for f in fs) for n, fs in plan.items()}
    _, kw = _quiet()
    summary = run_evals(evals, make_model=lambda n: next(queues[n]), compiler=compile_board, bind=None, db_path=DB,
                        runs_dir=tmp_path / "runs", out_dir=tmp_path / "results", repeats=3, **kw)
    assert {n: summary["by_board"][n]["clean_majority"] for n in names} == {
        "a": True, "b": True, "c": True, "d": False, "e": False,
    }
    assert summary["go_no_go"]["decision"] == "go"
    assert "3/5" in summary["go_no_go"]["reason"]


def test_results_record_a_hash_of_each_prompt(tmp_path):
    import hashlib

    evals = _evals(tmp_path, ["a"])
    _, kw = _quiet()
    run = _run(tmp_path, evals, {"a": [_tsx(GOOD)]}, **kw)["run"]
    files = sorted(p for p in (ROOT / "prompts").glob("*.md") if p.name != "README.md")
    assert sorted(run["prompts"]) == [p.name for p in files]
    for path in files:
        assert run["prompts"][path.name] == hashlib.sha256(path.read_bytes()).hexdigest()
    combined = hashlib.sha256("".join(f"{p.name}:{run['prompts'][p.name]}\n" for p in files).encode()).hexdigest()
    assert run["prompts_hash"] == combined


def test_reflow_eval_passes_repeat_through_and_prints_rates(tmp_path, monkeypatch, capsys):
    import reflow.evals as evals_module

    seen = {}

    def fake_run_evals(evals_dir, **kw):
        seen.update(kw)
        board = {"name": "a", "repeat": 1, "status": "passed", "stage": "none", "attempts": 1, "clean": True,
                 "foreign_part_numbers": [], "abort_reason": "", "error": "", "expectation_misses": [],
                 "model_retries": 1}
        return {
            "boards": [board, dict(board, repeat=2, status="failed_verify", stage="rules", clean=False)],
            "by_board": {"a": {"runs": 2, "passed": 1, "first_pass": 1, "clean": 1, "pass_rate": 0.5,
                               "clean_rate": 0.5, "clean_majority": True, "stages": {"none": 1, "rules": 1}}},
            "totals": {"boards": 2, "passed": 1, "first_pass": 1, "clean": 1, "foreign_part_numbers": 0,
                       "input_tokens": 1, "output_tokens": 2, "model_errors": 0, "design_failures": 1,
                       "by_stage": {"none": 1, "rules": 1}},
            "go_no_go": {"decision": "undecided", "reason": "draft"},
        }

    monkeypatch.setattr(evals_module, "run_evals", fake_run_evals)
    monkeypatch.setattr(cli, "load_config", lambda **kw: {"max_attempts": 3, "compile_cap": 2})
    monkeypatch.setattr(cli, "load_model", lambda config: Scripted([]))
    assert cli.main(["eval", "--evals", str(tmp_path), "--repeat", "2"]) == 0
    assert seen["repeats"] == 2
    out = capsys.readouterr().out
    assert "a run 1/2: passed (stage none)" in out
    assert "a run 2/2: failed_verify (stage rules)" in out
    assert "a: 1/2 passed, 1/2 clean" in out
    assert "0 model error(s), 1 design failure(s)" in out
