"""L-10: `reflow learn RUN_DIR` opens learn mode for a run folder (DECISIONS L-2)."""
import builtins
import sys
from pathlib import Path

import reflow.cli as cli

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "tests" / "data" / "real_runs" / "learn_mcp9808_20261022"


def test_reflow_learn_serves_the_run_folder(monkeypatch):
    import types

    calls = []
    fake = types.ModuleType("reflow.learn.server")
    fake.serve = lambda run_dir, **kw: calls.append((Path(run_dir), kw))
    monkeypatch.setitem(sys.modules, "reflow.learn.server", fake)
    assert cli.main(["learn", str(RUN), "--port", "8765", "--no-browser"]) == 0
    assert calls == [(RUN, {"port": 8765, "open_browser": False})]


def test_a_folder_that_is_not_a_run_is_refused(tmp_path, capsys):
    assert cli.main(["learn", str(tmp_path)]) == 2
    assert "run.json" in capsys.readouterr().err


def test_without_the_learn_extra_it_says_how_to_install_it(monkeypatch, capsys):
    real_import = builtins.__import__

    def no_fastapi(name, *args, **kwargs):
        if name == "reflow.learn.server" or name.startswith(("fastapi", "uvicorn")):
            raise ModuleNotFoundError(f"No module named {name!r}", name=name)
        return real_import(name, *args, **kwargs)

    monkeypatch.delitem(sys.modules, "reflow.learn.server", raising=False)
    monkeypatch.setattr(builtins, "__import__", no_fastapi)
    assert cli.main(["learn", str(RUN)]) == 2
    assert "pip install 'reflow-pcb[learn]'" in capsys.readouterr().err
