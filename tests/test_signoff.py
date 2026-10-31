"""L-03: the sign-off gate. Before any fab files: the remaining warnings, then one y/n, recorded in signoff.json.

Sign-off is a person's decision, so it is never assumed: no terminal means no
prompt and no sign-off, and an export checks the recorded answer
(docs/07-learn-mode.md, golden rule 6).
"""
import io
import json
import shutil
from pathlib import Path

import pytest

from reflow.contracts import SignOff, from_dict
from reflow.signoff import SignOffError, prompt_signoff, remaining_warnings, signoff_refusals

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "tests" / "data" / "fab" / "pcf8574_run"
WARNING = {"rule_id": "decoupling.series", "severity": "warning", "message": "C1 is 3 mm from U1",
           "why": "w", "fix_hint": "f", "refs": ["C1", "U1"], "nets": ["V3_3"]}


class Terminal(io.StringIO):
    def isatty(self) -> bool:
        return True


def _run(tmp_path: Path, *, warning: bool = False) -> Path:
    run = Path(shutil.copytree(RUN, tmp_path / "run", ignore=shutil.ignore_patterns("build")))
    if warning:
        verify = run / "attempts" / "01" / "verify.json"
        data = json.loads(verify.read_text(encoding="utf-8")) | {"warnings": 1, "violations": [WARNING]}
        verify.write_text(json.dumps(data), encoding="utf-8")
    return run


def _signed(run: Path) -> SignOff:
    return from_dict(SignOff, json.loads((run / "signoff.json").read_text(encoding="utf-8")))


def test_remaining_warnings_are_the_best_attempts_verify_warnings(tmp_path):
    assert remaining_warnings(_run(tmp_path)) == []
    assert remaining_warnings(_run(tmp_path / "w", warning=True)) == ["decoupling.series: C1 is 3 mm from U1"]


def test_y_records_an_accepted_signoff_with_the_warnings_shown(tmp_path):
    run = _run(tmp_path, warning=True)
    shown = []
    signed = prompt_signoff(run, stdin=Terminal("y\n"), out=shown.append)
    assert signed.accepted is True and signed.overrides == []
    assert signed.warnings_acknowledged == ["decoupling.series: C1 is 3 mm from U1"] and signed.at.endswith("Z")
    assert _signed(run) == signed
    text = "\n".join(shown)
    assert "PCF8574 GPIO expander" in text and "decoupling.series: C1 is 3 mm from U1" in text
    assert signoff_refusals(run) == []


def test_n_records_a_declined_signoff_that_stops_export(tmp_path):
    run = _run(tmp_path)
    assert prompt_signoff(run, stdin=Terminal("n\n"), out=lambda _: None).accepted is False
    assert _signed(run).accepted is False
    assert any("declined" in r for r in signoff_refusals(run))


def test_anything_but_y_or_n_asks_again(tmp_path):
    run = _run(tmp_path)
    shown = []
    assert prompt_signoff(run, stdin=Terminal("sure\n\nyes\n"), out=shown.append).accepted is True
    assert sum("y or n" in line for line in shown) == 2


def test_no_terminal_means_no_prompt_and_no_signoff(tmp_path):
    run = _run(tmp_path)
    with pytest.raises(SignOffError, match="terminal"):
        prompt_signoff(run, stdin=io.StringIO("y\n"), out=lambda _: None)
    assert not (run / "signoff.json").exists()


def test_end_of_input_records_nothing(tmp_path):
    run = _run(tmp_path)
    with pytest.raises(SignOffError, match="no answer"):
        prompt_signoff(run, stdin=Terminal(""), out=lambda _: None)
    assert not (run / "signoff.json").exists()


def test_a_run_never_signed_off_is_refused(tmp_path):
    reasons = signoff_refusals(_run(tmp_path))
    assert len(reasons) == 1 and "not signed off" in reasons[0]


def test_a_signoff_given_before_the_warnings_changed_is_refused(tmp_path):
    run = _run(tmp_path)
    prompt_signoff(run, stdin=Terminal("y\n"), out=lambda _: None)
    verify = run / "attempts" / "01" / "verify.json"
    data = json.loads(verify.read_text(encoding="utf-8")) | {"warnings": 1, "violations": [WARNING]}
    verify.write_text(json.dumps(data), encoding="utf-8")
    assert any("warnings changed" in r for r in signoff_refusals(run))


def test_the_learn_uis_signoff_passes_the_same_gate(tmp_path):
    from fastapi.testclient import TestClient

    from reflow.learn.server import create_app

    run = Path(shutil.copytree(RUN, tmp_path / "run"))
    client = TestClient(create_app(run, vault=tmp_path / "vault"))
    assert client.post("/api/signoff", json={"accepted": True, "overrides": []}).status_code == 200
    assert signoff_refusals(run) == []
