# DECISIONS

Agents **propose**; the human **accepts** or rejects. Only ACCEPTED entries bind. A contract change needs an accepted entry here before code changes.

Format: `ID · date · status (PROPOSED | ACCEPTED | REJECTED | SUPERSEDED) · decision · why · who`

## Accepted

| ID | Date | Decision | Why |
|---|---|---|---|
| A-01 | 2026-10-07 | Compile with **tscircuit**, not atopile | atopile CLI moving to hosted app; tscircuit builds without account and exports KiCad + DSN + netlist |
| A-02 | 2026-10-08 | Verify from the **netlist**, never from a rendered picture | Misread a schematic image as a short; netlist showed it correct |
| A-03 | 2026-10-10 | Hand-write rules, Violation model, fixtures; agents write plumbing | "Does the bug crash, or produce a plausible wrong answer?" |
| A-04 | 2026-10-13 | **Learn mode is mandatory** and interactive, not a quiz | Product stance: AI designs, user must understand |
| A-05 | 2026-10-13 | The AI **never picks a part number**; it requests a category | Hallucinated MPNs are the classic AI-hardware failure |
| A-06 | 2026-10-14 | v1 = verifier + harness + part resolver + simple 2-layer routing + learn mode v0; v2 = simulation, memory vault | Ship by 2026-11-01 without burning out |
| A-07 | 2026-10-17 | Name: **reflow** (command `reflow`, PyPI `reflow-pcb`) | Avoid using a competitor's brand in the name |
| A-08 | 2026-10-17 | Two launches: `reflow check` on the author's account now; full v1 co-posted with LARP Slayers | LARP Slayers want the harness; posting progress early |
| A-09 | 2026-10-17 | Compile errors do **not** consume a design attempt; only verifier failures do | A syntax slip isn't a design failure (needs a compile cap; see H-00) |
| A-10 | 2026-10-17 | Never claim "ERC is silent" on the real board; it reports `power_pin_not_driven` | Honesty; NOTES.md 2026-10-17 |

## Proposed (awaiting the human)

| ID | Date | Proposal | Options | Proposed by |
|---|---|---|---|---|
| D-1 | 2026-10-17 | LLM provider/model for v1 default | (a) Anthropic Claude (Sonnet tier) (b) OpenAI (GPT tier) (c) local via Ollama; all behind one interface | agent |
| D-2 | 2026-10-17 | Harness framework vs hand-rolled | (a) hand-rolled loop + 2–3 small adapters (b) hand-rolled loop + LiteLLM for model I/O (c) PydanticAI | agent |
| D-3 | 2026-10-17 | Feedback format Violation → LLM | (a) compact text block per violation (b) `RetryFeedback` as JSON (c) JSON + inline comments in the TSX at offending refs | agent |
| D-4 | 2026-10-17 | Learn-mode interaction design | (a) spot-the-bug multiple choice (b) spot-the-bug free text graded by refs (c) make-the-call first | agent |
| D-5 | 2026-10-17 | UI form for v1 | (a) CLI + generated report.html (b) CLI only (c) local web app | agent |
| D-6 | 2026-10-17 | Parts backend | (a) jlcsearch public JSON API (b) local SQLite snapshot from jlcparts/jlcsearch (c) bring-your-own-key distributor APIs (Mouser/DigiKey); or hybrid | agent |
| H-00 | 2026-10-17 | Harness Q3 best attempt · Q4 crash safety · Q5 early stop · Q6 provenance check point · COMPILE_CAP | see docs/06-harness-design.md | agent (questions only) |
| P-1 | 2026-10-17 | Add `runs/` to .gitignore | done provisionally; revert if unwanted | agent |
