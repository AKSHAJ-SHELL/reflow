"""L-12: ngspice testbenches for decoupling and I2C pull-ups (DECISIONS L-2a, O-1c).

Every measurement is checked against the **exact** solution of the same circuit,
computed without ngspice (tests/sim_reference.py: closed forms, and matrix-exponential
propagation of the circuit's state equations), to within 0.0001%. Every testbench
runs on each ngspice engine reflow can use. Each one also has a known-good and a
known-bad case, so a plot never shows physics the numbers don't back.

The textbook formulas shown to the user as the explanation are approximations of
those exact answers. Their gaps are pinned down at the end of this file.

The testbench values (shown in the UI as assumptions): Vs = 3.3 V; wiring Lw = 20 nH,
Rw = 0.05 ohm; load 330 ohm DC plus a 50 mA step rising in 1 ns; cap ESR 0.01 ohm,
ESL 0.4 nH; PCB path 1 nH/mm; I2C bus 100 pF, open-drain switch 20 ohm on / 1e12 off.
"""
import math

import pytest

import sim_reference as ref
from reflow.learn import sim

needs_ngspice = pytest.mark.skipif(sim.find_engine() is None, reason="no ngspice (CLI or KiCad's library)")

# Every test runs on each ngspice engine reflow can use: the ngspice CLI (e.g. Homebrew's) and
# KiCad's bundled libngspice. The exact answers are the same for both.
ENGINES = {"cli": sim.find_cli_engine(), "kicad": sim.find_kicad_engine()}
REAL_FIND_ENGINE = sim.find_engine      # the engine fixture replaces sim.find_engine in every test


@pytest.fixture(autouse=True, params=sorted(ENGINES))
def engine(request, monkeypatch):
    found = ENGINES[request.param]
    if found is None:
        pytest.skip(f"{request.param} ngspice isn't available here")
    monkeypatch.setattr(sim, "find_engine", lambda: found)
    return found


VS, RW, LW, RL, DI, TR, ESR, ESL = 3.3, 0.05, 20e-9, 330.0, 0.05, 1e-9, 0.01, 0.4e-9
EXACT = 1e-6                      # simulated vs exact: 0.0001%; observed worst 0.000004%


def shunt(cap_f, branch_l):
    return ref.droop_shunt(VS, RW, LW, RL, DI, TR, cap_f, ESR, branch_l, sim.STEP_WINDOW_S)


# ---------------------------------------------------------------------------
# decoupling
# ---------------------------------------------------------------------------

@needs_ngspice
def test_no_decoupling_cap_droops_exactly_as_the_circuit_equations_say(tmp_path):
    result = sim.decoupling(sim.DecouplingBoard(cap_f=None), tmp_path, variant="broken")
    assert result.ran and result.exit_code == 0
    assert result.measured["droop_v"] == pytest.approx(ref.droop_no_cap(VS, RW, LW, RL, DI, TR), rel=EXACT)
    assert result.verdict == "bad"


@needs_ngspice
def test_a_100nf_cap_at_the_pin_holds_the_supply(tmp_path):
    result = sim.decoupling(sim.DecouplingBoard(cap_f=100e-9), tmp_path, variant="as_designed")
    assert result.measured["droop_v"] == pytest.approx(shunt(100e-9, ESL), rel=EXACT)
    assert result.verdict == "good"


@needs_ngspice
def test_a_cap_in_series_starves_the_chip(tmp_path):
    result = sim.decoupling(sim.DecouplingBoard(cap_f=100e-9, cap_in_series=True), tmp_path, variant="broken")
    tau = RL * 100e-9                                           # 33 us
    at_tau, at_end = ref.series_cap(VS, RW, LW, RL, 100e-9, 10e-9, tau, 3 * tau)
    assert result.measured["v_at_tau"] == pytest.approx(at_tau, rel=EXACT)
    assert result.measured["v_end"] == pytest.approx(at_end, rel=EXACT)
    assert result.verdict == "bad"
    assert result.measured["tau_s"] == pytest.approx(tau)


