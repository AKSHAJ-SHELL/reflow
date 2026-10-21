"""V-11: pin maps from vendor pin data, then the KiCad symbol library.

Inputs in tests/data/pinmaps/ (licences beside them):
- st/mcu/STM32F103C(8-B)Tx.xml: ST STM32_open_pin_data, BSD-3-Clause, unmodified.
- kicad/*.kicad_sym: four unmodified symbols from KiCad 10.0.5's libraries,
  CC-BY-SA-4.0 WITH KiCad-libraries-exception.

Where the expected pins come from:
- MCP9808: Microchip DS20005095B, Table 3-1 (p.11), MSOP column, read directly.
- STM32F103C8 (LQFP48): ST's own published pin data. Three independent sources
  agree on every pin listed below: ST's XML, the EasyEDA symbol for LCSC C8734,
  and the KiCad symbol. ST's datasheet DS5319 itself could not be downloaded
  when these tests were written, so it was not read directly.
"""
import shutil
from pathlib import Path

import pytest

from reflow.cli import find_kicad_cli
from reflow.contracts import PIN_KINDS
from reflow.parts.pinmap import (
    PinMapError,
    base_name,
    compare_pin_maps,
    from_kicad_symbol,
    from_st_pin_data,
    import_pin_map,
)

DATA = Path(__file__).resolve().parent / "data" / "pinmaps"
KICAD = DATA / "kicad"
ST = DATA / "st"

MCP9808_DATASHEET = [  # DS20005095B Table 3-1, MSOP
    ("1", "SDA"), ("2", "SCL"), ("3", "ALERT"), ("4", "GND"),
    ("5", "A2"), ("6", "A1"), ("7", "A0"), ("8", "VDD"),
]
STM32_POWER_RESET_BOOT = {
    "1": ("VBAT", "power"), "7": ("NRST", "input"), "8": ("VSSA", "ground"), "9": ("VDDA", "power"),
    "23": ("VSS", "ground"), "24": ("VDD", "power"), "35": ("VSS", "ground"), "36": ("VDD", "power"),
    "44": ("BOOT0", "input"), "47": ("VSS", "ground"), "48": ("VDD", "power"),
}


def _by_number(pin_map):
    return {p.number: p for p in pin_map.pins}


def _symbol_lib(tmp_path: Path, body: str, name: str = "Test.kicad_sym") -> Path:
    (tmp_path / name).write_text(f"(kicad_symbol_lib (version 20251024) {body})", encoding="utf-8")
    return tmp_path


def _pin(etype: str, name: str, number: str) -> str:
    return f'(pin {etype} line (at 0 0 0) (length 2.54) (name "{name}") (number "{number}"))'


# ---------------------------------------------------------------------------
# KiCad symbols
# ---------------------------------------------------------------------------

def test_kicad_mcp9808_matches_the_datasheet_table():
    pin_map = from_kicad_symbol("Sensor_Temperature:MCP9808_MSOP", symbols_dir=KICAD)
    assert [(p.number, p.name.upper()) for p in pin_map.pins] == MCP9808_DATASHEET
    pins = _by_number(pin_map)
    assert pins["8"].kind == "power"
    assert pins["4"].kind == "ground"


def test_kicad_source_records_what_the_library_says():
    """The library's Datasheet link for MCP9808 is MCP9804's document (22203b).
    The importer reports the link as written; it does not correct it."""
    pin_map = from_kicad_symbol("Sensor_Temperature:MCP9808_MSOP", symbols_dir=KICAD)
    assert pin_map.source.locator == "Sensor_Temperature:MCP9808_MSOP"
    assert "KiCad" in pin_map.source.doc
    assert pin_map.source.url.endswith("22203b.pdf")


