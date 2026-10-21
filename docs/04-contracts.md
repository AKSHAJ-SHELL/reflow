# 04 · Contracts

Every arrow in the pipeline passes exactly one object. They are defined once, in [`reflow/contracts.py`](../reflow/contracts.py), with a worked JSON example for each in [`docs/examples/`](examples/). [`tests/test_contracts.py`](../tests/test_contracts.py) freezes every field name and parses every example strictly (unknown keys, missing keys and wrong types all fail).

**To change a contract:** propose it in `DECISIONS.md` → human accepts → change `contracts.py`, the frozen list in the test, this file and the example JSON **in one commit**. Never loosen a contract test to make it pass.

Conventions: all paths are strings relative to the repo or run folder; all times are ISO-8601 UTC; enums are plain strings listed in `contracts.py`.

---

## 0 · request → `Spec` (spec checkpoint)

| Field | Type | Meaning |
|---|---|---|
| request | str | The user's sentence, verbatim |
| title | str | Short board name |
| power | str | e.g. "3.3V on the header" |
| interfaces | list[str] | Connectors / buses exposed |
| constraints | list[str] | Size, layers, address, etc. |
| named_parts | list[str] | **Part numbers the user typed.** The only MPNs anything downstream may copy |
| open_questions | list[OpenQuestion{id, question, answer}] | Asked by the planner, answered by the user |
| confirmed | bool | True only after the user confirms. Nothing downstream runs on `false` |

Example: [spec.json](examples/spec.json)

## 1 · `Spec` → `Plan` (planner, LLM)

`Plan{blocks: list[Block], parts: list[PartRequest], nets: list[str]}`

`Block{name, purpose, part_ids}` · `PartRequest{id, role, category, value, package, tolerance, voltage, mpn, notes}`

- `category` ∈ `PART_CATEGORIES`.
- `mpn` must be `""` unless copied from `Spec.named_parts` (checked by a contract test on the example, and by the provenance rule at runtime).

Example: [plan.json](examples/plan.json)

## 2 · `Plan.parts` → `ResolvedParts` (resolver, deterministic)

`ResolvedParts{resolved: list[ResolvedPart], unresolved: list[Unresolved]}`

`ResolvedPart{request_id, lcsc, mpn, manufacturer, package, value, stock, basic, unit_price_usd, source, fetched_at}` · `Unresolved{request_id, reason}`

- Every `PartRequest` appears in exactly one of the two lists.
- An unresolved part stops the run before codegen with a readable reason. It is never guessed.

Example: [resolved_parts.json](examples/resolved_parts.json) (values illustrative)

## 2b · `PartCard` (ground truth, HUMAN-verified)

`PartCard{family, mpns, lcsc, package, pins: list[CardPin], pin_source: Citation, verified_by, verified_on}` · `CardPin{number, name, kind}` · `Citation{doc, locator, url}`