@needs_ngspice
@pytest.mark.parametrize("path_mm", [20.0, 2.0])
def test_the_layout_path_to_the_pin_adds_its_inductance(tmp_path, path_mm):
    board = sim.DecouplingBoard(cap_f=100e-9, path_mm=path_mm)
    result = sim.decoupling(board, tmp_path, variant="as_designed")
    assert result.measured["droop_v"] == pytest.approx(shunt(100e-9, ESL + path_mm * 1e-9), rel=EXACT)
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
@pytest.mark.parametrize("ohms", [4.7e3, 1e3, 47e3])
def test_rise_time_is_exactly_the_rc_exponentials(tmp_path, ohms):
    result = sim.i2c_pullup(sim.I2cBoard(pullup_ohm=ohms), tmp_path, variant="as_designed")
    assert result.measured["rise_30_70_s"] == pytest.approx(ref.rise_30_70(ohms, 100e-12, VS, 1e12), rel=EXACT)


@needs_ngspice
def test_4k7_on_100pf_meets_standard_mode_but_not_fast_mode(tmp_path):
    result = sim.i2c_pullup(sim.I2cBoard(pullup_ohm=4.7e3), tmp_path, variant="as_designed")
    assert result.verdict == "good"
    assert any("standard mode" in n and "fast mode" in n for n in result.notes)


@needs_ngspice
def test_a_47k_pull_up_is_too_slow_even_for_standard_mode(tmp_path):
    """3.98 us, four times standard mode's 1000 ns (UM10204 Table 10)."""
    result = sim.i2c_pullup(sim.I2cBoard(pullup_ohm=47e3), tmp_path, variant="broken")
    assert result.verdict == "bad"
    assert "outside standard mode" in result.notes[0]


@needs_ngspice
def test_no_pull_up_never_rises(tmp_path):
    result = sim.i2c_pullup(sim.I2cBoard(pullup_ohm=None), tmp_path, variant="broken")
    assert result.ran
    assert result.measured["v_max_after_release"] < 0.3 * VS
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


# ---------------------------------------------------------------------------
# the textbook formulas shown to the user, against the exact answers
# ---------------------------------------------------------------------------
# These don't run ngspice. They pin down how far each one-line formula is from the
# exact solution of the testbench, so the explanation next to a plot is honest
# about being an approximation. The simulation itself is held to EXACT above.

def test_l_di_dt_is_0_27_percent_under_the_exact_no_cap_droop():
    exact = ref.droop_no_cap(VS, RW, LW, RL, DI, TR)          # 1.00270 V: adds the Rw drop and the load
    assert LW * DI / TR == pytest.approx(exact, rel=0.003)


def test_the_lc_ring_formula_is_0_4_percent_under_the_exact_100nf_droop():
    exact = shunt(100e-9, ESL)                                # 22.449 mV
    assert DI * math.sqrt(LW / 100e-9) == pytest.approx(exact, rel=0.005)


@pytest.mark.parametrize("path_mm, gap", [(20.0, 0.003), (2.0, 0.011)])
def test_parallel_inductance_formula_is_within_its_gap_of_the_exact_pcb_droop(path_mm, gap):
    branch = ESL + path_mm * 1e-9
    formula = LW * branch / (LW + branch) * DI / TR
    assert formula == pytest.approx(shunt(100e-9, branch), rel=gap)


def test_vs_over_e_is_0_02_percent_off_the_exact_series_cap_voltage():
    tau = RL * 100e-9
    exact, _ = ref.series_cap(VS, RW, LW, RL, 100e-9, 10e-9, tau, 3 * tau)
    assert VS / math.e == pytest.approx(exact, rel=0.0003)


def test_0_847_rc_is_the_exact_rise_time_to_eight_digits():
    assert 4.7e3 * 100e-12 * math.log(7 / 3) == pytest.approx(ref.rise_30_70(4.7e3, 100e-12, VS, 1e12), rel=1e-7)


def test_the_reference_solver_agrees_with_the_closed_form():
    """The matrix-exponential solver, with the cap branch effectively removed, matches the no-cap
    closed form, so the two exact references check each other."""
    general = ref.droop_shunt(VS, RW, LW, RL, DI, TR, 1e-18, 1e6, 1.0, 50e-9)
    assert general == pytest.approx(ref.droop_no_cap(VS, RW, LW, RL, DI, TR), rel=1e-7)
