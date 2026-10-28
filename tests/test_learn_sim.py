"""L-12: ngspice testbenches for decoupling and I2C pull-ups (DECISIONS L-2a, O-1c).

Every testbench is checked against a hand calculation written out here, and
has a known-good and a known-bad case, so a plot never shows physics the
numbers don't back. ngspice runs as a separate process; without it these skip.

Hand calculations (values from the testbenches' defaults, shown in the UI as assumptions):

Decoupling. Supply Vs = 3.3 V through wiring Lw = 20 nH, Rw = 0.05 ohm to the chip node.
Load: a DC resistor (10 mA) plus a current step dI = 50 mA with rise t_r = 1 ns.
- No cap: during the ramp V = Vs - Lw*dI/t_r, a 20e-9*0.05/1e-9 = 1.0 V droop.
- With C = 100 nF (ESR 0.01 ohm, ESL 0.4 nH, typical of 0402) next to the pin: the edge is
  carried by the cap, (Lw || ESL)*dI/t_r = 19.6 mV, and then the LC rings,
  dI*sqrt(Lw/C) = 0.05*sqrt(20e-9/100e-9) = 22.4 mV, a little less with the damping from Rw
  and ESR. Either way about 20 mV.
- Cap in series (supply -> cap -> chip): no DC path, so after power-up
  V(t) = Vs*exp(-t/(R_load*C)); at t = R_load*C = 330*100e-9 = 33 us, V = Vs/e = 1.21 V.
- PCB path L_p from the cap to the pin (1 nH/mm): on the edge, the chip sees the wiring and the
  cap path in parallel, so the droop is (Lw || (L_p + ESL))*dI/t_r. 20 mm: 10.1 nH -> 0.505 V;
  2 mm: 2.14 nH -> 107 mV.

I2C pull-up. Pull-up R to VDD = 3.3 V, bus capacitance C_bus = 100 pF, an open-drain switch
releases the line. 30%->70% rise time = R*C_bus*ln(0.7/0.3) = 0.8473*R*C_bus:
4.7 k -> 398 ns (inside standard mode's 1000 ns, outside fast mode's 300 ns; NXP UM10204,
Table 10); 1 k -> 84.7 ns. No pull-up: the line never reaches 30%.
"""
import math
import shutil

import pytest

from reflow.learn import sim

needs_ngspice = pytest.mark.skipif(sim.find_engine() is None, reason="no ngspice (CLI or KiCad's library)")

# Every test runs on each ngspice engine reflow can use: the ngspice CLI (e.g. Homebrew's) and
# KiCad's bundled libngspice. The hand calculations are the same for both.
ENGINES = {"cli": sim.find_cli_engine(), "kicad": sim.find_kicad_engine()}
REAL_FIND_ENGINE = sim.find_engine      # the engine fixture replaces sim.find_engine in every test


@pytest.fixture(autouse=True, params=sorted(ENGINES))
def engine(request, monkeypatch):
    found = ENGINES[request.param]
    if found is None:
        pytest.skip(f"{request.param} ngspice isn't available here")
    monkeypatch.setattr(sim, "find_engine", lambda: found)
    return found

LW, DI, TR, ESL = 20e-9, 0.05, 1e-9, 0.4e-9


# ---------------------------------------------------------------------------
# decoupling
# ---------------------------------------------------------------------------

@needs_ngspice
def test_no_decoupling_cap_droops_by_l_di_dt(tmp_path):
    result = sim.decoupling(sim.DecouplingBoard(cap_f=None), tmp_path, variant="broken")
    assert result.ran and result.exit_code == 0
    expected = LW * DI / TR                                     # 1.0 V
    assert result.measured["droop_v"] == pytest.approx(expected, rel=0.12)
    assert result.verdict == "bad"


