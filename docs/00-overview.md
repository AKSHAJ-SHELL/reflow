# 00 · Overview

**reflow** is an open-source agent that turns a one-sentence hardware request into a verified, manufacturable 2-layer PCB, and won't let you ship a board you don't understand.

Written 2026-10-17. Stage: **verifier done, harness next.** v1 launch target: **Sun 2026-11-01**.

## Read order

1. This file (assumptions)
2. [01-current-state](01-current-state.md): what works today
3. [02-architecture](02-architecture.md) → [04-contracts](04-contracts.md): the pipeline and its exact data at every arrow
4. [06-harness-design](06-harness-design.md): the stage being built now
5. [../TASKS.md](../TASKS.md): what to do next, with owners

## The three ideas

1. **Don't rebuild the EDA stack.** tscircuit compiles, KiCad checks and exports, freerouting/tscircuit route. reflow is the orchestration + verification layer.
2. **Gate every board on intent verification.** Generating boards is a solved demo. Catching plausible-but-wrong boards is not. reflow's hand-written rules catch bugs KiCad's ERC misses or only reports vaguely.
3. **The AI works, the human thinks.** Spec checkpoint, mandatory interactive learn mode, sign-off. About 2 minutes of human attention per board.

## Assumptions (written instead of asking)

| # | Assumption | Why / source |
|---|---|---|
| A1 | The compiler is **tscircuit (`tsci`)**, not atopile. The kickoff brief said "atopile -> KiCad"; that is treated as stale. | NOTES.md 2026-10-07: atopile CLI moved toward a hosted app; tscircuit builds without an account and exports KiCad + DSN + netlist. |
| A2 | Package and command are `reflow`; the intended PyPI name is `reflow-pcb` (not yet set in pyproject). The folder on disk is still `reflow/`. | Name decided 2026-10-17. |
| A3 | `SYSTEM_DESIGN.md` (repo root, "reflow" naming) is historical. `docs/` is authoritative where they differ. | Written 2026-10-13, before the v1 scope cut and rename. |
| A4 | v1 boards: 2 layers, low speed, roughly ≤ 20 parts, one schematic sheet. High-speed/RF nets are refused, not attempted. | v1 scope decision 2026-10-13/14. |
| A5 | Learn mode and sign-off run in the terminal in v1, with a generated `report.html` for viewing. A local web app is v2. | UI discussion 2026-10-13. Decision D-5 still open. |
| A6 | Routing default is tscircuit's built-in autorouter; freerouting is the fallback through KiCad 10's SWIG `pcbnew` DSN/SES bridge. KiCad is pinned to 10.x. | KiCad has no CLI/IPC DSN path until 11; SWIG is slated for removal in 11. |
| A7 | One model interface (prompt in, text out). Provider not chosen yet. | Decision D-1 open. |
| A8 | Parts come from a local jlcparts snapshot (`reflow parts update`); the jlcsearch API was retired after its stock data and search broke. | Decided: D-6a (2026-10-21), P-06. |
| A9 | "Weekend 1 done" meant the toolchain round trip (KiCad → DSN → freerouting → SES → KiCad). **No LLM code exists yet.** | Repo state 2026-10-17. |
| A10 | Schedule: harness go/no-go **Sun 2026-10-25**, v1 launch **Sun 2026-11-01**. Hard stop: AMC 12A on Thu 2026-11-05, MTFC from 2026-11-08. | Author's calendar. |
| A11 | Public framing: an open-source alternative to tools like another tool. Never "killing another tool"; comparisons are factual and reproducible. | Author's rule. |

## Non-negotiables

- The AI never writes a part number the user didn't type. It asks for a category; the resolver returns real parts.
- Nothing is called "AI-designed" without its verification + DRC report attached.
- Every rule ships with a known-good and a known-bad fixture.
- Retries are bounded (3 design attempts). Failure is reported honestly.
