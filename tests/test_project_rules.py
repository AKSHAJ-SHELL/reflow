"""V-21: rules.toml parser and `reflow rules check` (DECISIONS V-2).

Pin names are checked against V-11 pin maps built from the test pin data in
tests/data/pinmaps/ (KiCad symbols, ST pin data). The example rules file is
the accepted V-2 example for the MCP9808 board.
"""
from pathlib import Path

import pytest

import reflow.cli as cli
from reflow.parts.pinmap import from_kicad_symbol, from_st_pin_data
from reflow.project_rules import RulesFileError, check_rules, load_rules

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "docs" / "proposals" / "examples" / "rules.toml"
KICAD = ROOT / "tests" / "data" / "pinmaps" / "kicad"
ST = ROOT / "tests" / "data" / "pinmaps" / "st"


def _mcp9808():
    return {"U1": from_kicad_symbol("Sensor_Temperature:MCP9808_MSOP", symbols_dir=KICAD)}


def _rules(tmp_path: Path, *bodies: str) -> Path:
    path = tmp_path / "rules.toml"
    path.write_text("\n".join(f"[[rule]]\n{body}" for body in bodies), encoding="utf-8")
    return path


GOOD = 'on = "U1.VDD"\nneed = "cap"\nto = "GND"\nvalue = "100nF"\nsource = "datasheet 6.1"\nwhy = "steady supply"'


# ---------------------------------------------------------------------------
# the example passes
# ---------------------------------------------------------------------------

def test_the_example_rules_file_loads():
    rules = load_rules(EXAMPLE)
    assert len(rules.rule) == 7
    assert {r.need for r in rules.rule} == {"cap", "pullup", "tie", "open"}


def test_the_example_checks_without_errors_and_warns_about_gnd():
    result = check_rules(load_rules(EXAMPLE), _mcp9808())
    assert result.errors == []
    assert any("U1.GND" in w for w in result.warnings)       # no rule says anything about GND
    assert not any("U1.VDD" in w for w in result.warnings)   # VDD has its cap rule


# ---------------------------------------------------------------------------
# file and field errors
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("missing", ["why", "source"])
def test_why_and_source_are_required(tmp_path, missing):
    body = "\n".join(line for line in GOOD.splitlines() if not line.startswith(missing))
    with pytest.raises(RulesFileError, match=missing):
        load_rules(_rules(tmp_path, body))


@pytest.mark.parametrize("field", ["why", "source"])
def test_why_and_source_must_say_something(tmp_path, field):
    body = GOOD.replace(f'{field} = "', f'{field} = "  ').replace('"  steady supply"', '"  "').replace('"  datasheet 6.1"', '"  "')
    result = check_rules(load_rules(_rules(tmp_path, body)), _mcp9808())
    assert any(field in e for e in result.errors)


def test_an_unknown_key_is_refused(tmp_path):
    with pytest.raises(RulesFileError, match="colour"):
        load_rules(_rules(tmp_path, GOOD + '\ncolour = "red"'))


def test_a_toml_syntax_error_is_refused(tmp_path):
    path = tmp_path / "rules.toml"
    path.write_text("[[rule]\non = ", encoding="utf-8")
    with pytest.raises(RulesFileError):
        load_rules(path)


def test_a_missing_file_is_refused(tmp_path):
    with pytest.raises(RulesFileError):
        load_rules(tmp_path / "nope.toml")


@pytest.mark.parametrize("body, fragment", [
    (GOOD.replace('need = "cap"', 'need = "bypass"'), "need"),
    (GOOD.replace('to = "GND"\n', ""), "to"),
    ('on = "U1.ALERT"\nneed = "open"\nto = "GND"\nsource = "s"\nwhy = "w"', "to"),
    (GOOD.replace('value = "100nF"', 'value = "fast"'), "value"),
    (GOOD.replace('value = "100nF"', 'value = "1uF..100nF"'), "value"),
    (GOOD.replace('on = "U1.VDD"', 'on = "VDD"'), "on"),
])
def test_field_errors_are_reported(tmp_path, body, fragment):
    result = check_rules(load_rules(_rules(tmp_path, body)), _mcp9808())
    assert any(fragment in e for e in result.errors), result.errors


