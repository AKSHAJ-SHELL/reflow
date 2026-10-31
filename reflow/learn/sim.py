"""ngspice testbenches for learn mode.  Task L-12, written by the agent under O-1c; the human reviews it line by line.

Contract
--------
    find_engine() -> Engine | None                   # the ngspice command, else KiCad's bundled library
    find_cli_engine() / find_kicad_engine() -> Engine | None
    find_ngspice() -> str | None                     # REFLOW_NGSPICE, else ngspice on PATH
    decoupling(board: DecouplingBoard, workdir, *, variant) -> Bench
    i2c_pullup(board: I2cBoard, workdir, *, variant) -> Bench
    Bench.to_contract() -> contracts.SimResult

A circuit.json has no wiring parasitics, no IC load current and no
open-drain drivers, so simulating the raw board shows nothing. Each
testbench adds exactly that physics, around the board's own values (cap
value, pull-up value, supply voltage, and on the PCB the cap-to-pin path).
Every value the board doesn't contain is listed in `assumptions` and shown
with the plot.

Decoupling: Vs -> Rw, Lw (supply wiring) -> chip node. The load is a DC
resistor plus a fast current step. The cap (ESR, ESL, and the PCB path at
1 nH/mm) goes from the chip node to GND, or in series between the supply and
the chip for the series-cap mistake. Measured: the droop at the chip during
the step; with a series cap, the decay after power-up.

I²C pull-up: the pull-up to VDD, bus capacitance, and an open-drain switch
that releases the line. Measured: the 30%→70% rise time, compared with
UM10204's 1000 ns (standard mode) and 300 ns (fast mode).

The hand calculations each testbench is checked against are in
tests/test_learn_sim.py, which runs every testbench on each engine and checks
each measurement against an exact solution of the same circuit computed
without ngspice (tests/sim_reference.py) to within 0.01%. The time steps are
chosen for that: 10 ps across the decoupling step, RC/5000 for I²C, and
threshold crossings interpolated between samples, and `.options trtol=1` (with
ngspice's default of 7 the integration overshoots by 19% at a load-step corner
under an inductor).

Engines, in order:
1. The ngspice command: REFLOW_NGSPICE, else `ngspice` on PATH (e.g.
   Homebrew), run as `ngspice -b deck`.
2. KiCad's bundled ngspice library: REFLOW_LIBNGSPICE, else the libngspice
   that ships next to kicad-cli (KiCad 10 on macOS:
   Contents/Frameworks/libngspice*.dylib). It's driven through ctypes in a
   child process (`reflow.learn._libngspice`), never inside reflow's own
   process.
With neither, `ran` is False and nothing is plotted. Each result says which
engine ran.

Must never
----------
- plot a result ngspice didn't produce, or hide a spike when thinning the plot,
- present an assumed value as the board's,
- simulate a concept that has no validated testbench here.
"""
from __future__ import annotations

import math
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from reflow.contracts import SimResult, SimSignal

PLOT_POINTS = 1000
STEP_WINDOW_S = 1.5e-6          # decoupling: the load step and its LC ringing
NH_PER_MM = 1e-9
I2C_STANDARD_S, I2C_FAST_S = 1000e-9, 300e-9


@dataclass
class DecouplingBoard:
    cap_f: float | None             # None: no decoupling cap
    supply_v: float = 3.3
    cap_in_series: bool = False
    path_mm: float = 0.0            # cap-to-pin path on the PCB; 0 = schematic level
    path_estimated: bool = False    # True: straight-line pad distance (an unrouted board), a lower bound
    # assumptions (the board file has none of these)
    wiring_l: float = 20e-9
    wiring_r: float = 0.05
    cap_esr: float = 0.01
    cap_esl: float = 0.4e-9
    load_r: float = 330.0
    step_a: float = 0.05
    rise_s: float = 1e-9


@dataclass
class I2cBoard:
    pullup_ohm: float | None        # None: no pull-up
    supply_v: float = 3.3
    bus_c: float = 100e-12          # assumption