def test_kicad_kinds_follow_the_electrical_type(tmp_path):
    body = '(symbol "T" ' + " ".join([
        _pin("power_in", "V_{DD}", "1"), _pin("power_in", "GND", "2"), _pin("input", "EN", "3"),
        _pin("output", "OUT", "4"), _pin("bidirectional", "SDA", "5"), _pin("tri_state", "MISO", "6"),
        _pin("open_collector", "~{INT}", "7"), _pin("no_connect", "NC", "8"), _pin("passive", "EP", "9"),
        _pin("passive", "VSS", "10"), _pin("passive", "XTAL", "11"), _pin("power_out", "VOUT", "12"),
    ]) + ")"
    pin_map = from_kicad_symbol("Test:T", symbols_dir=_symbol_lib(tmp_path, body))
    kinds = {p.number: (p.name, p.kind) for p in pin_map.pins}
    assert kinds == {
        "1": ("VDD", "power"), "2": ("GND", "ground"), "3": ("EN", "input"), "4": ("OUT", "output"),
        "5": ("SDA", "io"), "6": ("MISO", "io"), "7": ("INT", "open_drain_out"), "8": ("NC", "nc"),
        "9": ("EP", "thermal_pad"), "10": ("VSS", "ground"), "11": ("XTAL", "io"), "12": ("VOUT", "output"),
    }
    assert all(p.kind in PIN_KINDS for p in pin_map.pins)
    assert any("11" in note and "passive" in note for note in pin_map.notes)


def test_pins_in_several_units_are_collected_and_identical_copies_fold(tmp_path):
    body = ('(symbol "T" (symbol "T_0_1" ' + _pin("power_in", "VDD", "1") + ") "
            '(symbol "T_1_1" ' + _pin("input", "A", "2") + ") "
            '(symbol "T_1_2" ' + _pin("input", "A", "2") + "))")
    pin_map = from_kicad_symbol("Test:T", symbols_dir=_symbol_lib(tmp_path, body))
    assert [(p.number, p.name) for p in pin_map.pins] == [("1", "VDD"), ("2", "A")]


def test_one_pin_number_with_two_names_raises(tmp_path):
    body = '(symbol "T" ' + _pin("input", "A", "2") + " " + _pin("input", "B", "2") + ")"
    with pytest.raises(PinMapError, match="2"):
        from_kicad_symbol("Test:T", symbols_dir=_symbol_lib(tmp_path, body))


@pytest.mark.parametrize("lib_id", ["Sensor_Temperature:NOPE", "Nope:MCP9808_MSOP", "no_colon"])
def test_unknown_symbol_raises(lib_id):
    with pytest.raises(PinMapError):
        from_kicad_symbol(lib_id, symbols_dir=KICAD)


def test_symbol_dir_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("REFLOW_KICAD_SYMBOL_DIR", str(KICAD))
    assert len(from_kicad_symbol("Sensor_Temperature:MCP9808_MSOP").pins) == 8


@pytest.mark.skipif(find_kicad_cli() is None, reason="kicad-cli not found")
def test_installed_kicad_library_is_found_next_to_kicad_cli(monkeypatch):
    monkeypatch.delenv("REFLOW_KICAD_SYMBOL_DIR", raising=False)
    assert len(from_kicad_symbol("MCU_ST_STM32F1:STM32F103C8Tx").pins) == 48


# ---------------------------------------------------------------------------
# ST pin data
# ---------------------------------------------------------------------------

def test_st_stm32f103c8_power_reset_and_boot_pins():
    pin_map = from_st_pin_data("STM32F103C8T6", st_dir=ST)
    pins = _by_number(pin_map)
    assert len(pins) == 48
    for number, (name, kind) in STM32_POWER_RESET_BOOT.items():
        assert (pins[number].name, pins[number].kind) == (name, kind), number
    others = {p.kind for n, p in pins.items() if n not in STM32_POWER_RESET_BOOT}
    assert others == {"io"}
    assert pin_map.package == "LQFP48"
    assert pin_map.source.locator == "mcu/STM32F103C(8-B)Tx.xml"


@pytest.mark.parametrize("mpn", ["STM32F103C8T6", "STM32F103CBT6", "STM32F103C8T7", "STM32F103C8T6TR", "stm32f103c8t6"])
def test_st_part_numbers_match_the_ref_name_pattern(mpn):
    assert from_st_pin_data(mpn, st_dir=ST).part == mpn


@pytest.mark.parametrize("mpn", ["STM32F103C6T6", "STM32F103R8T6", "STM32F103C8U6", "MCP9808"])
def test_st_part_with_no_file_raises(mpn):
    with pytest.raises(PinMapError, match=mpn):
        from_st_pin_data(mpn, st_dir=ST)


def test_st_part_matching_two_files_raises(tmp_path):
    (tmp_path / "mcu").mkdir()
    src = ST / "mcu" / "STM32F103C(8-B)Tx.xml"
    shutil.copy(src, tmp_path / "mcu" / "STM32F103C(8-B)Tx.xml")
    shutil.copy(src, tmp_path / "mcu" / "STM32F103C8Tx.xml")
    with pytest.raises(PinMapError, match="two|more than one"):
        from_st_pin_data("STM32F103C8T6", st_dir=tmp_path)


