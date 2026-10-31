"""Exact solutions of reflow's ngspice testbenches, computed without ngspice.

Each testbench in reflow/learn/sim.py is a small linear circuit driven by
piecewise-linear sources. Here the same circuits are written as their state
equations x' = A x + b(t), and solved exactly between the corners of the
sources with a matrix exponential (scaling and squaring, a Taylor series on a
matrix whose norm is below 1/2, so the truncation error is far below double
precision). The ramp inputs become extra states with constant derivatives,
so propagation over any interval is exact. The I2C rise time and the no-cap
droop also have closed forms, which are used directly.

This is a test helper: an independent check on the simulator, not part of reflow.
"""
from __future__ import annotations

import math

# ---------------------------------------------------------------------------
# small dense linear algebra
# ---------------------------------------------------------------------------


def _matmul(a, b):
    n, m, p = len(a), len(b), len(b[0])
    return [[sum(a[i][k] * b[k][j] for k in range(m)) for j in range(p)] for i in range(n)]


def _matvec(a, x):
    return [sum(a[i][k] * x[k] for k in range(len(x))) for i in range(len(a))]


def _expm(a, dt):
    """exp(a*dt) by scaling and squaring."""
    n = len(a)
    m = [[a[i][j] * dt for j in range(n)] for i in range(n)]
    norm = max(sum(abs(v) for v in row) for row in m)
    squarings = max(0, math.ceil(math.log2(norm / 0.5))) if norm > 0.5 else 0
    scale = 2.0 ** squarings
    m = [[v / scale for v in row] for row in m]
    result = [[float(i == j) for j in range(n)] for i in range(n)]
    term = [row[:] for row in result]
    for k in range(1, 30):
        term = [[v / k for v in row] for row in _matmul(term, m)]
        result = [[result[i][j] + term[i][j] for j in range(n)] for i in range(n)]
    for _ in range(squarings):
        result = _matmul(result, result)
    return result


class _Linear:
    """x' = A x on an augmented state (inputs are states with constant derivatives)."""

    def __init__(self, a):
        self.a = a
        self.cache = {}

    def step(self, x, dt):
        key = round(dt, 18)
        if key not in self.cache:
            self.cache[key] = _expm(self.a, dt)
        return _matvec(self.cache[key], x)


def _minimum(system, x0, read, t_end, grid):
    """min of read(x(t)) on [0, t_end]: a fine grid, then golden-section refinement around the lowest point."""
    xs, t, x = [(0.0, x0)], 0.0, x0
    n = int(round(t_end / grid))
    for _ in range(n):
        x = system.step(x, grid)
        t += grid
        xs.append((t, x))
    k = min(range(len(xs)), key=lambda i: read(xs[i][1]))
    lo_i, hi_i = max(0, k - 1), min(len(xs) - 1, k + 1)
    t_lo, x_lo = xs[lo_i]
    a, b = 0.0, xs[hi_i][0] - t_lo
    g = (math.sqrt(5) - 1) / 2

    def f(s):
        return read(system.step(x_lo, s)) if s > 0 else read(x_lo)

    c, d = b - g * (b - a), a + g * (b - a)
    for _ in range(80):
        if f(c) < f(d):
            b = d
        else:
            a = c
        c, d = b - g * (b - a), a + g * (b - a)
    return min(f((a + b) / 2), read(xs[k][1]))


# ---------------------------------------------------------------------------
# decoupling
# ---------------------------------------------------------------------------


def droop_no_cap(vs, rw, lw, rl, di, tr):
    """Closed form. Lw iL' + (Rw+RL) iL = Vs + RL I(t), v = RL (iL - I), I ramps 0 -> dI over tr.
    v is lowest at the end of the ramp; the droop is measured from Vs, as sim.py does."""
    r = rw + rl
    tau = lw / r
    i_l = (vs + rl * di) / r - rl * di * tau / (r * tr) * (1 - math.exp(-tr / tau))
    return vs - rl * (i_l - di)


def droop_shunt(vs, rw, lw, rl, di, tr, c, esr, l_branch, window):
    """Exact. States [iL, iB, vC, I, 1]: wiring current, cap-branch current, cap voltage, load step, constant.
        Lw iL' = Vs - Rw iL - v
        Lb iB' = v - ESR iB - vC          (Lb = ESL + PCB path)
        C  vC' = iB
        v = RL (iL - iB - I)
    I ramps at dI/tr for tr, then holds. Starts from the DC steady state with I = 0."""
    def a_matrix(slope):
        return [
            [-(rw + rl) / lw, rl / lw, 0.0, rl / lw, vs / lw],
            [rl / l_branch, -(rl + esr) / l_branch, -1 / l_branch, -rl / l_branch, 0.0],
            [0.0, 1 / c, 0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, 0.0, slope],
            [0.0, 0.0, 0.0, 0.0, 0.0],
        ]

    def v_of(x):
        return rl * (x[0] - x[1] - x[3])

    i0 = vs / (rw + rl)
    x0 = [i0, 0.0, rl * i0, 0.0, 1.0]
    ramp = _Linear(a_matrix(di / tr))
    hold = _Linear(a_matrix(0.0))
    during = _minimum(ramp, x0, v_of, tr, tr / 200)
    x_end = ramp.step(x0, tr)
    after = _minimum(hold, x_end, v_of, window, 1e-11)
    return vs - min(during, after)


def series_cap(vs, rw, lw, rl, c, rise, t_at, t_end):
    """Exact. Supply ramps 0 -> Vs over `rise`, then holds; states [iL, vC, Vsrc, 1]:
        Lw iL' = Vsrc - (Rw + RL) iL - vC,  C vC' = iL,  v = RL iL.
    Returns (v at t_at, v at t_end)."""
    def a_matrix(slope):
        return [
            [-(rw + rl) / lw, -1 / lw, 1 / lw, 0.0],
            [1 / c, 0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, slope],
            [0.0, 0.0, 0.0, 0.0],
        ]

    ramp, hold = _Linear(a_matrix(vs / rise)), _Linear(a_matrix(0.0))
    x = ramp.step([0.0, 0.0, 0.0, 1.0], rise)
    return rl * hold.step(x, t_at - rise)[0], rl * hold.step(x, t_end - rise)[0]


# ---------------------------------------------------------------------------
# I2C pull-up
# ---------------------------------------------------------------------------


def rise_30_70(r_pull, c_bus, vdd, r_off):
    """Closed form after the switch opens: v -> v_inf with tau = C (R || Roff), v_inf = Vdd Roff/(R+Roff).
    The 30% and 70% crossings are both on that exponential, so the rise time doesn't depend on
    when the switch opens or where the line started."""
    v_inf = vdd * r_off / (r_pull + r_off)
    tau = c_bus * r_pull * r_off / (r_pull + r_off)
    return tau * math.log((v_inf - 0.3 * vdd) / (v_inf - 0.7 * vdd))