@dataclass
class Bench:
    concept: str
    variant: str
    ran: bool
    exit_code: int
    deck_path: str
    t: list[float] = field(default_factory=list)
    v: list[float] = field(default_factory=list)
    signal: str = ""
    measured: dict = field(default_factory=dict)
    verdict: str = "unknown"
    notes: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    engine: str = ""                # which ngspice ran, in words

    def to_contract(self) -> SimResult:
        signals = []
        if self.ran and self.t:
            t, v = _thin(self.t, self.v, PLOT_POINTS)
            signals = [SimSignal(name=self.signal, unit="V", t=t, v=v)]
        return SimResult(concept=self.concept, variant=self.variant, signals=signals, exit_code=self.exit_code,
                         deck_path=self.deck_path, ran=self.ran, verdict=self.verdict, notes=list(self.notes),
                         assumptions=list(self.assumptions))


@dataclass(frozen=True)
class Engine:
    kind: str                       # "cli" (the ngspice command) | "kicad" (KiCad's bundled libngspice)
    path: str


def find_ngspice() -> str | None:
    override = os.environ.get("REFLOW_NGSPICE", "").strip()
    return override or shutil.which("ngspice")


def find_cli_engine() -> Engine | None:
    found = find_ngspice()
    return Engine("cli", found) if found else None


def find_kicad_engine() -> Engine | None:
    override = os.environ.get("REFLOW_LIBNGSPICE", "").strip()
    if override:
        return Engine("kicad", override) if Path(override).is_file() else None
    import reflow.cli as cli

    kicad_cli = cli.find_kicad_cli()
    if kicad_cli is None:
        return None
    here = Path(kicad_cli).parent
    patterns = [(here.parent / "Frameworks", "libngspice*.dylib"),   # macOS app bundle
                (here.parent / "lib", "libngspice*.so*"),           # Linux
                (here, "*ngspice*.dll")]                            # Windows (bin/)
    for folder, pattern in patterns:
        found = sorted(folder.glob(pattern)) if folder.is_dir() else []
        if found:
            return Engine("kicad", str(found[0]))
    return None


def find_engine() -> Engine | None:
    return find_cli_engine() or find_kicad_engine()


# ---------------------------------------------------------------------------
# decoupling
# ---------------------------------------------------------------------------

def decoupling(board: DecouplingBoard, workdir, *, variant: str) -> Bench:
    return _with_engine_note(_decoupling(board, workdir, variant=variant))


def i2c_pullup(board: I2cBoard, workdir, *, variant: str) -> Bench:
    return _with_engine_note(_i2c_pullup(board, workdir, variant=variant))


def _with_engine_note(bench: Bench) -> Bench:
    if bench.ran and bench.engine:
        bench.notes.append(f"Simulated with {bench.engine}.")
    return bench