def test_st_unknown_pin_type_raises(tmp_path):
    (tmp_path / "mcu").mkdir()
    text = (ST / "mcu" / "STM32F103C(8-B)Tx.xml").read_text(encoding="utf-8")
    assert 'Type="Boot"' in text
    (tmp_path / "mcu" / "STM32F103C(8-B)Tx.xml").write_text(text.replace('Type="Boot"', 'Type="Weird"'), encoding="utf-8")
    with pytest.raises(PinMapError, match="Weird"):
        from_st_pin_data("STM32F103C8T6", st_dir=tmp_path)


# ---------------------------------------------------------------------------
# comparing sources and choosing one
# ---------------------------------------------------------------------------

def test_base_name_drops_the_alternate_function_and_case():
    assert base_name("PC14-OSC32_IN") == "PC14"
    assert base_name("PA0-WKUP") == "PA0"
    assert base_name("Alert") == "ALERT"
    assert base_name("VDD") == "VDD"


def test_st_and_kicad_agree_on_the_stm32f103c8():
    st = from_st_pin_data("STM32F103C8T6", st_dir=ST)
    kicad = from_kicad_symbol("MCU_ST_STM32F1:STM32F103C8Tx", symbols_dir=KICAD)
    assert compare_pin_maps(st, kicad) == []
    notes = " ".join(kicad.notes)
    assert "35" in notes and "47" in notes        # KiCad types these two VSS pins passive


def test_import_prefers_vendor_data_and_checks_it_against_kicad():
    result = import_pin_map("STM32F103C8T6", st_dir=ST,
                            kicad_lib_id="MCU_ST_STM32F1:STM32F103C8Tx", symbols_dir=KICAD)
    assert result.pin_map.source.doc.startswith("STMicroelectronics")
    assert result.checked_against is not None and "KiCad" in result.checked_against.doc
    assert result.disagreements == []


def test_a_disagreement_between_sources_is_reported(tmp_path):
    """Swap VSS/VDD on pins 23 and 24 in a copy of the KiCad symbol."""
    text = (KICAD / "MCU_ST_STM32F1.kicad_sym").read_text(encoding="utf-8")
    marker_vss, marker_vdd = '(number "23"', '(number "24"'
    assert marker_vss in text and marker_vdd in text
    text = text.replace(marker_vss, '(number "__A"').replace(marker_vdd, '(number "23"').replace('(number "__A"', '(number "24"')
    (tmp_path / "MCU_ST_STM32F1.kicad_sym").write_text(text, encoding="utf-8")
    result = import_pin_map("STM32F103C8T6", st_dir=ST,
                            kicad_lib_id="MCU_ST_STM32F1:STM32F103C8Tx", symbols_dir=tmp_path)
    joined = "\n".join(result.disagreements)
    assert "pin 23" in joined and "pin 24" in joined
    assert result.pin_map.source.doc.startswith("STMicroelectronics")   # vendor data still wins


def test_a_pin_missing_from_one_source_is_reported(tmp_path):
    body = '(symbol "T" ' + _pin("power_in", "VDD", "1") + ")"
    one = from_kicad_symbol("Test:T", symbols_dir=_symbol_lib(tmp_path, body))
    body2 = '(symbol "T" ' + _pin("power_in", "VDD", "1") + " " + _pin("input", "EN", "2") + ")"
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    two = from_kicad_symbol("Test:T", symbols_dir=_symbol_lib(other_dir, body2))
    assert any("pin 2" in d for d in compare_pin_maps(one, two))


def test_import_falls_back_to_kicad_without_vendor_data():
    result = import_pin_map("MCP9808T-E/MS", kicad_lib_id="Sensor_Temperature:MCP9808_MSOP", symbols_dir=KICAD)
    assert "KiCad" in result.pin_map.source.doc
    assert result.checked_against is None and result.disagreements == []


def test_import_with_no_source_raises(monkeypatch):
    monkeypatch.delenv("REFLOW_ST_PIN_DATA", raising=False)
    with pytest.raises(PinMapError, match="MCP9808"):
        import_pin_map("MCP9808T-E/MS")
