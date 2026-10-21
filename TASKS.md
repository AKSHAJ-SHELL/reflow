# Task board

One task ID at a time. Failing test first. **OWNER=HUMAN tasks are never touched by agents** (not even "small fixes"); agents may write tests *for* them only if asked.

Owners: **HUMAN** = the author hand-codes it · **AGENT** = coding agent · **AGENT→HUMAN** = agent drafts, human approves before merge.
Status: `todo` · `doing` · `done` · `blocked`. Dates are targets (see 03-v1-scope for the cut order).

## Now: housekeeping

| ID | Goal | Inputs | Outputs | Acceptance test | Deps | Owner | Status |
|---|---|---|---|---|---|---|---|
| Z-01 | Finish the rename | working tree | committed imports; `reflow/netlist.py` deleted; pyproject `name = "reflow-pcb"` | `grep -rn reflow --include=*.py .` empty; `pytest -q` green; `reflow check fixtures/sensor_good` exit 0 | — | HUMAN | todo |
| Z-02 | Untrack `scratch/` | git index | `git rm -r --cached scratch` committed | `git ls-files scratch` empty | Z-01 | HUMAN | todo |
| D-01 | Launch post for `reflow check` | 01-current-state real-board result | README hook + screenshot + post | Stranger can install and run `reflow check` from README in ≤ 5 min | Z-01 | HUMAN | todo (Sun 10-18) |

## Verifier (rules are HUMAN)

| ID | Goal | Inputs | Outputs | Acceptance test | Deps | Owner | Status |
|---|---|---|---|---|---|---|---|
| V-01 | Fixtures for `decoupling.missing` and `i2c.duplicate_pullup` | sensor_good | `bad_no_decoupling`, `bad_double_pullup` | Each produces exactly its rule ID | — | HUMAN | todo |
| R-01 | `led.no_limiter` | blinky_good | rule + bad fixture | bad → exactly `led.no_limiter`; all good fixtures clean | — | HUMAN | todo |
| R-02 | `two_terminal.open` / `.shorted` | any good fixture | rule + 2 bad fixtures | each bad → exactly its ID; good clean | — | HUMAN | todo |
| R-03 | `parts.provenance` | `Spec`, `ResolvedParts`, netlist | rule + `bad_hallucinated_mpn` | bad → exactly `parts.provenance` | R-05 | HUMAN | todo |
| R-04 | `scope.high_speed` | netlist net names | rule + `bad_usb_route` | USB/DDR/RF nets flagged; good clean | — | HUMAN | todo |
| R-05 | Optional context arg for rules (`check(nl, pcb=None, ctx=None)`) | rules API | backward-compatible `run_all` | all existing tests unchanged and green | — | HUMAN | todo |

## Verifier input and project rules (DECISIONS V-1, V-2)

| ID | Goal | Inputs | Outputs | Acceptance test | Deps | Owner | Status |
|---|---|---|---|---|---|---|---|
| V-10 | `circuit.json` → `Netlist` loader | `CompileResult.circuit_json` | `reflow/circuit_netlist.py` | recorded sensor boards load with the traced nets; rules on them give the planted bug only; malformed input raises | V-1 | AGENT | done (10-20) |
| V-11 | Pin-map importer (vendor pin data, then KiCad symbol; signed card overrides) | LCSC id / MPN + package | pin map per IC | MCP9808 and STM32F103C8 maps match their datasheets; a disagreement between sources is reported | V-1 | AGENT | done (10-20) |
| V-12 | Bind ICs to pin maps: relabel pins by physical number | Netlist, ResolvedParts, pin maps | card-labelled Netlist | wrong TSX pinout → mismatch findings; no pin map → finding | V-10, V-11 | HUMAN | todo |
| V-13 | Rules `parts.no_card`, `pinout.mismatch`, `verify.pcb_mismatch`, and how shorted named nets surface | V-12 output | rules + fixtures | each bad fixture → exactly its rule | V-12 | HUMAN | todo |
| V-14 | `.kicad_pcb` pad-net reader | `CompileResult.kicad_pcb` | {(ref, pad): net} | recorded board matches its `circuit.json` nets | — | AGENT | done (10-20) |
| V-16 | Verifier adapter `(circuit_json, ResolvedParts, Spec) → VerifyReport` | V-10..V-14 | callable for `run_design` | integration tests in `tests/test_integration.py` go green on the circuit.json path | V-10..V-14 | AGENT | done (10-20); loop test green once loop patch applied |
| R-07 | Citations for every rule in docs/05 | rules | docs/05 | every catalog row names its source | — | HUMAN | todo |
| R-10 | The six `need` checks (`project.cap`, `.pullup`, `.pulldown`, `.tie`, `.open`, `.connected`) | ProjectRules, Netlist | rules + fixtures | each bad fixture → exactly its rule | V-12 | HUMAN | todo |
| V-21 | `rules.toml` parser + `reflow rules check` | `Spec.rules_file` | `ProjectRules`, report | example rules.toml passes; unknown pin, missing `why` or `source` fail; uncovered power/reset/boot pins warn | V-11 | AGENT | todo |
| V-22 | Render project rules into codegen/fix prompts | ProjectRules | prompt text | one line per rule; no `why`/`source` in any prompt | V-21, H-08 | AGENT→HUMAN | todo |