def _decoupling(board: DecouplingBoard, workdir, *, variant: str) -> Bench:
    b = board
    assumptions = [
        f"supply wiring {b.wiring_l * 1e9:g} nH and {b.wiring_r:g} Ω from the source to the chip",
        f"the chip draws {b.supply_v / b.load_r * 1e3:.0f} mA DC (a {b.load_r:g} Ω load) plus a {b.step_a * 1e3:g} mA step "
        f"that rises in {b.rise_s * 1e9:g} ns",
    ]
    if b.cap_f is not None:
        assumptions.append(f"the cap has {b.cap_esr:g} Ω ESR and {b.cap_esl * 1e9:g} nH ESL (typical 0402)")
    if b.path_mm:
        how = "straight-line pad distance (the board isn't routed), so a lower bound" if b.path_estimated else "routed trace length"
        assumptions.append(f"cap-to-pin path {b.path_mm:.1f} mm ({how}) at about 1 nH per mm")

    lines = ["* reflow decoupling testbench", f".param vs={b.supply_v}"]
    if b.cap_f is not None and b.cap_in_series:
        tau = b.load_r * b.cap_f
        stop = 3 * tau
        lines += [
            "VS vs 0 PULSE(0 {vs} 0 10n 10n 1 2)",
            f"RW vs n1 {b.wiring_r}", f"LW n1 a {b.wiring_l}",
            f"CS a chip {b.cap_f}", f"RL chip 0 {b.load_r}",
            f".tran {stop / 20000} {stop} 0 {stop / 20000}",
        ]
        t0, window = 0.0, (0.0, stop)
    else:
        # ngspice starts from the DC operating point (everything settled), so the step comes early and
        # the run only covers the step and its ringing, at a 10 ps maximum step (accuracy, L-12).
        t0, width = 100e-9, 1.0
        stop = t0 + STEP_WINDOW_S
        lines += [
            "VS vs 0 DC {vs}",
            f"RW vs n1 {b.wiring_r}", f"LW n1 chip {b.wiring_l}",
            f"RL chip 0 {b.load_r}",
            f"IL chip 0 PULSE(0 {b.step_a} {t0} {b.rise_s} {b.rise_s} {width} 1)",
        ]
        if b.cap_f is not None:
            lines += [f"LP chip c1 {b.cap_esl + b.path_mm * NH_PER_MM}", f"RC c1 c2 {b.cap_esr}", f"CD c2 0 {b.cap_f}"]
        lines += [f".tran 0.01n {stop} 0 0.01n"]
        window = (0.0, stop)
    bench = _run("decoupling", variant, lines, "v(chip)", workdir, window)
    bench.signal, bench.assumptions = "V(chip)", assumptions
    if not bench.ran:
        return bench

    if b.cap_f is not None and b.cap_in_series:
        tau = b.load_r * b.cap_f
        v_tau, v_end = _at(bench.t, bench.v, tau), bench.v[-1]
        bench.measured = {"tau_s": tau, "v_at_tau": v_tau, "v_end": v_end, "droop_v": b.supply_v - min(bench.v)}
        bench.verdict = "bad" if v_end < 0.9 * b.supply_v else "good"
        bench.notes = [f"With the cap in series there's no DC path: the chip's supply falls to {v_tau:.2f} V after "
                       f"{tau * 1e6:.0f} µs and {v_end:.2f} V after {3 * tau * 1e6:.0f} µs."]
        return bench

    during = [v for t, v in zip(bench.t, bench.v) if t >= t0]
    droop = b.supply_v - min(during)
    bench.measured = {"droop_v": droop, "v_min": min(during)}
    bench.verdict = "good" if droop < 0.05 * b.supply_v else "bad"
    bench.notes = [f"The supply at the chip dips {droop * 1e3:.0f} mV ({droop / b.supply_v:.1%} of {b.supply_v:g} V) "
                   f"when the load steps by {b.step_a * 1e3:g} mA; under 5% counts as holding."]
    return bench


# ---------------------------------------------------------------------------
# I2C pull-up
# ---------------------------------------------------------------------------

def _i2c_pullup(board: I2cBoard, workdir, *, variant: str) -> Bench:
    b = board
    release = 1e-6
    rc = (b.pullup_ohm or 0) * b.bus_c
    stop = release + max(10 * rc, 2e-6)
    lines = [
        "* reflow I2C pull-up testbench",
        f"VDD vdd 0 DC {b.supply_v}",
        f"CB sda 0 {b.bus_c}",
        "VC ctl 0 PULSE(1 0 1u 1n 1n 1 2)",
        "S1 sda 0 ctl 0 OD",
        ".model OD SW(Ron=20 Roff=1e12 Vt=0.5 Vh=0.1)",
        f".tran {(rc / 5000) if rc else 1e-9} {stop} 0 {(rc / 5000) if rc else 1e-9}",
    ]
    if b.pullup_ohm is not None:
        lines.insert(3, f"RP vdd sda {b.pullup_ohm}")
    bench = _run("i2c-pullup", variant, lines, "v(sda)", workdir, (0.0, stop))
    bench.signal = "V(SDA)"
    bench.assumptions = [f"bus capacitance {b.bus_c * 1e12:g} pF (the board file has none)",
                         "an open-drain driver (20 Ω on) releases the line at 1 µs"]
    if not bench.ran:
        return bench
    after = [(t, v) for t, v in zip(bench.t, bench.v) if t >= release]
    v_max = max(v for _, v in after)
    t30 = _crossing(after, 0.3 * b.supply_v)
    t70 = _crossing(after, 0.7 * b.supply_v)
    bench.measured = {"v_max_after_release": v_max}
    if t30 is None or t70 is None:
        bench.verdict = "bad"
        bench.notes = [f"The line never rises: it stays at {v_max:.2f} V after the driver lets go, so every bit reads 0."]
        return bench
    rise = t70 - t30
    bench.measured["rise_30_70_s"] = rise
    std, fast = rise <= I2C_STANDARD_S, rise <= I2C_FAST_S
    bench.verdict = "good" if std else "bad"
    bench.notes = [f"30%→70% rise time {rise * 1e9:.0f} ns: {'inside' if std else 'outside'} standard mode "
                   f"(1000 ns), {'inside' if fast else 'outside'} fast mode (300 ns), NXP UM10204 Table 10."]
    return bench