- **Pin maps (V-2 amends V-1 b).** The verifier looks up each IC's pins in this order: a signed `PartCard` in `cards/`, then the vendor's machine-readable pin data (e.g. ST STM32_open_pin_data), then the KiCad symbol library. A card is an **override**, written when 2–3 are wrong or missing. No trusted pin map → verify error.
- A card covers one IC family and package, checked pin by pin against the manufacturer datasheet named in `pin_source`. Cards live in `cards/` and are **HUMAN-owned** (like `fixtures/`).
- `kind` ∈ `PIN_KINDS`. `power` and `ground` pins become `power_in` in the verifier's netlist.
- `verified_by == ""` is a draft. The verifier ignores drafts.
- An agent may draft a card (for example from the part's EasyEDA symbol). Only a person fills `verified_by`.

Example: [part_card.json](examples/part_card.json) (draft)

## 3 · → `GeneratedCode` (codegen, LLM)

`GeneratedCode{attempt, compile_try, tsx, model, input_tokens, output_tokens}`

- `attempt` counts **design** attempts (max 3). Compile retries increment `compile_try`, not `attempt`.
- `tsx` is always the **whole** `index.circuit.tsx`, never a diff.

Example: [generated_code.json](examples/generated_code.json)

## 4 · `GeneratedCode` → `CompileResult` (compiler, deterministic)

`CompileResult{ok, errors: list[CompileError], stderr_tail, kicad_sch, kicad_pcb, circuit_json}` · `CompileError{message, line, column, file}`

- `stderr_tail`: last ≤ 40 lines, trimmed before it is stored.
- Paths are `""` when `ok` is false.

Example: [compile_result.json](examples/compile_result.json)

## 5 · netlist source → `VerifyReport` (verifier)

`VerifyReport{schematic, components, nets, errors, warnings, violations: list[Violation]}`. Identical to `reflow check --json` (enforced by `test_cli_json_matches_verify_report`).

- **Input (Decision V-1).** `reflow design` verifies `CompileResult.circuit_json`. `reflow check` verifies a KiCad schematic through `kicad-cli`. Both produce one `Netlist` (`reflow/netlist.py` types) and run the same `run_all`. tscircuit's `.kicad_sch` export is **not** verified: its connectivity is wrong (REVIEW.md §9).
- `schematic` is the file name the netlist came from: `board.kicad_sch` for `reflow check`, `circuit.json` for `reflow design`.
- **Connectivity** comes from `circuit.json`: ports are grouped by `subcircuit_connectivity_map_key`. A net is named after its `source_net`, otherwise `Net-(<ref>-<pin name>)`. A port alone on its key is `unconnected-(<ref>-<pin name>-Pad<n>)`.
- **IC pins come from the trusted pin map (§2b), not the TSX.** Each IC is matched through its LCSC id, which must equal a `ResolvedParts` row. Pin names and kinds are set from the pin map by physical pin number. A TSX label that differs from the map is a verify error. An IC with no trusted pin map is a verify error.
- **Built = verified.** The `.kicad_pcb` pad nets must equal the `circuit.json` connectivity. Any difference is a verify error.

### Violation (built, frozen)

| Field | Type | Audience | Meaning |
|---|---|---|---|
| rule_id | str | both | `family.check`, e.g. `decoupling.series` |
| severity | str | both | `error` \| `warning` |
| message | str | both | What is wrong, naming refs and nets |
| why | str | **human only** | The physics; shown in learn mode and the report |
| fix_hint | str | **model + human** | A concrete instruction the model can apply |
| refs | list[str] | both | Reference designators involved |
| nets | list[str] | both | Net names involved |

Example: [verify_report.json](examples/verify_report.json)

## 6 · `VerifyReport` | `CompileResult` → `RetryFeedback` (HUMAN-owned conversion)

What the model sees on the next try. **`why` is excluded on purpose** (enforced by `test_feedback_is_violation_minus_why`).

| Field | Type | Meaning |
|---|---|---|
| kind | str | `compile` \| `verify` |
| attempt | int | The attempt that just failed |
| max_attempts | int | 3 in v1 |
| history | list[str] | One line per earlier failed attempt, oldest first, e.g. `attempt 1: decoupling.series C1/U1` |
| violations | list[FeedbackViolation] | `kind == verify`: `{rule_id, severity, message, fix_hint, refs, nets}` |
| compile_errors | list[CompileError] | `kind == compile`: trimmed |

Example: [retry_feedback.json](examples/retry_feedback.json)

**Rendering.** The harness renders `RetryFeedback` into text with the template in `prompts/fix.md` (HUMAN-approved), together with the current `tsx`. Which format the model actually sees (compact text vs JSON vs annotated code) is Decision D-3; the *contract* above doesn't change with that choice.

## 7 · loop → `RunResult` (harness)

`RunResult{run_id, status, attempts: list[AttemptRecord], best_attempt, run_dir, input_tokens, output_tokens}`

`AttemptRecord{attempt, compile_tries, compiled, errors, warnings, rule_ids, dir}`

- `status` ∈ `passed | failed_verify | failed_compile | aborted`.
- `best_attempt` is 0 if nothing compiled. **How** the best attempt is chosen is a HUMAN decision (06-harness-design, Q3).
- Written to `runs/<id>/run.json` after every step (crash safety).

Example: [run_result.json](examples/run_result.json)

## 8 · `RunResult` → `LearnRecord`, `SignOff` (learn mode)

`LearnRecord{interactions: list[LearnInteraction], skipped_concepts}` · `LearnInteraction{kind, concept, rule_id, prompt, user_answer, correct, explanation}` · `SignOff{accepted, warnings_acknowledged, overrides, at}`

- `kind` ∈ `spot_bug | make_call`. Every interaction comes from a **real** violation in this run (`rule_id`), never a canned quiz.

Examples: [learn_record.json](examples/learn_record.json), [signoff.json](examples/signoff.json)

## 9 · `.kicad_pcb` → `RouteResult` (router)

`RouteResult{status, router, tries, routed_nets, total_nets, unrouted_nets, refused_nets, drc: DrcSummary, kicad_pcb}` · `DrcSummary{errors, warnings, unconnected, report_path}`

- `status` ∈ `routed | partial | refused | failed`; `router` ∈ `tscircuit | freerouting`.
- `drc` always comes from **our** `kicad-cli pcb drc` run after refilling zones, never from the router's log.

Example: [route_result.json](examples/route_result.json)

## 10 · routed board → `FabPackage` (output)

`FabPackage{gerbers_dir, drill, pos_csv, bom_csv, design_md, report_json, report_html}`

Example: [fab_package.json](examples/fab_package.json)