## Contracts

| ID | Goal | Inputs | Outputs | Acceptance test | Deps | Owner | Status |
|---|---|---|---|---|---|---|---|
| C-01 | Stage contracts + strict parsing + examples | docs/04 | `reflow/contracts.py`, `docs/examples/*.json`, `tests/test_contracts.py` | `pytest -q tests/test_contracts.py` green | — | AGENT | done (10-17) |

## Harness (core is HUMAN)

| ID | Goal | Inputs | Outputs | Acceptance test | Deps | Owner | Status |
|---|---|---|---|---|---|---|---|
| H-00 | Answer Q3–Q6 + COMPILE_CAP in DECISIONS.md | 06-harness-design | accepted decisions | each Q has one chosen option | — | HUMAN | done (10-19) |
| H-01 | Harness skeleton: dataclasses + signatures, no bodies | contracts | `reflow/harness/*.py` | imports cleanly; signatures use contracts types | H-00, C-01 | HUMAN | done (10-19) |
| H-02 | Context builder + Violation→`RetryFeedback` conversion | `VerifyReport`, `CompileResult` | `RetryFeedback` + rendered prompt text | output parses as `RetryFeedback`; contains no `why`; prompt within token budget | H-01 | HUMAN | done (10-19) |
| H-03 | Core loop | everything above | `RunResult` | fake model + fake compiler: passes on attempt 2 → status passed, best_attempt 2 | H-02, M-01, K-01 | HUMAN | done (10-19) |
| H-04 | Retry termination + best-attempt selection | attempt records | `RunResult.status`, `best_attempt` | table test of the Q3/Q5 scenarios | H-03 | HUMAN | done (10-19) |
| H-05 | Run folder I/O (+ resume if Q4=a) | `RunResult`, artifacts | `runs/<id>/...` per 02-architecture | kill mid-run → files from completed steps exist and parse | H-01 | AGENT | todo |
| H-06 | Spec checkpoint + planner call (CLI side) | request | confirmed `Spec`, `Plan` | `Plan` parses strictly; `mpn` only from `named_parts` | M-01, H-08 | AGENT | todo |
| H-07 | `reflow design "<request>"` command | harness | CLI entry | `reflow design --help`; fake-model end-to-end test | H-03 | AGENT | done (10-19) |
| H-09 | Wire `reflow design` to config, `compile_board`, catalog + resolver, design verifier | config, H-03, V-16 | runnable command | scripted model + real tsci: no-pull-up board fails then passes from config; missing key / bad config / catalog failure exit 2 | H-07, V-16 | AGENT | done (10-21) |
| H-08 | Prompts: planner, codegen, fix | contracts, tscircuit docs | `prompts/*.md` | human approved; no hardcoded model ids | — | AGENT→HUMAN | doing (awaiting human review) |

## Model + compiler (AGENT)

| ID | Goal | Inputs | Outputs | Acceptance test | Deps | Owner | Status |
|---|---|---|---|---|---|---|---|
| M-01 | Model adapters behind `complete(system, prompt)` | config | `reflow/llm.py` | mock-server/unit tests per adapter; errors raise `ModelError` | D-1 | AGENT | todo |
| M-02 | Config loader (`reflow.toml` + env) | — | config dict | no secrets in repo; missing key → clear error | — | AGENT | todo |
| K-01 | `compile_board()` via `tsci` | TSX string | `CompileResult` | blinky TSX compiles; a syntax error returns ok=False with ≥1 `CompileError` | — | AGENT | todo |
| K-02 | Compile-error parser + trimming | tsci stderr | `CompileError[]`, ≤40-line tail | round-trip on 5 recorded stderr samples | K-01 | AGENT | todo |

## Parts

