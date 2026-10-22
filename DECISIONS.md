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
| V-1 | 2026-10-20 | ACCEPTED `reflow design` verifies `circuit.json`, never tscircuit's `.kicad_sch`. IC pin names and kinds come from a trusted pin map by physical pin number, never from TSX labels; TSX label ≠ map is a verify error; no trusted map is a verify error. `.kicad_pcb` pad nets must equal `circuit.json`. Every rule cites its source. New contracts `Citation`, `CardPin`, `PartCard`, `PIN_KINDS`; no existing field changes. (b) as amended by V-2. Full text: `docs/proposals/V-1-circuit-json-ground-truth.md` | Accepted by the human in chat |
| V-2 | 2026-10-20 | ACCEPTED General rules ship with reflow. A project adds `rules.toml` (`on`, `need` ∈ {cap, pullup, pulldown, tie, open, connected}, `to`, `value`, `source`, `why`) written by the student from datasheets. Rules go to codegen as constraints and are checked deterministically at verify (`project.<need>`); `why` never reaches the model. The datasheet tutor is a separate Claude skill, not part of reflow. Amends V-1 (b): pin maps come from vendor data, then KiCad symbols, with a signed `PartCard` as override. Contract change approved 2026-10-20: `RULE_NEEDS`, `ProjectRule`, `ProjectRules`, `Spec.rules_file`. Full text: `docs/proposals/V-2-rule-framework.md` | Accepted by the human in chat |
| D-6a | 2026-10-21 | ACCEPTED Amends D-6. Parts data comes from the local jlcparts snapshot (`cache.sqlite3`, read-only) at `REFLOW_PARTS_DB` (default `~/.cache/reflow/jlcparts/`), outside the repo and never redistributed; `reflow parts update` downloads it. `ResolvedPart.fetched_at` is the row's own date. Basic = `library_type == "base"`. jlcsearch client and tests are retired (removal needs the human's OK in that commit). Sub-answers: (a) headers use `value="1x4"`, `package="2.54mm"`; (b) resolver matches a typed family to orderable MPNs by prefix + package, Unresolved with a question if ambiguous; (c) 1.5 GB disk is fine for v1; (d) data terms unverified. Full text: `docs/proposals/D-6a-jlcparts-snapshot.md` | Accepted by the human in chat |
| O-1 | 2026-10-21 | ACCEPTED Ownership exception, these two tasks only: P-02b (resolver changes) is implemented by the agent and reviewed line by line by the human before it counts as done; E-02 (eval boards) is drafted by the agent and every expectation is checked by the human against the datasheets before any go/no-go result counts. Golden rule 1 is unchanged for everything else. | Accepted by the human in chat |
| V-2a | 2026-10-21 | ACCEPTED Amends V-2: rules.toml gains `[[part]] ref, mpn, symbol` (new contract `RulePart`, `ProjectRules.part`, default `[]`). `mpn` must be a `Spec.named_parts` string. Codegen is told to give that part that reference; `reflow rules check` builds pin maps from it. Full text: `docs/proposals/V-2a-rule-parts.md` | Accepted by the human in chat |

## Proposed (awaiting the human)

| ID | Date | Proposal | Options | Proposed by |
|---|---|---|---|---|
| D-4 | 2026-10-17 | Learn-mode interaction design | (a) spot-the-bug multiple choice (b) spot-the-bug free text graded by refs (c) make-the-call first | agent |
| D-5 | 2026-10-17 | UI form for v1 | (a) CLI + generated report.html (b) CLI only (c) local web app | agent |
| P-1 | 2026-10-17 | Add `runs/` to .gitignore | done provisionally; revert if unwanted | agent |