@needs_ngspice
def test_a_100nf_cap_at_the_pin_holds_the_supply(tmp_path):
    result = sim.decoupling(sim.DecouplingBoard(cap_f=100e-9), tmp_path, variant="as_designed")
    ring = DI * math.sqrt(LW / 100e-9)                          # 22.4 mV
    assert result.measured["droop_v"] == pytest.approx(ring, rel=0.10)
    assert result.verdict == "good"


@needs_ngspice
def test_a_cap_in_series_starves_the_chip(tmp_path):
    result = sim.decoupling(sim.DecouplingBoard(cap_f=100e-9, cap_in_series=True), tmp_path, variant="broken")
    tau = 330 * 100e-9                                          # 33 us
    assert result.measured["v_at_tau"] == pytest.approx(3.3 / math.e, rel=0.10)   # 1.21 V
    assert result.measured["v_end"] < 0.2
    assert result.verdict == "bad"
    assert result.measured["tau_s"] == pytest.approx(tau)


@needs_ngspice
@pytest.mark.parametrize("path_mm, expected_v", [
    (20.0, (LW * (20e-9 + ESL) / (LW + 20e-9 + ESL)) * DI / TR),   # 0.505 V
    (2.0, (LW * (2e-9 + ESL) / (LW + 2e-9 + ESL)) * DI / TR),     # 107 mV
])
def test_the_layout_path_to_the_pin_adds_its_inductance(tmp_path, path_mm, expected_v):
    board = sim.DecouplingBoard(cap_f=100e-9, path_mm=path_mm)
    result = sim.decoupling(board, tmp_path, variant="as_designed")
    assert result.measured["droop_v"] == pytest.approx(expected_v, rel=0.15)
    assert any("1 nH per mm" in a for a in result.assumptions)


def test_every_decoupling_result_says_what_it_assumed(tmp_path):
    result = sim.decoupling(sim.DecouplingBoard(cap_f=100e-9), tmp_path, variant="as_designed")
    text = " ".join(result.assumptions)
    for needle in ("20 nH", "50 mA", "1 ns", "330"):
        assert needle in text


# ---------------------------------------------------------------------------
# I2C pull-ups
# ---------------------------------------------------------------------------

@needs_ngspice
@pytest.mark.parametrize("ohms", [4.7e3, 1e3])
def test_rise_time_is_0_847_rc(tmp_path, ohms):
    result = sim.i2c_pullup(sim.I2cBoard(pullup_ohm=ohms), tmp_path, variant="as_designed")
    expected = ohms * 100e-12 * math.log(0.7 / 0.3)
    assert result.measured["rise_30_70_s"] == pytest.approx(expected, rel=0.05)


@needs_ngspice
def test_4k7_on_100pf_meets_standard_mode_but_not_fast_mode(tmp_path):
    result = sim.i2c_pullup(sim.I2cBoard(pullup_ohm=4.7e3), tmp_path, variant="as_designed")
    assert result.verdict == "good"
    assert any("standard mode" in n and "fast mode" in n for n in result.notes)


@needs_ngspice
def test_a_47k_pull_up_is_too_slow_even_for_standard_mode(tmp_path):
    """0.8473 * 47k * 100 pF = 3.98 us, four times standard mode's 1000 ns (UM10204 Table 10)."""
    result = sim.i2c_pullup(sim.I2cBoard(pullup_ohm=47e3), tmp_path, variant="broken")
    assert result.measured["rise_30_70_s"] == pytest.approx(47e3 * 100e-12 * math.log(0.7 / 0.3), rel=0.05)
    assert result.verdict == "bad"
    assert "outside standard mode" in result.notes[0]


@needs_ngspice
def test_no_pull_up_never_rises(tmp_path):
    result = sim.i2c_pullup(sim.I2cBoard(pullup_ohm=None), tmp_path, variant="broken")
    assert result.ran
    assert result.measured["v_max_after_release"] < 0.3 * 3.3
    assert result.measured.get("rise_30_70_s") is None
    assert result.verdict == "bad"


# ---------------------------------------------------------------------------
# honesty and plumbing
# ---------------------------------------------------------------------------