| ID | Goal | Inputs | Outputs | Acceptance test | Deps | Owner | Status |
|---|---|---|---|---|---|---|---|
| P-01 | Catalog client | category query | `CatalogPart[]` | "4.7k 0402" returns ≥1 in-stock part with a real LCSC id; network error raises `CatalogError` | D-6 | AGENT | todo |
| P-02 | Resolver validity + ranking | `PartRequest`, candidates | `ResolvedPart` / `Unresolved` | package matches request; basic > stock > price; IC only if in `named_parts` | P-01 | HUMAN | done |
| P-03 | Local catalog cache / offline snapshot | catalog | cached results | second run makes no network calls | P-01 | AGENT | todo |
| P-04 | `reflow parts update`: download the jlcparts snapshot, join + inflate, CRC check, install atomically (D-6a) | jlcparts data URL | `cache.sqlite3` + `snapshot.json` at `REFLOW_PARTS_DB` | split-archive fixture installs; a missing or corrupt part fails and keeps the old database | D-6a | AGENT | done (10-21) |
| P-05 | Catalog client on the local snapshot, category-aware queries; candidates carry `category` (C2 catalog half) | `PartRequest` | `CatalogPart[]` | MCP9808 plan resolves its 4.7k/100nF/header/IC requests from a snapshot fixture | P-04 | AGENT | done (10-21); header + IC resolve once P-02b lands |
| P-02b | Resolver: reject a candidate of the wrong category (`CatalogPart.category`); typed family → orderable MPN by prefix + package, Unresolved with a question if ambiguous; for a connector, `package` is the pitch (D-6a a), not the row's package text; use `CatalogPart.fetched_at` for `ResolvedPart.fetched_at` (C2 resolver half) | candidates | `ResolvedParts` | `tests/test_parts_integration.py` C2 cases | P-05 | HUMAN | todo |
| P-06 | Retire the jlcsearch client and its tests | — | — | suite green without jlcsearch | P-05 | AGENT (removal needs the human's OK) | todo |

## Learn mode

| ID | Goal | Inputs | Outputs | Acceptance test | Deps | Owner | Status |
|---|---|---|---|---|---|---|---|
| L-01 | Interaction selection + grading + skip logic | `RunResult`, violations | `LearnInteraction` list | every interaction's `rule_id` is a real violation from the run | H-03, D-4 | HUMAN | todo |
| L-02 | Terminal screens for spot-the-bug | L-01 output | interactive prompts | scripted-input test records a `LearnRecord` | L-01 | AGENT | todo |
| L-03 | Sign-off gate | warnings, overrides | `SignOff` | `n` stops before export | — | AGENT | todo |

## Routing + output (AGENT)

| ID | Goal | Inputs | Outputs | Acceptance test | Deps | Owner | Status |
|---|---|---|---|---|---|---|---|
| X-01 | Router wrapper (tscircuit router) | placed board | `RouteResult` | sensor board routes; `drc` from our kicad-cli run | K-01 | AGENT | todo |
| X-02 | freerouting fallback via bridges | `.kicad_pcb` | `RouteResult` | round trip on scratch demo board, zones refilled | X-01 | AGENT | todo (cut #1) |
| X-04 | Re-DRC + compare + honest partial report | routed board | `DrcSummary`, unrouted list | partial board lists unrouted nets | X-01 | AGENT | todo |
| O-01 | Fab export | routed board | `FabPackage` | gerbers/drill/pos/BOM exist; refuses without verify+DRC report | X-04 | AGENT | todo |
| O-02 | `report.json` / `report.md` | run folder | reports | includes every attempt's violations and final DRC | H-03 | AGENT | todo |
| O-03 | `report.html` (KiCanvas/iBOM) | run folder | html | opens offline | O-02 | AGENT | todo (cut #2) |

## Evaluation + launch

| ID | Goal | Inputs | Outputs | Acceptance test | Deps | Owner | Status |
|---|---|---|---|---|---|---|---|
| E-02 | Eval prompt set (≥5 boards, with hand-written expectations) | — | `evals/*.toml` | each prompt has expected nets/parts | — | HUMAN | todo |
| E-01 | Eval runner + metrics (first-pass vs post-retry pass rate, hallucinated-part rate, tokens) | E-02 | `evals/results/*.json` | reproducible with a fixed seed/model | H-07 | AGENT | todo |
| D-02 | Demo recording (simple board end to end + honest stop on a harder one) | v1 | video | real runs, no staged failures | v1 | HUMAN | todo (10-31) |

**Go/no-go: Sun 2026-10-25, evening.** `reflow design "MCP9808 breakout, I2C header, 3.3V"` produces a verifier-clean compiled board within 3 attempts on ≥ 3 of 5 eval prompts, with zero part numbers outside the resolver. **No-go → cut routing to v1.1** and launch "design + verify" on 11-01.
