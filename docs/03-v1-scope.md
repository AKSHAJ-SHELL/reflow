# 03 · v1 scope

## In v1 (launch 2026-11-01)

| Area | v1 means |
|---|---|
| Verifier | Built rules (4 IDs) + `parts.provenance` + `scope.high_speed`. Every rule has good + bad fixtures. |
| Harness | `reflow design "<request>"`: spec checkpoint → plan → resolve → codegen → compile → verify → fix (max 3 design attempts, separate compile-retry cap) → result folder. |
| Part resolver | Passives, LEDs and connectors from a JLC catalog; ICs only if the user named them and they exist in the catalog. |
| Learn mode | Mandatory in `design`. At least one **spot-the-bug** interaction built from the AI's real failed attempt; sign-off gate. Terminal. |
| Routing | Simple 2-layer boards only. One router by default, re-DRC after every route, honest "route these nets by hand" report. Refuses high-speed/RF nets. |
| Output | Gerbers, drill, pos, BOM, `report.json`/`report.md` (`report.html` if time allows). |
| Docs | README with status table, quickstart, demo. |

## Out of v1 (v2+)

- Simulation / break-it mode (ngspice)
- Project memory vault (Obsidian-style)
- Datasheet part profiles
- Click-to-explore web UI / local web app
- Multi-sheet schematics, 4+ layers, high-speed or RF routing
- Self-improvement / fine-tuning (Ornith comparison is a side path)
- MCP server for reflow

## Cut order if behind (first cut first)

1. freerouting fallback (keep one router)
2. `report.html` (keep `report.md`)
3. make-the-call interaction (keep spot-the-bug)
4. Routing entirely → v1.1 ("design + verify; you route")

**Never cut:** the verifier, the provenance gate, spot-the-bug, the honest failure report.

## v1 is done when

- On the eval set (E-02, ≥ 5 prompts × 3 runs), `reflow design` reaches a verifier-clean board within 3 attempts on a majority of runs, and the measured numbers are published as they are.
- Zero part numbers in any output that didn't come from the resolver or the user (measured, not assumed).
- Every shipped board has its verify + DRC report beside it.
- A stranger can follow the README quickstart in ≤ 5 minutes on macOS.
