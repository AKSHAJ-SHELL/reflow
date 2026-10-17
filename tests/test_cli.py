import json
from pathlib import Path

import pytest

from reflow.cli import find_kicad_cli, main

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"

pytestmark = pytest.mark.skipif(find_kicad_cli() is None, reason="kicad-cli not found")


def run(capsys, *argv):
    code = main(["check", *argv])
    out, err = capsys.readouterr()
    return code, out + err


def test_good_board_passes(capsys):
    code, out = run(capsys, str(FIXTURES / "sensor_good"))
    assert code == 0
    assert "No issues found" in out


def test_series_cap_fails(capsys):
    code, out = run(capsys, str(FIXTURES / "bad_series_cap"))
    assert code == 1
    assert "decoupling.series" in out


def test_floating_addr_fails(capsys):
    code, out = run(capsys, str(FIXTURES / "bad_floating_addr"))
    assert code == 1
    assert "address.floating" in out


def test_json_output(capsys):
    code = main(["check", str(FIXTURES / "bad_no_pullups"), "--json"])
    out, _ = capsys.readouterr()
    data = json.loads(out)
    assert code == 1
    assert data["violations"][0]["rule_id"] == "i2c.missing_pullup"
    assert data["errors"] >= 1


def test_missing_path(capsys):
    code, _ = run(capsys, str(FIXTURES / "does_not_exist"))
    assert code == 2