# ---------------------------------------------------------------------------
# ngspice
# ---------------------------------------------------------------------------

def _run(concept: str, variant: str, lines: list[str], vector: str, workdir, window) -> Bench:
    folder = Path(workdir)
    folder.mkdir(parents=True, exist_ok=True)
    deck = folder / f"{concept}-{variant}.cir"
    data = folder / f"{concept}-{variant}.txt"
    # trtol=1 (ngspice's default is 7): with the looser truncation-error control, trapezoidal integration
    # rang at the load step's first corner under an inductor (19% high on the 100 nF testbench). Gear
    # needed a 5x smaller step to match. tests/sim_reference.py has the exact solutions it's checked against.
    deck.write_text("\n".join(lines + [".options method=trap trtol=1", ".control", "run", f"wrdata {data} {vector}", "quit",
                                       ".endc", ".end", ""]),
                    encoding="utf-8")
    engine = find_engine()
    if engine is None:
        return Bench(concept, variant, False, -1, str(deck),
                     notes=["No ngspice found, so this can't be simulated: install it (brew install ngspice), "
                            "or install KiCad, whose bundled ngspice reflow can use."])
    if data.exists():
        data.unlink()
    if engine.kind == "cli":
        argv = [engine.path, "-b", str(deck)]
    else:
        argv = [sys.executable, "-m", "reflow.learn._libngspice", engine.path, str(deck), str(data), vector]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return Bench(concept, variant, False, -1, str(deck), notes=["ngspice took longer than 120 s; nothing to show."])
    if proc.returncode != 0 or not data.is_file():
        tail = (proc.stderr or proc.stdout).strip().splitlines()[-1:] or [""]
        return Bench(concept, variant, False, proc.returncode, str(deck), notes=[f"ngspice failed: {tail[0]}"])
    if engine.kind == "cli":
        label = f"the ngspice command ({engine.path})"
    else:
        banner = (proc.stdout.strip().splitlines() or ["ngspice"])[-1]
        label = f"KiCad's bundled ngspice library ({banner})"
    t, v = [], []
    for row in data.read_text(encoding="utf-8").split("\n"):
        cols = row.split()
        if len(cols) >= 2:
            tt = float(cols[0])
            if window[0] <= tt <= window[1]:
                t.append(tt)
                v.append(float(cols[1]))
    return Bench(concept, variant, True, proc.returncode, str(deck), t=t, v=v, engine=label)


def _crossing(points: list[tuple[float, float]], level: float) -> float | None:
    """The first time the signal rises through `level`, interpolated between the two samples around it."""
    for (t0, v0), (t1, v1) in zip(points, points[1:]):
        if v0 < level <= v1:
            return t0 + (t1 - t0) * (level - v0) / (v1 - v0)
    return None


def _at(t: list[float], v: list[float], when: float) -> float:
    for i in range(1, len(t)):
        if t[i] >= when:
            span = t[i] - t[i - 1]
            return v[i] if span == 0 else v[i - 1] + (v[i] - v[i - 1]) * (when - t[i - 1]) / span
    return v[-1]


def _thin(t: list[float], v: list[float], buckets: int) -> tuple[list[float], list[float]]:
    """At most 2*buckets points; each bucket keeps its minimum and its maximum, in time order."""
    if len(t) <= 2 * buckets:
        return list(t), list(v)
    out_t, out_v = [], []
    size = math.ceil(len(t) / buckets)
    for start in range(0, len(t), size):
        idx = range(start, min(start + size, len(t)))
        lo = min(idx, key=lambda i: v[i])
        hi = max(idx, key=lambda i: v[i])
        for i in sorted({lo, hi}):
            out_t.append(t[i])
            out_v.append(v[i])
    return out_t, out_v
