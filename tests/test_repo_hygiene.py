"""Test inputs must be in git, or a fresh clone fails tests that pass locally.

`.gitignore` hides `kicad/` folders and `*.zip` files, which once kept two
fixtures (tests/data/pinmaps/kicad/, tests/data/snapshot/cache.zip) out of
every commit while the tests that read them passed on the author's machine.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WATCHED = ["tests/data", "evals", "docs/examples", "docs/proposals/examples"]


@pytest.mark.skipif(shutil.which("git") is None or not (ROOT / ".git").exists(), reason="not a git checkout")
def test_no_test_input_is_hidden_by_gitignore():
    proc = subprocess.run(
        ["git", "ls-files", "--others", "--ignored", "--exclude-standard", "--", *WATCHED],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    hidden = [line for line in proc.stdout.splitlines() if "__pycache__" not in line]
    assert hidden == [], f"ignored by .gitignore, so never committed: {hidden}"
