"""Compiler wrapper: tscircuit TSX -> KiCad files.  OWNER: AGENT (tasks K-01, K-02).

Contract
--------
    compile_board(tsx: str, workdir: Path, *, timeout_s: int = 120) -> contracts.CompileResult
    circuit_json_errors(path) -> list[contracts.CompileError]

- Writes `tsx` unchanged to workdir/index.circuit.tsx and runs `tsci export`
  for circuit-json, kicad_sch, and kicad_pcb.
- On failure returns ok=False with parsed CompileError entries and the last
  <= 40 lines of stderr. Never raises for a compile error; raises only if
  `tsci` itself is missing or times out (exit code 2 territory, like
  `reflow check`).
- tsci exits 0 even when it could not build the board: it writes the errors
  into circuit.json as `source_*_error` elements (e.g. a component with
  invalid props is dropped, with `source_failed_to_create_component_error`).
  `circuit_json_errors` reads them, one CompileError per element in file
  order, each message on one line and without tscircuit's "Details:" dump.
  Any of them, or an unreadable circuit.json, makes the compile not ok.
  `*_warning` elements are not errors. Neither are `pcb_*` / `schematic_*`
  errors: they are layout results (blinky compiles with a
  `pcb_port_not_connected_error` from the autorouter), which the PCB checks
  report (V-13), not the compiler.

Must never
----------
- edit or "repair" the model's code,
- write outside `workdir`,
- treat a non-zero exit as success, or a zero exit as proof the files exist,
- treat a zero exit as proof the board was built (circuit.json may hold errors),
- copy a part number out of the TSX into an MPN or LCSC id.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from reflow.contracts import CompileError, CompileResult

STDERR_TAIL_LINES = 40

_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_RE_DASH = re.compile(
    r"^(?P<file>.+?):(?P<line>\d+):(?P<col>\d+)\s+-\s+error:\s*(?P<msg>.+)$"
)
_RE_TSC = re.compile(
    r"^(?P<file>[^(]+)\((?P<line>\d+),(?P<col>\d+)\):\s*error"
    r"(?:\s+(?P<code>TS\d+))?:\s*(?P<msg>.+)$"
)
_RE_COLON = re.compile(
    r"^(?P<file>.+?):(?P<line>\d+):(?P<col>\d+):\s*error:\s*(?P<msg>.+)$"
)
_RE_FATAL = re.compile(r"^Fatal error \[[^\]]+\]:\s*(?P<msg>.+)$")
_RE_BULLET = re.compile(r"^-\s+\S+_error:\s*(?P<msg>.*)$")
_RE_ESBUILD = re.compile(r"^(?:[\u2718\u00d7xX]\s*)?\[ERROR\]\s*(?P<msg>.+)$")
_RE_ESBUILD_LOC = re.compile(
    r"^(?P<file>.+?):(?P<line>\d+):(?P<col>\d+):?\s*$"
)
_RE_BUN = re.compile(
    r"^(?:SyntaxError|TypeError|ReferenceError|Error|error):\s*(?P<msg>.+)$"
)
_RE_AT = re.compile(
    r"\bat\s+(?:\S+\s+\()?(?P<file>(?:[A-Za-z]:)?[^:\s()]+\.(?:tsx|ts|jsx|js))"
    r":(?P<line>\d+):(?P<col>\d+)"
)
_RE_NO_LINE = re.compile(r"^(?P<file>[^:\n]+):\s+error:\s*(?P<msg>.+)$")
_RE_QUOTED_FILE = re.compile(r"""["']([^"']+\.(?:tsx|ts|jsx|js))["']""")
_RE_FRAME = re.compile(r"^\d+\s*[|│]")
_SKIP_PREFIXES = (
    "at ",
    "Build exiting",
    "Build complete",
    "Building",
    "Generating",
    "Circuit JSON",
    "Circuits",
    "Options",
    "Output",
    "Saved ",
    "note:",
)

_EXPORTS = (
    ("circuit-json", "circuit.json"),
    ("kicad_sch", "board.kicad_sch"),
    ("kicad_pcb", "board.kicad_pcb"),
)


class TsciMissingError(RuntimeError):
    """`tsci` is not installed or not executable. Not a board compile error."""


class TsciTimeoutError(RuntimeError):
    """`tsci` did not finish within timeout_s. Not a board compile error."""


def find_tsci() -> str | None:
    override = os.environ.get("TSCI")
    if override:
        candidate = Path(override)
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
        return shutil.which(override)
    return shutil.which("tsci")


def trim_stderr(text: str, *, max_lines: int = STDERR_TAIL_LINES) -> str:
    """Last `max_lines` lines of stderr, with ANSI color codes removed."""
    lines = _strip_ansi(text or "").splitlines()
    if len(lines) > max_lines:
        lines = lines[-max_lines:]
    return "\n".join(lines)


def parse_compile_errors(stderr: str) -> list[CompileError]:
    """Turn tsci stderr into CompileError rows. Order follows the text."""
    lines = _strip_ansi(stderr or "").splitlines()
    found: list[CompileError] = []
    seen: set[tuple[str, int, int, str]] = set()
    pending: str | None = None

    def add(message: str, line: int = 0, column: int = 0, file: str = "index.circuit.tsx") -> None:
        message = message.strip()
        if not message:
            return
        file = _normalize_file(file)
        key = (file, line, column, message)
        if key in seen:
            return
        seen.add(key)
        found.append(CompileError(message, line, column, file))

    for index, raw in enumerate(lines):
        text = raw.strip()
        if not text:
            continue
        if pending is not None:
            loc = _RE_ESBUILD_LOC.match(text)
            if loc:
                add(pending, int(loc["line"]), int(loc["col"]), loc["file"])
                pending = None
                continue
        dash = _RE_DASH.match(text)
        if dash:
            pending = None
            add(dash["msg"], int(dash["line"]), int(dash["col"]), dash["file"])
            continue
        tsc = _RE_TSC.match(text)
        if tsc:
            pending = None
            message = f"{tsc['code']}: {tsc['msg']}" if tsc["code"] else tsc["msg"]
            add(message, int(tsc["line"]), int(tsc["col"]), tsc["file"])
            continue
        colon = _RE_COLON.match(text)
        if colon:
            pending = None
            add(colon["msg"], int(colon["line"]), int(colon["col"]), colon["file"])
            continue
        fatal = _RE_FATAL.match(text)
        if fatal:
            pending = None
            add(fatal["msg"], file=_file_in(fatal["msg"]))
            continue
        bullet = _RE_BULLET.match(text)
        if bullet:
            pending = None
            add(bullet["msg"] or text)
            continue
        no_line = _RE_NO_LINE.match(text)
        if no_line:
            pending = None
            add(no_line["msg"], file=no_line["file"])
            continue
        esbuild = _RE_ESBUILD.match(text)
        if esbuild:
            pending = esbuild["msg"]
            continue
        bun = _RE_BUN.match(text)
        if bun:
            pending = None
            loc = _at_nearby(lines, index)
            if loc is None:
                add(bun["msg"])
            else:
                add(bun["msg"], loc[0], loc[1], loc[2])
            continue
    if pending:
        add(pending)
    if not found:
        plain = _plain_line(lines)
        if plain:
            add(plain)
    return found


def format_compile_errors(errors: list[CompileError]) -> str:
    """Canonical text form. parse_compile_errors() of this text returns `errors`."""
    lines = []
    for err in errors:
        if err.line:
            lines.append(f"{err.file}:{err.line}:{err.column} - error: {err.message}")
        else:
            lines.append(f"{err.file}: error: {err.message}")
    return "\n".join(lines)


def compile_board(tsx: str, workdir: Path, *, timeout_s: int = 120) -> CompileResult:
    if not isinstance(tsx, str):
        raise TypeError("tsx must be a str")
    tsci = find_tsci()
    if tsci is None:
        raise TsciMissingError(
            "tsci not found. Install tscircuit (`npm i -g tscircuit`) or set TSCI."
        )
    root = Path(workdir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    source = root / "index.circuit.tsx"
    source.write_text(tsx, encoding="utf-8")

    deadline = time.monotonic() + timeout_s
    stderr_parts: list[str] = []
    for fmt, name in _EXPORTS:
        dest = root / name
        cmd = [
            tsci,
            "export",
            source.name,
            "-f",
            fmt,
            "-o",
            str(dest),
            "--disable-parts-engine",
        ]
        proc = _run(cmd, root, deadline, timeout_s)
        stderr_parts.append(proc.stderr or "")
        if proc.returncode != 0:
            return _failed("".join(stderr_parts), proc.returncode, files_ok=False)
        if not _contained(root, dest):
            return _failed("".join(stderr_parts), proc.returncode, files_ok=False)

    circuit_json, kicad_sch, kicad_pcb = (root / name for _, name in _EXPORTS)
    built = circuit_json_errors(circuit_json)
    if built:
        return CompileResult(
            ok=False,
            errors=built,
            stderr_tail=trim_stderr("".join(stderr_parts)),
            kicad_sch="",
            kicad_pcb="",
            circuit_json="",
        )
    return CompileResult(
        ok=True,
        errors=[],
        stderr_tail=trim_stderr("".join(stderr_parts)),
        kicad_sch=str(kicad_sch),
        kicad_pcb=str(kicad_pcb),
        circuit_json=str(circuit_json),
    )


def circuit_json_errors(path) -> list[CompileError]:
    """The `source_*_error` elements tsci wrote into circuit.json, as CompileErrors."""
    try:
        elements = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [CompileError(f"tsci wrote an unreadable circuit.json ({exc.__class__.__name__})")]
    if not isinstance(elements, list):
        return [CompileError("tsci wrote a circuit.json that is not a list of elements")]
    errors: list[CompileError] = []
    for element in elements:
        kind = element.get("type", "") if isinstance(element, dict) else ""
        if not isinstance(kind, str) or not (kind.startswith("source_") and kind.endswith("_error")):
            continue
        message = element.get("message")
        text = message if isinstance(message, str) and message.strip() else kind
        text = " ".join(text.split(" Details:", 1)[0].split())
        errors.append(CompileError(text))
    return errors


def _run(cmd: list[str], cwd: Path, deadline: float, timeout_s: int) -> subprocess.CompletedProcess[str]:
    left = deadline - time.monotonic()
    if left <= 0:
        raise TsciTimeoutError(f"tsci timed out after {timeout_s}s")
    try:
        return subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=left,
        )
    except subprocess.TimeoutExpired as exc:
        raise TsciTimeoutError(f"tsci timed out after {timeout_s}s") from exc
    except FileNotFoundError as exc:
        raise TsciMissingError("tsci not found") from exc


def _failed(stderr: str, returncode: int, *, files_ok: bool) -> CompileResult:
    errors = parse_compile_errors(stderr)
    if not errors:
        if returncode == 0 and not files_ok:
            message = "tsci exited 0 but did not write KiCad schematic, PCB, and circuit json"
        else:
            message = f"tsci exited with status {returncode}"
        errors = [CompileError(message)]
    return CompileResult(
        ok=False,
        errors=errors,
        stderr_tail=trim_stderr(stderr),
        kicad_sch="",
        kicad_pcb="",
        circuit_json="",
    )


def _contained(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root)
    except ValueError:
        return False
    return path.is_file() and path.stat().st_size > 0


def _strip_ansi(text: str) -> str:
    return _ANSI.sub("", text)


def _normalize_file(file: str) -> str:
    cleaned = file.strip().strip("\"'")
    if not cleaned:
        return "index.circuit.tsx"
    path = Path(cleaned)
    if path.is_absolute():
        return path.name or "index.circuit.tsx"
    return cleaned


def _file_in(message: str) -> str:
    match = _RE_QUOTED_FILE.search(message)
    if match:
        return _normalize_file(match.group(1))
    return "index.circuit.tsx"


def _at_nearby(lines: list[str], start: int) -> tuple[int, int, str] | None:
    for raw in lines[start + 1:start + 6]:
        match = _RE_AT.search(raw)
        if match:
            return int(match["line"]), int(match["col"]), match["file"]
    return None


def _plain_line(lines: list[str]) -> str | None:
    for raw in lines:
        text = raw.strip()
        if not text or set(text) <= {"^", "~", "|", " "}:
            continue
        if text.startswith(_SKIP_PREFIXES) or "_warning:" in text:
            continue
        if _RE_FRAME.match(text):
            continue
        return text
    return None