def test_without_ngspice_nothing_is_plotted(tmp_path, monkeypatch):
    monkeypatch.setattr(sim, "find_engine", lambda: None)
    result = sim.i2c_pullup(sim.I2cBoard(pullup_ohm=4.7e3), tmp_path, variant="as_designed")
    assert result.ran is False and result.to_contract().signals == [] and result.verdict == "unknown"
    assert "ngspice" in result.notes[0]


@needs_ngspice
def test_the_deck_is_kept_and_the_result_is_a_strict_contract(tmp_path):
    from reflow.contracts import SimResult, from_dict, to_dict

    result = sim.decoupling(sim.DecouplingBoard(cap_f=100e-9), tmp_path, variant="as_designed")
    assert (tmp_path / "decoupling-as_designed.cir").is_file()
    assert result.deck_path.endswith("decoupling-as_designed.cir")
    contract = result.to_contract()
    assert from_dict(SimResult, to_dict(contract)) == contract
    assert contract.signals[0].unit == "V" and len(contract.signals[0].t) == len(contract.signals[0].v)


@needs_ngspice
def test_downsampling_keeps_the_worst_point(tmp_path):
    """A 1 ns spike must survive the thinning for the plot, or the plot would hide the droop."""
    result = sim.decoupling(sim.DecouplingBoard(cap_f=None), tmp_path, variant="broken")
    plotted = min(result.to_contract().signals[0].v)
    assert plotted == pytest.approx(3.3 - result.measured["droop_v"], abs=1e-6)
    assert len(result.to_contract().signals[0].v) <= 2 * sim.PLOT_POINTS



# ---------------------------------------------------------------------------
# which engine runs
# ---------------------------------------------------------------------------

def test_the_result_says_which_engine_ran(tmp_path, engine):
    result = sim.i2c_pullup(sim.I2cBoard(pullup_ohm=4.7e3), tmp_path, variant="as_designed")
    assert result.ran
    expected = "KiCad's bundled ngspice library" if engine.kind == "kicad" else "the ngspice command"
    assert any(expected in n for n in result.notes)


def test_the_cli_comes_first_then_kicads_library(monkeypatch, tmp_path):
    lib = tmp_path / "libngspice.0.dylib"
    lib.write_bytes(b"")
    monkeypatch.setenv("REFLOW_LIBNGSPICE", str(lib))
    monkeypatch.setenv("REFLOW_NGSPICE", "/opt/fake/ngspice")
    assert REAL_FIND_ENGINE() == sim.Engine("cli", "/opt/fake/ngspice")
    monkeypatch.delenv("REFLOW_NGSPICE")
    monkeypatch.setattr(sim.shutil, "which", lambda name: None)
    assert REAL_FIND_ENGINE() == sim.Engine("kicad", str(lib))


def test_kicads_library_is_found_next_to_kicad_cli(monkeypatch, tmp_path):
    app = tmp_path / "KiCad.app" / "Contents"
    (app / "MacOS").mkdir(parents=True)
    (app / "Frameworks").mkdir()
    (app / "MacOS" / "kicad-cli").write_text("", encoding="utf-8")
    (app / "Frameworks" / "libngspice.0.dylib").write_bytes(b"")
    monkeypatch.delenv("REFLOW_LIBNGSPICE", raising=False)
    monkeypatch.setattr("reflow.cli.find_kicad_cli", lambda: str(app / "MacOS" / "kicad-cli"))
    assert sim.find_kicad_engine() == sim.Engine("kicad", str(app / "Frameworks" / "libngspice.0.dylib"))


def test_with_no_engine_the_note_says_how_to_get_one(tmp_path, monkeypatch):
    monkeypatch.setattr(sim, "find_engine", lambda: None)
    result = sim.decoupling(sim.DecouplingBoard(cap_f=100e-9), tmp_path, variant="as_designed")
    assert result.ran is False
    assert "brew install ngspice" in result.notes[0] and "KiCad" in result.notes[0]