def test_a_value_range_and_a_single_value_are_both_fine(tmp_path):
    rules = load_rules(_rules(tmp_path, GOOD.replace('"100nF"', '"100nF..1uF"'), GOOD.replace('"100nF"', '"0.1uF"')))
    assert check_rules(rules, _mcp9808()).errors == []


# ---------------------------------------------------------------------------
# pins against the pin map
# ---------------------------------------------------------------------------

def test_an_unknown_pin_is_an_error_that_names_the_source(tmp_path):
    result = check_rules(load_rules(_rules(tmp_path, GOOD.replace("U1.VDD", "U1.VCC"))), _mcp9808())
    assert any("U1.VCC" in e and "MCP9808_MSOP" in e for e in result.errors), result.errors


def test_a_pin_can_be_named_by_its_number(tmp_path):
    assert check_rules(load_rules(_rules(tmp_path, GOOD.replace("U1.VDD", "U1.8"))), _mcp9808()).errors == []


def test_a_part_with_no_pin_map_is_a_warning_not_an_error(tmp_path):
    result = check_rules(load_rules(_rules(tmp_path, GOOD.replace("U1.VDD", "U7.VDD"))), _mcp9808())
    assert result.errors == []
    assert any("U7" in w and "pin map" in w for w in result.warnings)


def test_uncovered_power_reset_and_boot_pins_are_warned_about(tmp_path):
    maps = {"U1": from_st_pin_data("STM32F103C8T6", st_dir=ST)}
    rules = load_rules(_rules(tmp_path, *[GOOD.replace("U1.VDD", f"U1.{n}") for n in ("24", "36", "48")]))
    result = check_rules(rules, maps)
    assert result.errors == []
    warned = " ".join(result.warnings)
    for name in ("VBAT", "VDDA", "VSSA", "NRST", "BOOT0"):
        assert name in warned, name
    assert "U1.VDD (pin 24)" not in warned


# ---------------------------------------------------------------------------
# the command
# ---------------------------------------------------------------------------

def test_reflow_rules_check_passes_the_example(monkeypatch, capsys):
    monkeypatch.setenv("REFLOW_KICAD_SYMBOL_DIR", str(KICAD))
    code = cli.main(["rules", "check", str(EXAMPLE), "--symbol", "U1=Sensor_Temperature:MCP9808_MSOP"])
    out = capsys.readouterr().out
    assert code == 0
    assert "7 rules" in out and "0 errors" in out and "U1.GND" in out


def test_reflow_rules_check_with_an_st_part(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("REFLOW_ST_PIN_DATA", str(ST))
    path = _rules(tmp_path, GOOD.replace("U1.VDD", "U1.BOOT0").replace('need = "cap"', 'need = "pulldown"'))
    assert cli.main(["rules", "check", str(path), "--mpn", "U1=STM32F103C8T6"]) == 0
    assert "NRST" in capsys.readouterr().out


def test_reflow_rules_check_exits_1_on_rule_errors(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("REFLOW_KICAD_SYMBOL_DIR", str(KICAD))
    path = _rules(tmp_path, GOOD.replace("U1.VDD", "U1.VCC"))
    assert cli.main(["rules", "check", str(path), "--symbol", "U1=Sensor_Temperature:MCP9808_MSOP"]) == 1
    assert "U1.VCC" in capsys.readouterr().out


@pytest.mark.parametrize("args", [["nope.toml"], [str(EXAMPLE), "--symbol", "U1"], [str(EXAMPLE), "--symbol", "U1=Nope:Nope"]])
def test_reflow_rules_check_exits_2_on_unusable_input(args, monkeypatch, capsys):
    monkeypatch.setenv("REFLOW_KICAD_SYMBOL_DIR", str(KICAD))
    assert cli.main(["rules", "check", *args]) == 2
    assert "reflow:" in capsys.readouterr().err
