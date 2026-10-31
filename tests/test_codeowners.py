"""Every file has an owner, and the files that steer a model, a coding agent, CI or the verifier
are listed by name, so a PR touching them always asks for the maintainer's review (task CI-02).

GitHub only enforces this with branch protection's "Require review from Code Owners" on main,
which is a repo setting (docs/REVIEWING.md).
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CODEOWNERS = ROOT / ".github" / "CODEOWNERS"
MAINTAINER = "@AKSHAJ-SHELL"

# Paths where a change can steer a model or agent, run code in CI, or change what "correct" means.
SENSITIVE = [
    "/.github/",
    "/prompts/",
    "/skills/",
    "/AGENTS.md",
    "/CLAUDE.md",
    "/docs/agents/",
    "/reflow/rules/",
    "/reflow/harness/",
    "/reflow/netlist.py",
    "/reflow/violation.py",
    "/reflow/contracts.py",
    "/reflow/claude_code.py",
    "/reflow/llm.py",
    "/fixtures/",
    "/evals/",
    "/tools/",
    "/pyproject.toml",
    "/reflow.toml",
    "/tests/conftest.py",
]


def _rules() -> dict[str, list[str]]:
    assert CODEOWNERS.is_file(), ".github/CODEOWNERS is missing"
    rules = {}
    for line in CODEOWNERS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            path, *owners = line.split()
            rules[path] = owners
    return rules


def test_every_file_has_the_maintainer_as_owner():
    assert _rules().get("*") == [MAINTAINER]


def test_sensitive_paths_are_listed_by_name():
    rules = _rules()
    missing = [p for p in SENSITIVE if rules.get(p) != [MAINTAINER]]
    assert not missing, f"not in CODEOWNERS with {MAINTAINER}: {missing}"


def test_listed_paths_exist():
    stale = [p for p in _rules() if p != "*" and not (ROOT / p.strip("/")).exists()]
    assert not stale, f"CODEOWNERS lists paths that don't exist: {stale}"


def test_only_the_maintainer_owns_anything():
    others = {o for owners in _rules().values() for o in owners if o != MAINTAINER}
    assert not others, others
