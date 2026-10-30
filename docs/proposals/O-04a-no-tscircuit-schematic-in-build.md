# O-04a: no tscircuit schematic in build/

Status: ACCEPTED 2026-10-30, option A (the human, in chat). Q3 not decided.
Proposed 2026-10-29 by the agent, at the human's request.

## Problem

Every compile try writes tscircuit's schematic export to `attempts/NN/build/board.kicad_sch`, and
`CompileResult.kicad_sch` points to it. That file is wrong (REVIEW.md §9, V-1):

- wire ends stop 0.06–0.09 mm short of the pins, off KiCad's 1.27 mm grid, so nothing connects;
- symbols come from libraries that don't exist (`Custom:rail_down`, `Connector_Generic:Conn_01x4_J1`);
- it isn't annotated.

On eval run 20261028T161716Z, KiCad ERC finds 20–108 problems per board. On 2026-10-29 the human
opened the MCP9808 one in KiCad and got 8 errors and 51 warnings. They opened it because it is the
`.kicad_sch` in the obvious place, and it is named the same as ours.

Nothing in reflow reads it:

- the design verifier refuses it (`reflow/verifier.py`, V-1);
- learn mode, the report and export read `circuit.json` and our schematic;
- `reflow/export.py` ships our schematic (O-04), never this one.

Our schematic (`schematic/board.kicad_sch`, O-04) gets 0 ERC errors and 0 warnings on every board it
can draw, but it is only written by `reflow export`, at the end of a run.

## Options

### A. Stop exporting tscircuit's schematic (recommended)

- `compile_board` asks tsci for `circuit-json` and `kicad_pcb` only. That is one fewer tsci call per
  compile try; how much time it saves is unmeasured.
- `CompileResult.kicad_sch` stays in the dataclass, so old run folders still parse, but it is always
  `""`. Its comment and docs/04 say it is unused and that our schematic is in `schematic/` after
  `reflow export`.
- Our schematic is still drawn only at export.
- **Changes:**
  - `reflow/compile.py` (AGENT);
  - `docs/04-contracts.md`, with the `contracts.py` comment only;
  - tests: `test_compile.py`'s checks that the file exists change to "no `.kicad_sch` in build/".
    That is a test change, so it is listed here for the human to see; it doesn't loosen any check
    of the files that are still made.
- **Cost:** a run folder no longer has any schematic until `reflow export`.

### B. `CompileResult.kicad_sch` points to our schematic

- Each compile try draws ours (`reflow.schematic.write_schematic`) into `build/board.kicad_sch`,
  from that try's `circuit.json`.
- tscircuit's export is either not made (as in A) or kept as `build/tscircuit.kicad_sch`.
- **Symbols:** drawing needs the chips' KiCad symbols, from rules.toml `[[part]] symbol`. The
  compiler the loop is given is a `(tsx, workdir)` callable, so `reflow/cli.py` can wrap
  `compile_board` with the symbols and no change to `loop.py` (HUMAN).
- **When drawing fails** (no symbol, the LED/diode pin-1 refusal, a pin the symbol doesn't have),
  the try still compiled. So `kicad_sch` is `""`, and the reason needs a home. Either:
  - a new field, `CompileResult.schematic_problems: list[str] = []` (a second contract change); or
  - the reason is only shown at export, as it is today.
- ERC isn't run per try; that stays at export (kicad-cli takes seconds per board).
- **Changes:**
  - `reflow/compile.py` or a wrapper in `cli.py`;
  - `reflow/learn/fixit.py`, which also calls `compile_board`;
  - `docs/04-contracts.md`;
  - tests.
- **Cost:** more work, a second possible contract field, and a schematic in build/ that hasn't been
  ERC-checked yet.

### C. Rename only

- tscircuit's export is written as `build/tscircuit.kicad_sch`, and `kicad_sch` points to it.
- The meaning is unchanged; only the name warns the reader.
- **Cost:** the broken file is still there to open.

## Questions for the human

1. A, B or C?
2. If B: a new `schematic_problems` field, or reasons only at export?
3. If A or B: should `reflow design` also run `schematic_report` on the best attempt at the end of
   a run, so every run folder has our checked schematic without waiting for export? That adds about
   10–30 s per run for KiCad ERC and `reflow check`.

## When accepted

Failing test first:

- A: "build/ has no `.kicad_sch`".
- B: "build/board.kicad_sch is ours (generator `reflow`)".
- C: "build/ has `tscircuit.kicad_sch` and no `board.kicad_sch`".

Then the change, docs/04 and docs/02 (the run tree), and a run of the eval boards' export to show
the ERC results are unchanged. One commit.
