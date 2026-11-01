"""The CI workflow can't be turned into a way to run someone else's code with our access (task CI-01).

A pull request from a fork runs the workflow file from that PR. These checks make sure the file on
main stays safe to run, and a PR that loosens it fails here, in front of the reviewer:

- the token is read-only, and the workflow never asks for more;
- no `pull_request_target` or `workflow_run` (they run with the base repo's secrets and token);
- no secrets at all: model runs stay on the maintainer's machine;
- every action is pinned to a full commit SHA, so a moved tag can't swap in new code;
- no `${{ github.event... }}` text (PR titles, branch names) is pasted into a shell command;
- old runs are cancelled on a new push, and every job has a timeout.

Text checks on purpose: the project has no YAML dependency, and the file is small.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
CI = WORKFLOWS / "ci.yml"


def _text() -> str:
    assert CI.is_file(), f"{CI.relative_to(ROOT)} is missing"
    return CI.read_text(encoding="utf-8")


def _code_lines(text: str) -> list[str]:
    """Lines with comments removed, so a comment can explain a rule without tripping it."""
    out = []
    for line in text.splitlines():
        stripped = line.split(" #", 1)[0].rstrip()
        if stripped.lstrip().startswith("#"):
            continue
        out.append(stripped)
    return out


def test_ci_is_the_only_workflow():
    assert sorted(p.name for p in WORKFLOWS.iterdir()) == ["ci.yml"]


def test_runs_on_push_to_main_and_on_pull_requests():
    text = _text()
    assert re.search(r"^on:\s*$", text, re.M)
    assert re.search(r"^  push:\s*\n    branches: \[main\]", text, re.M)
    assert re.search(r"^  pull_request:\s*$", text, re.M)


def test_no_triggers_that_run_with_the_base_repos_access():
    code = "\n".join(_code_lines(_text()))
    for trigger in ("pull_request_target", "workflow_run", "issue_comment"):
        assert trigger not in code, trigger


def test_token_is_read_only():
    code = _code_lines(_text())
    top = [i for i, line in enumerate(code) if line == "permissions:"]
    assert top, "no top-level permissions block"
    assert code[top[0] + 1].strip() == "contents: read"
    assert not any(re.search(r":\s*write\b", line) for line in code), "a permission asks for write"
    assert not any("write-all" in line or "read-all" in line for line in code)


def test_no_secrets():
    code = "\n".join(_code_lines(_text()))
    assert "secrets." not in code
    assert "secrets:" not in code


def test_actions_are_pinned_to_a_full_commit():
    uses = [line.split("uses:", 1)[1].strip() for line in _code_lines(_text()) if "uses:" in line]
    assert uses, "no actions found"
    for ref in uses:
        assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", ref), f"not pinned to a commit: {ref}"


def test_event_text_never_reaches_a_shell():
    code = "\n".join(_code_lines(_text()))
    assert "github.event." not in code
    assert "github.head_ref" not in code


def test_newer_push_cancels_the_older_run():
    text = _text()
    assert re.search(r"^concurrency:\s*\n  group: .+\n  cancel-in-progress: true", text, re.M)


def test_every_job_has_a_timeout():
    text = "\n".join(_code_lines(_text()))
    jobs = re.split(r"^  (?=[a-z][\w-]*:\s*$)", text.split("\njobs:\n", 1)[1], flags=re.M)
    jobs = [j for j in jobs if j.strip()]
    assert jobs
    for job in jobs:
        name = job.split(":", 1)[0]
        assert re.search(r"^    timeout-minutes: \d+", job, re.M), f"job {name} has no timeout"


def test_full_job_refuses_to_pass_by_skipping():
    """Tests skip when kicad-cli or tsci is missing. The full job must check both are there first."""
    text = _text()
    assert "kicad-cli version" in text
    assert "tsci --version" in text
