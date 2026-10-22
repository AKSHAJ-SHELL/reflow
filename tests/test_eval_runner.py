"""E-01: the eval runner over evals/ (TASKS.md go/no-go).

A scripted model stands in for the LLM; parts come from the 27-row snapshot
fixture (tests/data/parts_db/), and compile + verify are the real tsci and
design verifier, so these tests skip without tsci. Each eval folder here is a
copy of evals/mcp9808_breakout with a different name and, sometimes, an edit.
"""
import json
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
    assert run["pin_binding"] == "none (V-12 not built)"
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
    monkeypatch.setattr(cli, "load_model", lambda config: Scripted([_tsx(GOOD)]))
    code = cli.main(["eval", "--evals", str(evals), "--out", str(tmp_path / "results")])
    out, err = capsys.readouterr()
    assert code == 0, err
    assert "1/1 passed" in out and "undecided" in out
    assert "V-12" in err
