"""tools/check_links.py finds Markdown links to files or headings that don't exist (task CI-04)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import check_links  # noqa: E402


def _write(tmp_path: Path, files: dict[str, str]) -> list[Path]:
    paths = []
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        paths.append(path)
    return paths


def _broken(tmp_path, files):
    found = check_links.check(_write(tmp_path, files), root=tmp_path)
    return [(b.path, b.line, b.target) for b in found]


def test_missing_file(tmp_path):
    assert _broken(tmp_path, {"README.md": "See [setup](SETUP.md).\n"}) == [("README.md", 1, "SETUP.md")]


def test_existing_file_and_folder(tmp_path):
    files = {"README.md": "[s](SETUP.md) [d](docs/) [c](docs/a.md:12)\n", "SETUP.md": "x\n", "docs/a.md": "y\n"}
    assert _broken(tmp_path, files) == []


def test_relative_to_the_linking_file(tmp_path):
    files = {"docs/a.md": "[b](b.md) [r](../README.md) [x](../nope.md)\n", "docs/b.md": "", "README.md": ""}
    assert _broken(tmp_path, files) == [("docs/a.md", 1, "../nope.md")]


def test_headings(tmp_path):
    files = {
        "README.md": "# Design a board\n\n## Limits (honest)\n\n[a](#design-a-board) [b](#limits-honest) [c](#nope)\n"
                     "[d](SETUP.md#settings) [e](SETUP.md#gone)\n",
        "SETUP.md": "## Settings\n",
    }
    assert _broken(tmp_path, files) == [("README.md", 5, "#nope"), ("README.md", 6, "SETUP.md#gone")]


def test_web_links_code_and_fenced_blocks_are_skipped(tmp_path):
    text = "[w](https://x.example/a.md) [m](mailto:a@b.c) `[c](nope.md)`\n\n```\n[f](nope.md)\n```\n"
    assert _broken(tmp_path, {"README.md": text}) == []


def test_repo_links_resolve():
    result = subprocess.run([sys.executable, str(ROOT / "tools" / "check_links.py")],
                            cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_ci_runs_it():
    assert "python tools/check_links.py" in (ROOT / ".github" / "workflows" / "ci.yml").read_text()
