"""K-01 tsci wrapper and K-02 stderr parser. Parser samples live in this file."""
import shutil
import stat
import textwrap
from pathlib import Path

import pytest

from reflow.compile import (
    TsciMissingError,
    TsciTimeoutError,
    circuit_json_errors,
    compile_board,
    format_compile_errors,
    parse_compile_errors,
    trim_stderr,
)
from reflow.contracts import CompileError

ROOT = Path(__file__).resolve().parents[1]
TAIL_LIMIT = 40
# tsci exits 0 on this board but writes its errors into circuit.json (see its README).
LIGHTNING = ROOT / "tests" / "data" / "real_runs" / "mcp9808_lightning_20261022"


def _install_tsci(directory: Path, body: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    script = directory / "tsci"
    script.write_text("#!/usr/bin/python3\n" + body, encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)


def _use_tsci(monkeypatch, directory: Path) -> None:
    monkeypatch.setenv("PATH", str(directory))
    monkeypatch.delenv("TSCI", raising=False)


def test_missing_tsci_raises(tmp_path, monkeypatch):
    empty = tmp_path / "bin"
    empty.mkdir()
    _use_tsci(monkeypatch, empty)
    work = tmp_path / "work"
    with pytest.raises(TsciMissingError):
        compile_board("export default () => (<board />)", work)
    assert not (work / "index.circuit.tsx").exists()


def test_syntax_error_is_not_ok_and_tail_is_trimmed(tmp_path, monkeypatch):
    tsx = "export default () => (\n  <board>\n"
    noise = "\n".join(f"note: pass {i}" for i in range(50))
    diagnostic = "index.circuit.tsx:2:3 - error: Unexpected token '<'"
    _install_tsci(
        tmp_path / "bin",
        textwrap.dedent(
            f"""
            import pathlib, sys
            src = pathlib.Path("index.circuit.tsx").read_text(encoding="utf-8")
            assert src == {tsx!r}
            sys.stderr.write({noise!r} + "\\n" + {diagnostic!r} + "\\n")
            raise SystemExit(1)
            """
        ),
    )
    _use_tsci(monkeypatch, tmp_path / "bin")
    work = tmp_path / "work"
    before = set(tmp_path.iterdir())
    result = compile_board(tsx, work)

    assert result.ok is False
    assert len(result.errors) >= 1
    assert result.errors[0] == CompileError(
        "Unexpected token '<'", 2, 3, "index.circuit.tsx"
    )
    assert len(result.stderr_tail.splitlines()) <= TAIL_LIMIT
    assert diagnostic in result.stderr_tail
    assert result.kicad_sch == ""
    assert result.kicad_pcb == ""
    assert result.circuit_json == ""
    assert (work / "index.circuit.tsx").read_text(encoding="utf-8") == tsx
    assert set(tmp_path.iterdir()) == before | {work}


def test_wrapper_does_not_turn_tsx_text_into_a_part_id(tmp_path, monkeypatch):
    tsx = 'export default () => (\n  <resistor name="R1" supplierPartNumber="C25804" />\n'
    _install_tsci(
        tmp_path / "bin",
        textwrap.dedent(
            """
            import sys
            sys.stderr.write("index.circuit.tsx:1:1 - error: Unexpected token\\n")
            raise SystemExit(1)
            """
        ),
    )
    _use_tsci(monkeypatch, tmp_path / "bin")
    result = compile_board(tsx, tmp_path / "work")
    blob = result.stderr_tail + " ".join(err.message for err in result.errors)
    blob += result.kicad_sch + result.kicad_pcb + result.circuit_json
    assert "C25804" not in blob
    assert (tmp_path / "work" / "index.circuit.tsx").read_text(encoding="utf-8") == tsx


def test_zero_exit_without_output_files_is_not_ok(tmp_path, monkeypatch):
    _install_tsci(
        tmp_path / "bin",
        "import sys\nsys.stderr.write('Build exiting with code 0: build finished successfully\\n')\n",
    )
    _use_tsci(monkeypatch, tmp_path / "bin")
    result = compile_board("export default () => (<board />)", tmp_path / "work")
    assert result.ok is False
    assert result.errors
    assert result.kicad_sch == ""
    assert result.kicad_pcb == ""
    assert result.circuit_json == ""


def test_zero_exit_with_outputs_is_ok(tmp_path, monkeypatch):
    _install_tsci(
        tmp_path / "bin",
        textwrap.dedent(
            """
            import pathlib, sys
            args = sys.argv[1:]
            out = pathlib.Path(args[args.index("-o") + 1])
            out.parent.mkdir(parents=True, exist_ok=True)
            fmt = args[args.index("-f") + 1]
            if fmt == "kicad_sch":
                out.write_text("(kicad_sch (version 20250114))\\n")
            elif fmt == "kicad_pcb":
                out.write_text("(kicad_pcb (version 20250114))\\n")
            else:
                out.write_text("[]\\n")
            """
        ),
    )
    _use_tsci(monkeypatch, tmp_path / "bin")
    work = tmp_path / "work"
    result = compile_board("export default () => (<board />)", work)
    assert result.ok is True
    assert result.errors == []
    for path in (result.kicad_sch, result.kicad_pcb, result.circuit_json):
        file = Path(path)
        assert file.is_file() and file.stat().st_size > 0
        file.resolve().relative_to(work.resolve())


def test_nonzero_exit_is_not_ok_even_if_files_exist(tmp_path, monkeypatch):
    _install_tsci(
        tmp_path / "bin",
        textwrap.dedent(
            """
            import pathlib, sys
            args = sys.argv[1:]
            if "-o" in args:
                out = pathlib.Path(args[args.index("-o") + 1])
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text("not a success\\n")
            sys.stderr.write("index.circuit.tsx:4:1 - error: still broken\\n")
            raise SystemExit(1)
            """
        ),
    )
    _use_tsci(monkeypatch, tmp_path / "bin")
    result = compile_board("export default () => (<board />)", tmp_path / "work")
    assert result.ok is False
    assert result.kicad_sch == ""
    assert result.kicad_pcb == ""
    assert result.circuit_json == ""
    assert result.errors[0].message == "still broken"


def test_timeout_raises(tmp_path, monkeypatch):
    _install_tsci(
        tmp_path / "bin",
        "import time\ntime.sleep(30)\n",
    )
    _use_tsci(monkeypatch, tmp_path / "bin")
    with pytest.raises(TsciTimeoutError):
        compile_board("export default () => (<board />)", tmp_path / "work", timeout_s=1)


# Recorded tsci stderr dialects. Kept here, not under fixtures/.
SAMPLES = [
    (
        "dash",
        "index.circuit.tsx:14:5 - error: Unexpected token '<'\n",
        [
            CompileError("Unexpected token '<'", 14, 5, "index.circuit.tsx"),
        ],
    ),
    (
        "tsc",
        "src/board.tsx(3,12): error TS1005: '>' expected.\n",
        [
            CompileError("TS1005: '>' expected.", 3, 12, "src/board.tsx"),
        ],
    ),
    (
        "bun",
        "error: Expected \">\" but found end of file\n"
        "    at /tmp/job/index.circuit.tsx:42:3\n",
        [
            CompileError(
                'Expected ">" but found end of file',
                42,
                3,
                "index.circuit.tsx",
            ),
        ],
    ),
    (
        "fatal",
        "\x1b[31mFatal error [circuit_generation_failed]: "
        'No component found in "/tmp/w/index.circuit.tsx". '
        "Make sure you export a component.\x1b[39m\n",
        [
            CompileError(
                'No component found in "/tmp/w/index.circuit.tsx". '
                "Make sure you export a component.",
                0,
                0,
                "index.circuit.tsx",
            ),
        ],
    ),
    (
        "esbuild",
        "\n".join(f"note: compiling module {i}" for i in range(55))
        + "\n\u2718 [ERROR] Unexpected \"<\"\n"
        + "\n    index.circuit.tsx:14:5:\n"
        + "      14 \u2502     <\n",
        [
            CompileError('Unexpected "<"', 14, 5, "index.circuit.tsx"),
        ],
    ),
    (
        "tsci-export-syntax",
        "Error generating circuit JSON: BuildMessage: Syntax Error\n",
        [
            CompileError("Error generating circuit JSON: BuildMessage: Syntax Error"),
        ],
    ),
    (
        "tsci-build-syntax",
        "2 | <board>\n"
        "           ^\n"
        "error: Syntax Error\n"
        "    at /tmp/syntax-probe/index.circuit.tsx:2:8\n"
        "Fatal error [circuit_generation_failed]: Syntax Error\n"
        "Build exiting with code 1: fatal circuit build errors occurred\n",
        [
            CompileError("Syntax Error", 2, 8, "index.circuit.tsx"),
            CompileError("Syntax Error", 0, 0, "index.circuit.tsx"),
        ],
    ),
]


@pytest.mark.parametrize("name, stderr, expected", SAMPLES, ids=[s[0] for s in SAMPLES])
def test_parse_recorded_stderr_round_trip(name, stderr, expected):
    errors = parse_compile_errors(stderr)
    assert errors == expected
    assert parse_compile_errors(format_compile_errors(errors)) == expected
    tail = trim_stderr(stderr)
    assert len(tail.splitlines()) <= TAIL_LIMIT
    assert "\x1b" not in tail
    assert parse_compile_errors(tail) == expected


def test_plain_circuit_diagnostic_is_kept():
    stderr = (
        'Could not find port for selector "R_MISSING.pin1"\n'
        "    at renderCircuit (/usr/lib/tscircuit/cli.js:10:4)\n"
        "Build exiting with code 1: circuit build errors occurred\n"
    )
    errors = parse_compile_errors(stderr)
    assert errors == [
        CompileError('Could not find port for selector "R_MISSING.pin1"'),
    ]


def test_bullet_circuit_error():
    stderr = '- source_trace_not_connected_error: Could not find port for selector "R1.pin1"\n'
    assert parse_compile_errors(stderr) == [
        CompileError('Could not find port for selector "R1.pin1"'),
    ]


def test_warnings_are_not_compile_errors():
    stderr = "- source_no_power_pin_defined_warning: No power pin defined\n"
    assert parse_compile_errors(stderr) == []


@pytest.mark.skipif(shutil.which("tsci") is None, reason="tsci not installed; blinky ok path parked")
def test_blinky_tsx_compiles(tmp_path):
    tsx = (ROOT / "boards" / "blinky" / "index.circuit.tsx").read_text(encoding="utf-8")
    result = compile_board(tsx, tmp_path, timeout_s=180)
    assert result.ok is True
    assert result.errors == []
    assert (tmp_path / "index.circuit.tsx").read_text(encoding="utf-8") == tsx
    for path in (result.kicad_sch, result.kicad_pcb, result.circuit_json):
        file = Path(path)
        assert file.is_file() and file.stat().st_size > 0
        file.resolve().relative_to(tmp_path.resolve())
    assert "kicad_sch" in Path(result.kicad_sch).read_text(encoding="utf-8")
    assert "kicad_pcb" in Path(result.kicad_pcb).read_text(encoding="utf-8")


@pytest.mark.skipif(shutil.which("tsci") is None, reason="tsci not installed")
def test_real_tsci_syntax_error(tmp_path):
    tsx = "export default () => (\n  <board>\n"
    result = compile_board(tsx, tmp_path, timeout_s=120)
    assert result.ok is False
    assert result.errors
    assert len(result.stderr_tail.splitlines()) <= TAIL_LIMIT
    assert (tmp_path / "index.circuit.tsx").read_text(encoding="utf-8") == tsx


# ---------------------------------------------------------------------------
# errors tsci writes into circuit.json while exiting 0
# ---------------------------------------------------------------------------

def test_circuit_json_errors_from_the_empty_real_board():
    errors = circuit_json_errors(LIGHTNING / "circuit.json")
    assert len(errors) == 18
    assert errors[0] == CompileError(
        'Could not create chip "U1". Invalid props for chip "U1": '
        "supplierPartNumbers (Expected object, received array)"
    )
    assert [e.message.split(" ")[4] for e in errors[:5]] == ['"U1".', '"C1".', '"R1".', '"R2".', '"J1".']
    assert errors[5].message == 'Could not find port for selector ".C1 > .pin1". Component ".C1 > " not found'
    for err in errors:
        assert "\n" not in err.message and "Details:" not in err.message
        assert (err.line, err.column, err.file) == (0, 0, "index.circuit.tsx")
    assert parse_compile_errors(format_compile_errors(errors)) == errors


def test_circuit_json_warnings_are_not_errors():
    assert circuit_json_errors(ROOT / "tests" / "data" / "circuit_json" / "sensor_good.circuit.json") == []


def test_layout_errors_in_circuit_json_are_not_compile_errors(tmp_path):
    """blinky compiles with an autorouter pcb_port_not_connected_error; layout is checked later (V-13)."""
    import json

    path = tmp_path / "circuit.json"
    path.write_text(json.dumps([
        {"type": "pcb_port_not_connected_error", "message": "Port [D1.pin2] is not connected to net [GND] by a PCB trace."},
        {"type": "schematic_layout_error", "message": "overlap"},
        {"type": "source_no_power_pin_defined_warning", "message": "No power pin defined"},
    ]), encoding="utf-8")
    assert circuit_json_errors(path) == []


def test_zero_exit_with_errors_in_circuit_json_is_not_ok(tmp_path, monkeypatch):
    """tsci exits 0 and writes every file, but circuit.json says no component was created."""
    _install_tsci(
        tmp_path / "bin",
        textwrap.dedent(
            f"""
            import pathlib, shutil, sys
            args = sys.argv[1:]
            out = pathlib.Path(args[args.index("-o") + 1])
            fmt = args[args.index("-f") + 1]
            if fmt == "circuit-json":
                shutil.copy({str(LIGHTNING / "circuit.json")!r}, out)
            else:
                out.write_text("(" + fmt + " (version 20250114))\\n")
            """
        ),
    )
    _use_tsci(monkeypatch, tmp_path / "bin")
    result = compile_board("export default () => (<board />)", tmp_path / "work")
    assert result.ok is False
    assert result.errors == circuit_json_errors(LIGHTNING / "circuit.json")
    assert (result.kicad_sch, result.kicad_pcb, result.circuit_json) == ("", "", "")


def test_unreadable_circuit_json_is_not_ok(tmp_path, monkeypatch):
    _install_tsci(
        tmp_path / "bin",
        textwrap.dedent(
            """
            import pathlib, sys
            args = sys.argv[1:]
            pathlib.Path(args[args.index("-o") + 1]).write_text("not json\\n")
            """
        ),
    )
    _use_tsci(monkeypatch, tmp_path / "bin")
    result = compile_board("export default () => (<board />)", tmp_path / "work")
    assert result.ok is False
    assert "circuit.json" in result.errors[0].message


@pytest.mark.skipif(shutil.which("tsci") is None, reason="tsci not installed")
def test_real_tsci_empty_board_is_a_compile_error(tmp_path):
    tsx = (LIGHTNING / "index.circuit.tsx").read_text(encoding="utf-8")
    result = compile_board(tsx, tmp_path, timeout_s=180)
    assert result.ok is False
    assert "supplierPartNumbers (Expected object, received array)" in result.errors[0].message


@pytest.mark.skipif(shutil.which("tsci") is None, reason="tsci not installed")
def test_real_tsci_compiles_the_supplier_shape_codegen_teaches(tmp_path):
    """The same board with prompts/codegen.md's supplierPartNumbers shape compiles all 5 parts."""
    import json
    import re

    shape = 'supplierPartNumbers={{ jlcpcb: ["<lcsc cell>"] }}'
    assert shape in (ROOT / "prompts" / "codegen.md").read_text(encoding="utf-8")
    tsx = re.sub(
        r'supplierPartNumbers=\{\["(C\d+)"\]\}',
        lambda m: shape.replace("<lcsc cell>", m.group(1)),
        (LIGHTNING / "index.circuit.tsx").read_text(encoding="utf-8"),
    )
    assert tsx.count("jlcpcb: [") == 5
    result = compile_board(tsx, tmp_path, timeout_s=180)
    assert result.ok is True, result.errors
    elements = json.loads(Path(result.circuit_json).read_text(encoding="utf-8"))
    assert sorted(e["name"] for e in elements if e["type"] == "source_component") == ["C1", "J1", "R1", "R2", "U1"]
