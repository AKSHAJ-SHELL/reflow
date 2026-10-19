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
| D-1 | 2026-10-19 | ACCEPTED (a) Anthropic Claude Sonnet-tier as the v1 default, behind `complete()`. OpenAI is a later comparison arm. | Accepted by the human in chat |
| D-2 | 2026-10-19 | ACCEPTED (a) hand-rolled loop + small adapters. No LiteLLM, no PydanticAI. | Accepted by the human in chat |
| D-3 | 2026-10-19 | ACCEPTED (a) compact text rendered from `RetryFeedback`. On-disk feedback stays the contract JSON. | Accepted by the human in chat |
| D-6 | 2026-10-19 | ACCEPTED jlcsearch JSON API plus a local cache so a repeat run makes no network calls. No shared distributor keys. | Accepted by the human in chat |
| H-00 Q3 | 2026-10-19 | ACCEPTED `best_attempt` = fewest errors, then fewest warnings, then latest compiled attempt; 0 if none compiled. Next codegen TSX is the best-so-far file only when the latest attempt has strictly more errors. | Accepted by the human in chat |
| H-00 Q4 | 2026-10-19 | ACCEPTED (b) run folder rewritten every step; no resume command. | Accepted by the human in chat |
| H-00 Q5 | 2026-10-19 | ACCEPTED (c) always up to 3 design attempts. Log identical rule_ids+refs. No model switch, no `why` in the prompt. | Accepted by the human in chat |
| H-00 Q6 | 2026-10-19 | ACCEPTED (a) `parts.provenance` is a verifier error and consumes a design attempt. | Accepted by the human in chat |
| H-00 CAP | 2026-10-19 | ACCEPTED `COMPILE_CAP` default 2, from config. A missing code fence counts as a compile try. | Accepted by the human in chat |
| H-00 ST | 2026-10-19 | ACCEPTED `failed_compile` only when nothing compiled. Unresolved parts, unconfirmed spec, or a bad plan after one re-prompt: `aborted`. | Accepted by the human in chat |

## Proposed (awaiting the human)

| ID | Date | Proposal | Options | Proposed by |
|---|---|---|---|---|
| D-4 | 2026-10-17 | Learn-mode interaction design | (a) spot-the-bug multiple choice (b) spot-the-bug free text graded by refs (c) make-the-call first | agent |
| D-5 | 2026-10-17 | UI form for v1 | (a) CLI + generated report.html (b) CLI only (c) local web app | agent |
| P-1 | 2026-10-17 | Add `runs/` to .gitignore | done provisionally; revert if unwanted | agent |
