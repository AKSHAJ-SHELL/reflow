"""Check that Markdown links to files and headings in the repo resolve (task CI-04).

    python tools/check_links.py [FILE.md ...]      # default: every .md file git tracks
    exit 0 all resolve · 1 broken links (one per line: path:line: target) · 2 usage problem

Checks relative links (`[x](docs/02-architecture.md)`, `[x](../README.md)`, `[x](SETUP.md#settings)`)
and same-file anchors (`[x](#limits-honest)`), with GitHub's heading slugs. A `:12` line suffix
is allowed. Web links, mailto, inline code and fenced code blocks are skipped. Nothing is fetched.
"""
from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
FENCE = re.compile(r"^\s*(```|~~~)")
HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$")
INLINE_CODE = re.compile(r"`[^`]*`")


@dataclass(frozen=True)
class Broken:
    path: str
    line: int
    target: str


def slug(heading: str) -> str:
    """GitHub's anchor for a heading: lower case, drop punctuation, spaces to hyphens."""
    text = re.sub(r"`|\*\*|__", "", heading.strip().lower())
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def _lines_outside_fences(text: str):
    fenced = False
    for number, line in enumerate(text.splitlines(), 1):
        if FENCE.match(line):
            fenced = not fenced
            continue
        if not fenced:
            yield number, line


def anchors(path: Path) -> set[str]:
    seen: dict[str, int] = {}
    out = set()
    for _, line in _lines_outside_fences(path.read_text(encoding="utf-8")):
        m = HEADING.match(line)
        if m:
            base = slug(m.group(1))
            n = seen.get(base, 0)
            seen[base] = n + 1
            out.add(base if n == 0 else f"{base}-{n}")
    return out


def _resolves(source: Path, target: str, root: Path) -> bool:
    file_part, _, anchor = target.partition("#")
    file_part = re.sub(r":\d+(-\d+)?$", "", file_part)
    dest = source if not file_part else (source.parent / file_part)
    try:
        dest.resolve().relative_to(root.resolve())
    except ValueError:
        return False  # points outside the repo
    if not dest.exists():
        return False
    if anchor and dest.suffix == ".md":
        return anchor in anchors(dest)
    return True


def check(paths: list[Path], root: Path = ROOT) -> list[Broken]:
    found = []
    for path in paths:
        rel = path.resolve().relative_to(root.resolve()).as_posix()
        for number, line in _lines_outside_fences(path.read_text(encoding="utf-8")):
            for m in LINK.finditer(INLINE_CODE.sub("", line)):
                target = m.group(1).strip("<>")
                if re.match(r"[a-z][a-z0-9+.-]*:", target, re.I):
                    continue  # https:, mailto:, etc.
                if not _resolves(path, target, root):
                    found.append(Broken(rel, number, target))
    return found


def tracked_markdown(root: Path = ROOT) -> list[Path]:
    out = subprocess.run(["git", "ls-files", "-z", "*.md"], cwd=root, capture_output=True, check=True).stdout
    return [root / name for name in out.decode().split("\0") if name and (root / name).is_file()]


def main(argv: list[str]) -> int:
    try:
        paths = [Path(a) for a in argv] if argv else tracked_markdown()
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"check_links: can't list files: {exc}", file=sys.stderr)
        return 2
    found = check(paths)
    for b in found:
        print(f"{b.path}:{b.line}: {b.target}")
    if found:
        print(f"{len(found)} broken link(s).")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
