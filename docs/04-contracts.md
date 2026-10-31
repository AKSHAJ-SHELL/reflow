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
| rules_file | str | Path to the project's `rules.toml` (V-2), `""` for none. Set by the CLI from the user's file, never by the planner |

Example: [spec.json](examples/spec.json)

## 0b · `rules.toml` → `ProjectRules` (project rules, written by the student)

`ProjectRules{rule: list[ProjectRule], part: list[RulePart]}` · `ProjectRule{on, need, source, why, to, value}` · `RulePart{ref, mpn, symbol}`

| Field | Type | Meaning |
|---|---|---|
| on | str | `part.pin`, by datasheet pin name or number, e.g. `U1.VDD` |
| need | str | ∈ `RULE_NEEDS`: `cap`, `pullup`, `pulldown`, `tie`, `open`, `connected` |
| source | str | Where the student read it: document, section, page |
| why | str | The student's own explanation. **Human only**, like `Violation.why` |
| to | str | The net on the other side (`cap`, `pullup`, `pulldown`, `tie`); `""` otherwise |
| value | str | `"100nF"` or a range `"100nF..1uF"`; `""` = any value |

- The file on disk is TOML with one `[[rule]]` table per rule, so `tomllib.load` gives a dict that parses with `from_dict(ProjectRules, …)` directly.
- **`[[part]]` (V-2a)** says which part each reference in the rules is: `ref` ("U1"), `mpn` (a `Spec.named_parts` string, e.g. "MCP9808"), and optionally `symbol` (a KiCad library id for its pin map). Codegen is told to give that part that reference, so `U1.VDD` means the same pin to the student, the model and the verifier. `reflow rules check` builds pin maps from it. `part` defaults to `[]`, so rules files without it still parse.
- **Codegen and fix prompts** get one line per rule (`U1.VDD: cap to GND, 100nF..1uF`). `why` and `source` are never sent.
- **Verify** checks every rule deterministically against the pin map (V-1) and the `circuit.json` netlist. A failure is a `Violation` with `rule_id = "project.<need>"`, a generated `fix_hint`, and `why` = the student's `why` plus `source`.

Example: [project_rules.json](examples/project_rules.json) (the MCP9808 board's rules as JSON)

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
- `kicad_sch` is always `""` (Decision O-04a): tscircuit's schematic export isn't made. The field stays so old run folders parse. Our schematic is `schematic/board.kicad_sch`, drawn from circuit.json and checked by `reflow export` (O-04).

Example: [compile_result.json](examples/compile_result.json)

## 5 · netlist source → `VerifyReport` (verifier)

`VerifyReport{schematic, components, nets, errors, warnings, violations: list[Violation]}`. Identical to `reflow check --json` (enforced by `test_cli_json_matches_verify_report`).

- **Input (Decision V-1).** `reflow design` verifies `CompileResult.circuit_json`. `reflow check` verifies a KiCad schematic through `kicad-cli`. Both produce one `Netlist` (`reflow/netlist.py` types) and run the same `run_all`. tscircuit's `.kicad_sch` export is **not** verified: its connectivity is wrong (REVIEW.md §9).
- `schematic` is the file name the netlist came from: `board.kicad_sch` for `reflow check`, `circuit.json` for `reflow design`.
- **Connectivity** comes from `circuit.json` (`reflow/circuit_netlist.py`): ports are grouped by `subcircuit_connectivity_map_key`. A net with a `source_net` takes its name, even if only one port is on it. A net without one is `Net-(<ref>-<pin name>)` after its first pin, or `unconnected-(<ref>-<pin name>-Pad<n>)` when it has a single port. Two named nets on one key (a trace from `net.V3_3` to `net.GND`) raise `MergedNetsError` instead of picking a name. Pin types are left empty; they come from the pin map.
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

Learn mode v2 memory (DECISIONS L-2): `ConceptCard{concept, fsrs, last_reviewed, ratings}` · `VaultNote{path, kind, title, links}`

- One `ConceptCard` per concept. It lives in the frontmatter of the vault's `concepts/<concept>.md` (`~/.reflow/vault/`, or `REFLOW_VAULT`). `fsrs` is the scheduler's card as JSON, opaque to reflow. `ratings` are `"<ISO UTC> good|hard|again"`, from what the user did, never from self-rating.
- `kind` ∈ `concept | mistake | board`; `links` are the note's `[[wikilinks]]`, so Obsidian's graph and `/api/vault/graph` show the same thing.

Examples: [concept_card.json](examples/concept_card.json), [vault_note.json](examples/vault_note.json)

Simulation (DECISIONS L-2, L-2a): `SimRequest{concept, target_refs, variant, change}` · `SimResult{concept, variant, signals: list[SimSignal], exit_code, deck_path, ran, verdict, notes, assumptions}` · `SimSignal{name, unit, t, v}`

- ngspice runs as a separate process on a hand-written testbench per concept. `ran = false` means nothing is plotted, and `notes` say why.
- `assumptions` lists every value the board file doesn't contain (load step, bus capacitance, wiring inductance, nH per mm), so the UI shows them with the plot.
- Plotted signals are thinned for the browser, but each bucket keeps its minimum and maximum, so a spike is never hidden.

Example: [sim_result.json](examples/sim_result.json)

Fix-it (DECISIONS L-2a): `FixEdit{kind, ref, pin, value, part, a, b}` · `FixResult{number, base_attempt, edits, compiled, compile_errors, errors, warnings, violations, refused, tsx_path, circuit_json}`

- `kind` ∈ `add_part | set_value | connect | disconnect | delete | set_label | set_trace_limit` (a decoupling cap's maximum trace length to the pin, e.g. `3mm`). `a`/`b` are a pin (`U1.SDA`, `U1.pin3`) or a net (`V3_3`). A part the user adds carries no part number.
- Each fix is recompiled with tsci and verified by the same binder and rules as a run. It's saved in the run folder under `learn/fix/<number>/`. `refused` is set when the verifier won't take the board at all (two named nets shorted, no components).

Example: [fix_result.json](examples/fix_result.json)

## 9 · `.kicad_pcb` → `RouteResult` (router)

`RouteResult{status, router, tries, routed_nets, total_nets, unrouted_nets, refused_nets, drc: DrcSummary, kicad_pcb}` · `DrcSummary{errors, warnings, unconnected, report_path}`

- `status` ∈ `routed | partial | refused | failed`; `router` ∈ `tscircuit | freerouting`.
- `drc` always comes from **our** `kicad-cli pcb drc` run after refilling zones, never from the router's log.

Example: [route_result.json](examples/route_result.json)

## 10 · routed board → `FabPackage` (output)

`FabPackage{gerbers_dir, drill, pos_csv, bom_csv, design_md, report_json, report_html}`

Example: [fab_package.json](examples/fab_package.json)
