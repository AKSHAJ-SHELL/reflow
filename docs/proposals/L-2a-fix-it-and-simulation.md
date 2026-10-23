# L-2a · Fix-it tools and simulation (addendum to L-2)

Status: **ACCEPTED** 2026-10-22. The human asked for it in chat ("implement these: fix-it tools plus schematic simulation for decoupling and I²C pull-ups; routing; PCB-level simulation on the routed boards"). It was written up by the agent. Binding text: `DECISIONS.md` row L-2a. It adds an interaction to L-2 and moves phase 3 forward.

## The interaction: fix it yourself

Spot-the-bug asks *which part breaks it*. Fix-it goes further: after the reveal, the user gets tools on the AI's failed draft and fixes it themselves. reflow checks the fix with the same compiler, pin binding and rules a real run uses. Simulation then shows the physics of the broken draft next to the user's fix.

- **Tools** (each one an edit to the draft's TSX, so the result is a real tscircuit board):
  - add a resistor or capacitor between a pin or net and a net;
  - change a part's value;
  - connect a pin to a net;
  - disconnect a pin;
  - delete a part.
- **Checking a fix:** the learn server recompiles the edited TSX with `tsci` and re-verifies it (circuit.json, pin binding, rules), on the user's machine. **No model call.** The result is the same `VerifyReport` a run gets.
- **The AI's fix** (its final attempt) is shown only after the user has tried, so it stays commit-before-you-see. Nothing is scored.
- **Where fixes are saved:** in the run folder under `learn/fix/<n>/` (TSX, compile result, circuit.json, verify.json). The learn server writes nothing else besides `learn.json` and `signoff.json`.
- **No part numbers:** user-added parts carry no part number. Rule 5 is untouched, because no model output becomes an MPN.

## Simulation: schematic level

ngspice runs as a separate process (BSD-3, never imported). The testbenches are hand-written, and each one adds the physics a circuit.json lacks: supply wiring inductance, the IC's load current, an open-drain driver, bus capacitance. Every testbench ships with a hand-calculated expected value and a known-good and a known-bad test. A concept without a validated testbench says "can't simulate this yet".

| Concept | Testbench | Hand calculation it's checked against |
|---|---|---|
| Decoupling | Supply → wiring R + L → chip node; load = DC resistor + a fast current step; the decoupling cap (with ESR and ESL) from the chip node to GND | No cap: during the step's ramp, V = V<sub>s</sub> − L·ΔI/t<sub>r</sub>. With a cap: peak droop ≈ ΔI·√(L/C) (the LC ring). Cap in series: no DC path, so V decays as V<sub>s</sub>·e<sup>−t/(R<sub>load</sub>·C)</sup>. |
| I²C pull-ups | Pull-up R to the rail; bus capacitance C<sub>bus</sub>; an open-drain switch that releases the line | 30%→70% rise time = R·C<sub>bus</sub>·ln(7/3) ≈ 0.847·R·C<sub>bus</sub>. No pull-up: the line never reaches 30%. |

The assumed values (load step, bus capacitance, wiring inductance) are shown in the UI with every plot, labelled as assumptions. The board's own values (cap value, resistor value, supply voltage) come from the design.

## Simulation: PCB level

The same decoupling testbench, plus the path from the cap to the chip's supply pin on the actual layout:

- **The path length:** on a routed board, the length of the copper trace (`pcb_trace` segments) between the cap's pad and the pin. On an unrouted board, the straight-line distance between the two pads, labelled as a lower-bound estimate.
- **Inductance:** about 1 nH per mm (a common rule of thumb for a thin trace over a ground plane; an assumption, shown as such).
- **Hand calculation:** the extra fast droop ≈ L<sub>path</sub>·ΔI/t<sub>r</sub>, so the user sees a cap 20 mm away do less than one 2 mm away.

Gerber-level checks (the fab files match the verified netlist) belong with fab export (O-01) and V-13. They're out of scope here.

## Routing

tscircuit's autorouter runs inside `tsci export`. On the eval boards so far it was skipped (for example, "the 1mm maximum length for .C1 > .pin1 to .U1 > .pin16 cannot be satisfied"), so the PCB exports had no traces.

X-01 finds out why, makes the boards route where the router can, and reports unrouted nets honestly (X-04). A board that only partly routes is never called "routed" (golden rule 6).

## Ownership and contracts

- **Ownership:** the testbenches are O-1c (the agent writes them; the human reviews them line by line before they count).
- **Contracts:**
  - `SimRequest` and `SimResult` are the ones L-2 approved;
  - `SimSignal{name, unit, t, v}` is the "signals [{name, unit, t[], v[]}]" item L-2 lists inside SimResult, given its own dataclass;
  - `FixEdit` and `FixResult` are new, approved with this addendum.
