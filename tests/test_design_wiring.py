"""`reflow design` from a shell: config -> model, compile_board, catalog + resolver, design verifier.

No network and no API key: `load_model` and the catalog search are replaced
on `reflow.cli`. The compiler and the verifier are the real ones (the
end-to-end tests need tsci and skip without it).
"""
import json
import shutil
from pathlib import Path

import pytest

import reflow.cli as cli
from reflow.compile import find_tsci
from reflow.contracts import RunResult, from_dict
from reflow.llm import Completion, ModelError
from reflow.parts.catalog import CatalogError, CatalogPart

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "docs" / "examples"
TSX = ROOT / "tests" / "data" / "integration"
needs_tsci = pytest.mark.skipif(find_tsci() is None, reason="tsci not installed")


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """A cwd with no reflow.toml, and model settings only in the environment."""
    monkeypatch.chdir(tmp_path)
    for key in ("REFLOW_MAX_ATTEMPTS", "REFLOW_COMPILE_CAP", "REFLOW_TIMEOUT_S"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("REFLOW_API_KEY", "test-key")
    monkeypatch.setenv("REFLOW_PROVIDER", "anthropic")
    monkeypatch.setenv("REFLOW_MODEL", "test-model")
    monkeypatch.setenv("REFLOW_BASE_URL", "https://example.invalid")
    spec = json.loads((EXAMPLES / "spec.json").read_text(encoding="utf-8"))
    (tmp_path / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
    shutil.copy(EXAMPLES / "plan.json", tmp_path / "plan.json")
    return tmp_path


class ScriptedModel:
    def __init__(self, tsx_files: list[str]) -> None:
        self.replies = ["```tsx\n" + (TSX / name).read_text(encoding="utf-8") + "```\n" for name in tsx_files]
        self.calls = 0

    def complete(self, system, prompt, *, max_tokens=4096):
        if self.calls >= len(self.replies):
            raise AssertionError("model called more times than scripted")
        text = self.replies[self.calls]
        self.calls += 1
        return Completion(text=text, model="scripted/wiring", input_tokens=5, output_tokens=7)


def _catalog(calls: list):
    """One in-stock candidate per request; the named IC carries its MPN."""
    def search(request):
        calls.append((request.category, request.value, request.package))
        mpn = request.mpn or f"TEST-{request.category}-{request.value or 'x'}"
        return [CatalogPart(lcsc=f"C{100 + len(calls)}", mpn=mpn, manufacturer="test",
                            package=request.package or "pkg", value=request.value, stock=1000, basic=True,
                            unit_price_usd=0.01, source="test", category=request.category)]
    return search


def _use_model(monkeypatch, model, seen_config: list | None = None):
    def load_model(config):
        if seen_config is not None:
            seen_config.append(config)
        return model
    monkeypatch.setattr(cli, "load_model", load_model)


def _run(args: list[str]) -> int:
    return cli.main(["design", "--spec", "spec.json", *args])


# ---------------------------------------------------------------------------
# end to end
# ---------------------------------------------------------------------------

@needs_tsci
def test_design_runs_from_config_to_a_verified_board(workspace, monkeypatch, capsys):
    seen, searches = [], []
    model = ScriptedModel(["sensor_no_pullups.tsx", "sensor_good.tsx"])
    _use_model(monkeypatch, model, seen)
    monkeypatch.setattr(cli, "catalog_search", _catalog(searches))

    code = _run(["--plan", "plan.json", "--run-dir", "run"])
    out, err = capsys.readouterr()

    assert code == 0, err
    assert seen[0]["provider"] == "anthropic" and seen[0]["model"] == "test-model"
    assert seen[0]["api_key"] == "test-key"
    assert len(searches) == 5                       # one catalog query per plan part
    run = from_dict(RunResult, json.loads((workspace / "run" / "run.json").read_text(encoding="utf-8")))
    assert (run.status, run.best_attempt) == ("passed", 2)
    assert run.attempts[0].rule_ids == ["i2c.missing_pullup", "i2c.missing_pullup"]
    verify = json.loads((workspace / "run" / "attempts" / "01" / "verify.json").read_text(encoding="utf-8"))
    assert verify["schematic"] == "circuit.json"     # the design verifier, not the .kicad_sch export
    parts = json.loads((workspace / "run" / "parts.json").read_text(encoding="utf-8"))
    assert [p["request_id"] for p in parts["resolved"]] == ["p1", "p2", "p3", "p4", "p5"]
    assert "status=passed" in out
    assert "AI-designed" not in out and "routed" not in out.lower()
    assert "V-12" in err and "decoupling" in err      # the unbound-pins warning, every real run


@needs_tsci
def test_caps_come_from_config(workspace, monkeypatch, capsys):
    monkeypatch.setenv("REFLOW_MAX_ATTEMPTS", "1")
    _use_model(monkeypatch, ScriptedModel(["sensor_no_pullups.tsx"]))
    monkeypatch.setattr(cli, "catalog_search", _catalog([]))
    code = _run(["--plan", "plan.json", "--run-dir", "run"])
    capsys.readouterr()
    run = from_dict(RunResult, json.loads((workspace / "run" / "run.json").read_text(encoding="utf-8")))
    assert code == 1
    assert (run.status, len(run.attempts)) == ("failed_verify", 1)


# ---------------------------------------------------------------------------
# where the parts come from
# ---------------------------------------------------------------------------

@needs_tsci
def test_a_parts_file_skips_the_catalog(workspace, monkeypatch, capsys):
    example = json.loads((EXAMPLES / "resolved_parts.json").read_text(encoding="utf-8"))
    example["unresolved"] = []          # the example includes an unresolved header on purpose
    (workspace / "parts.json").write_text(json.dumps(example), encoding="utf-8")
    _use_model(monkeypatch, ScriptedModel(["sensor_good.tsx"]))

    def no_catalog(*args, **kwargs):
        raise AssertionError("catalog queried although --parts was given")

    monkeypatch.setattr(cli, "catalog_search", no_catalog)
    code = _run(["--plan", "plan.json", "--parts", "parts.json", "--run-dir", "run"])
    assert code == 0, capsys.readouterr().err


def test_an_unresolved_part_stops_before_any_model_call(workspace, monkeypatch, capsys):
    class NeverCalled:
        def complete(self, *args, **kwargs):
            raise AssertionError("model called although a part is unresolved")

    _use_model(monkeypatch, NeverCalled())
    monkeypatch.setattr(cli, "catalog_search", lambda request: [])
    code = _run(["--plan", "plan.json", "--run-dir", "run"])
    err = capsys.readouterr().err
    assert code == 2
    assert "no catalog candidates" in err


def test_a_catalog_failure_exits_2_with_its_message(workspace, monkeypatch, capsys):
    _use_model(monkeypatch, ScriptedModel([]))

    def down(*args, **kwargs):
        raise CatalogError("jlcsearch unreachable: test")

    monkeypatch.setattr(cli, "catalog_search", down)
    assert _run(["--plan", "plan.json", "--run-dir", "run"]) == 2
    assert "jlcsearch unreachable" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# configuration errors
# ---------------------------------------------------------------------------

def test_missing_api_key_exits_2_before_anything_runs(workspace, monkeypatch, capsys):
    monkeypatch.delenv("REFLOW_API_KEY")
    monkeypatch.setattr(cli, "catalog_search", lambda *a, **k: pytest.fail("catalog queried"))
    assert _run(["--plan", "plan.json", "--run-dir", "run"]) == 2
    assert "REFLOW_API_KEY" in capsys.readouterr().err
    assert not (workspace / "run").exists()


def test_bad_model_config_exits_2(workspace, monkeypatch, capsys):
    monkeypatch.delenv("REFLOW_BASE_URL")
    assert _run(["--plan", "plan.json", "--run-dir", "run"]) == 2
    assert "base_url" in capsys.readouterr().err


def test_spec_alone_still_only_checks_the_spec(workspace, monkeypatch, capsys):
    """No plan and no parts: parts can't be resolved, so the loop doesn't start."""
    monkeypatch.setattr(cli, "load_model", lambda config: pytest.fail("model built"))
    assert _run([]) == 0
    out = capsys.readouterr().out
    assert "design loop not run" in out and "--plan" in out
