import os, subprocess, tomllib
from pathlib import Path
import pytest
from reflow.cli import find_kicad_cli
from reflow.netlist import load_netlist

ROOT = Path(__file__).resolve().parents[1]
KICAD_CLI = find_kicad_cli()
FIXTURES = sorted({
    p.parent for p in (ROOT / "fixtures").rglob("*.kicad_sch")
    if not any(part.startswith(".") for part in p.relative_to(ROOT).parts)
})


def export_netlist(sch: Path, out: Path) -> Path:
    subprocess.run(
        [KICAD_CLI, "sch", "export", "netlist", "--format", "kicadsexpr", "-o", str(out), str(sch)],
        check=True, capture_output=True,
    )
    return out


@pytest.fixture(params=FIXTURES, ids=lambda p: p.name)
def board(request, tmp_path):
    if KICAD_CLI is None:
        pytest.skip("kicad-cli not found")  # CI's full job checks it's installed, so this can't hide there
    folder = request.param
    sch = next(folder.glob("*.kicad_sch"))
    nl = load_netlist(export_netlist(sch, tmp_path / "board.net"))
    exp_file = folder / "expected.toml"
    expected = tomllib.loads(exp_file.read_text()) if exp_file.exists() else {}
    return folder.name, nl, expected