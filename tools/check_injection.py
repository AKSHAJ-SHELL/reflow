"""Flag text a reviewer can't see, or wouldn't expect, in the repo's files (task CI-03).

    python tools/check_injection.py [PATH ...]     # default: every file git tracks
    exit 0 clean · 1 findings (one per line: path:line: kind: detail) · 2 usage problem

It's a tripwire for a pull request, not proof of safety: it finds the tricks that hide from a
reader of the diff, and the reviewer reads the rest (docs/REVIEWING.md). Checks:

- invisible: zero-width, bidirectional-override and Unicode tag characters, in any text file.
  They can hide instructions from a reader, or make code read differently from how it runs.
- hidden-comment: an HTML comment in Markdown. GitHub doesn't render it; a model reads it.
- override-phrase: text that tries to overrule a model's instructions, in any text file
  (prompts, specs, datasheet quotes and test data can all end up in a prompt).
- pipe-to-shell: `curl ... | sh` and the like, in any text file.
- remote-image: a Markdown image from the internet in a file a model or agent reads as
  instructions. A model that renders it can leak data in the URL.
- encoded-blob: a long base64-looking run in those same files.

Built files (the learn web app's bundle) and binary files are skipped.
"""
from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

INVISIBLE = re.compile("[\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff\U000e0000-\U000e007f]")
HTML_COMMENT = re.compile(r"<!--")
# Split so this file doesn't flag itself.
OVERRIDE = re.compile(
    "|".join([
        r"ignore\s+(all\s+|any\s+)?(the\s+)?(previous|prior|above|earlier)\s+(instructions|prompts?|rules)",
        r"disregard\s+(all\s+|any\s+)?(the\s+)?(previous|prior|above|earlier|your)\s+(instructions|rules)",
        r"forget\s+(all\s+|everything\s+)?(your|previous|prior)\s+instructions",
        r"you\s+are\s+now\s+(a|an|in)\s",
        r"new\s+system\s+" + r"prompt",
        r"(begin|end)\s+system\s+" + r"(prompt|message)",
    ]),
    re.I,
)
PIPE_TO_SHELL = re.compile(r"\b(curl|wget)\b[^|\n]*\|\s*(sudo\s+)?(ba|z)?sh\b", re.I)
REMOTE_IMAGE = re.compile(r"!\[[^\]]*\]\(\s*https?://", re.I)
ENCODED_BLOB = re.compile(r"[A-Za-z0-9+/=]{200,}")

# Files a model or coding agent reads as instructions.
AGENT_FILES = ("AGENTS.md", "CLAUDE.md")
AGENT_DIRS = ("prompts/", "skills/", "docs/agents/")

SKIP_DIRS = ("reflow/learn/static/", "web/node_modules/")
TEXT_SUFFIXES = {
    ".py", ".md", ".txt", ".toml", ".json", ".yml", ".yaml", ".tsx", ".ts", ".js", ".mjs", ".html",
    ".css", ".sh", ".ini", ".cfg", ".csv", ".kicad_sch", ".kicad_pcb", ".kicad_pro", ".kicad_sym",
    ".kicad_dru", ".net", ".dsn", ".ses", "",
}
SKIP_SELF = "tools/check_injection.py"
# The one HTML comment allowed: the prompts' draft banner on line 1 (H-08), which
# reflow/harness/feedback.py strips before a prompt is sent.
DRAFT_BANNER = "<!-- draft: human approval required before a loop loads this file -->"


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    kind: str
    detail: str


def _is_agent_file(rel: str) -> bool:
    return rel in AGENT_FILES or rel.startswith(AGENT_DIRS)


def _in_code_span(text: str, index: int) -> bool:
    """Shown as code (`<!-- ... -->` in backticks), so GitHub renders it and the reader sees it."""
    line_start = text.rfind("\n", 0, index) + 1
    return text.count("`", line_start, index) % 2 == 1


def _is_draft_banner(rel: str, text: str, index: int) -> bool:
    return rel.startswith("prompts/") and index == 0 and text.startswith(DRAFT_BANNER + "\n")


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def scan_text(rel: str, text: str) -> list[Finding]:
    found = []
    for m in INVISIBLE.finditer(text):
        found.append(Finding(rel, _line_of(text, m.start()), "invisible", f"U+{ord(m.group()):04X}"))
    if rel.endswith(".md"):
        for m in HTML_COMMENT.finditer(text):
            if _in_code_span(text, m.start()) or _is_draft_banner(rel, text, m.start()):
                continue
            found.append(Finding(rel, _line_of(text, m.start()), "hidden-comment", "HTML comment"))
    if rel != SKIP_SELF:
        for m in OVERRIDE.finditer(text):
            found.append(Finding(rel, _line_of(text, m.start()), "override-phrase", m.group()[:60]))
        for m in PIPE_TO_SHELL.finditer(text):
            found.append(Finding(rel, _line_of(text, m.start()), "pipe-to-shell", m.group()[:60]))
    if _is_agent_file(rel):
        for m in REMOTE_IMAGE.finditer(text):
            found.append(Finding(rel, _line_of(text, m.start()), "remote-image", m.group()[:60]))
        for m in ENCODED_BLOB.finditer(text):
            found.append(Finding(rel, _line_of(text, m.start()), "encoded-blob", f"{len(m.group())} chars"))
    return sorted(found, key=lambda f: (f.line, f.kind))


def scan(paths: list[Path], root: Path = ROOT) -> list[Finding]:
    found = []
    for path in paths:
        rel = path.resolve().relative_to(root.resolve()).as_posix()
        if rel.startswith(SKIP_DIRS) or path.suffix not in TEXT_SUFFIXES or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue  # binary
        found.extend(scan_text(rel, text))
    return found


def tracked_files(root: Path = ROOT) -> list[Path]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True).stdout
    return [root / name for name in out.decode().split("\0") if name]


def main(argv: list[str]) -> int:
    try:
        paths = [Path(a) for a in argv] if argv else tracked_files()
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"check_injection: can't list files: {exc}", file=sys.stderr)
        return 2
    found = scan(paths)
    for f in found:
        print(f"{f.path}:{f.line}: {f.kind}: {f.detail}")
    if found:
        print(f"{len(found)} finding(s). Read each one before merging (docs/REVIEWING.md).")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
