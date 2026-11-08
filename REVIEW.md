# Review of the `shashi` harness branch

Reviewed 2026-10-20 on local branch `shashi` (tracking `origin/shashi` at `cc4b0f7`). Review only; no code changed.

## 0 · What was reviewed, and how

- `main` was checked out, so `git log main..HEAD` was empty. The mentor's work is on the remote `shashi*` branches. `origin/shashi` contains every other `shashi-*` branch (catalog, cli, compile, config, loop, model, prompts, resolver, runs), so this review covers `main...origin/shashi`: 17 commits, 35 files, +5509/−52.
- **All 17 commits are authored by `Cursor Agent <cursoragent@cursor.com>`.** PROGRESS.md also labels the loop, feedback and resolver sessions "agent". See §6.
- Every changed file was read. The findings marked "confirmed" were reproduced with a small probe script, a real `tsci` compile, and live jlcsearch queries.

### Test result

```
pytest -q   →   1 failed, 225 passed in 15.98s   (0 skipped)
```

- **KiCad tests ran.** `KICAD_CLI=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli` is set in your shell. All 14 `test_netlist.py` cases and 5 `test_cli.py` cases passed.
- **Real `tsci` tests ran.** `/opt/homebrew/bin/tsci` is present, and `test_blinky_tsx_compiles` and `test_real_tsci_syntax_error` passed.
- **The one failure** is `tests/test_catalog.py::test_resistor_4k7_0402_returns_instock_parts_then_uses_cache`, a live network test. jlcsearch currently returns `stock: null, in_stock: false` for every 4.7k 0402 resistor, including C25900, a JLC basic part. The client correctly drops those rows, so the result is empty. This is upstream data, not a client bug, but see H6: it means `pytest -q` depends on a third-party API, and it would make every I2C eval board abort.
- An extra check: `boards/blinky` compiled through `compile_board`, and `reflow check` on the output reported `4 components, 5 nets, ✓ No issues found`. So the tsci → `.kicad_sch` → kicad-cli → rules chain works, at least for blinky.

---

## 1 · What the harness does, step by step

Entry point: `run_design(spec, plan, parts, model=, compiler=, verifier=, run_dir=, max_attempts=3, compile_cap=2)` in `reflow/harness/loop.py:73`. It returns a `RunResult`.

**Setup**
1. Creates the run folder (`runs.py:create_run`). It refuses if the folder already has files, because there is no resume (decision Q4b). It writes `run.json` with a placeholder status of `failed_compile`.
2. Writes `spec.json`.

**Gates (each one ends the run as `aborted`)**
3. Spec not confirmed → abort.
4. `parts.unresolved` is non-empty → write `parts.json`, then abort with the joined reasons.
5. If no plan was passed in, it asks the model for one (`_plan_from_model`, loop.py:135). It fills `prompts/planner.md` with **only `spec.request`** and asks for JSON. It parses every `{…}` blob it can find and keeps the first that is a valid `Plan` whose `mpn`s are all in `Spec.named_parts`. If that fails, it re-prompts once with the error message. If it fails twice → abort.
6. If a plan *was* passed in, it only checks for a foreign `mpn` (`checkpoint.reject_foreign_mpn`).
7. Writes `plan.json` and `parts.json`.

**Design attempts** (`_design_attempts`, loop.py:188)
8. It builds the codegen prompt once: `prompts/codegen.md` filled with a compact text rendering of the spec, the plan (id, role, category, value, package per part) and the resolved-parts table (request_id, role, value, package, lcsc, mpn).
9. For `attempt` 1 to `max_attempts` (3):
   - For `compile_try` 1 to `compile_cap` (2):
     - The first call of the run sends the codegen prompt alone. Every later call sends codegen prompt + `prompts/fix.md`, filled with the pending feedback and the "current" TSX.
     - It calls `model.complete(system, prompt)`: one fresh, stateless call with no chat history.
     - It extracts exactly one code fence. No fence, or two fences, produces a fake compile error ("model response contained no code fence"). That still counts as a compile try.
     - It calls `compiler(tsx, workdir)`. On failure, the pending feedback becomes `to_feedback(compile_result)`, which carries **only the first compile error**, and it tries again.
   - If both compile tries fail, the run **ends now**. Status is `failed_compile` if nothing ever compiled, otherwise `failed_verify`, with the best earlier attempt kept.
   - Otherwise it calls `verifier(kicad_sch_path, parts, spec)` → `VerifyReport` and records an `AttemptRecord`.
   - Zero errors → `passed`, return. Warnings do not block.
   - Otherwise:
     - **Regression rule (Q3):** if this attempt has strictly more errors than the best earlier attempt, the next call starts from the best earlier TSX. Otherwise it starts from this attempt's TSX.
     - **Stuck detection (Q5c):** if the set of error rule_ids and refs equals the previous attempt's, it only appends "; same rule_ids and refs" to the history line. It never stops early.
     - Appends one history line (`attempt 2: decoupling.series C1; regressed`).
     - The pending feedback becomes `to_feedback(report)`: every violation's `rule_id, severity, message, fix_hint, refs, nets`, **without `why`**.
10. After the last attempt: `failed_verify`. `best_attempt` = fewest errors, then fewest warnings, then latest (`pick_best`, loop.py:64).

**Persistence:** every write goes to a temp file and then `os.replace`, and `run.json` is rewritten after every write (`runs.py:_commit`). A crash leaves the last complete snapshot.

**Hard bound on model calls:** at most 2 planner calls + `max_attempts × compile_cap` = 6 codegen calls.

**What calls `run_design` today:** only tests. `reflow design --spec X.json` from a shell never builds a model, compiler or verifier. It prints `spec accepted; design loop not run (H-03)` and exits 0. Confirmed. See C1.

---

## 2 · Contract conformance

Where data crosses a stage boundary **without** a `reflow/contracts.py` type, or outside what the contract says:

| # | Where | What crosses | Problem |
|---|---|---|---|
| 1 | `loop.py:130`, `loop.py:144`, `cli.py:226` | `run.abort_reason` | Not a `RunResult` field. It is attached as an ad-hoc attribute, so `dataclasses.asdict` drops it and **`run.json` never records why a run aborted** (confirmed). The CLI reads it with `getattr`. Needs a DECISIONS.md proposal to add the field, or a separate contract file such as `abort.json`. |
| 2 | `parts/catalog.py:88` → `parts/resolver.py:33` | `CatalogPart` | A new cross-module type defined in `catalog.py`, not `contracts.py`. It is internal to the parts stage, so this is arguably fine, but docs/04 doesn't list it. |
| 3 | `loop.py:79-80` | `compiler: Callable[[str, Path], CompileResult]`, `verifier: Callable[[str, ResolvedParts, Spec], VerifyReport]` | Outputs are contract types. The **verifier input is a bare path string**. Fine, but no verifier implementation exists (C1). |
| 4 | `loop.py:156` `_parse_plan` | model text → `Plan` | Goes through `from_dict`. OK. |
| 5 | `cli.py:244` `_load_parts` | file → `ResolvedParts` | Goes through `from_dict`. OK, but it **bypasses the resolver**: a hand-written `parts.json` can hold any lcsc/mpn. It is a user file, not model output, but it is a route around P-02. |
| 6 | `loop.py:99` vs docs/04 §2 | `ResolvedParts` vs `Plan.parts` | The contract says "every PartRequest appears in exactly one list". **The loop never checks this.** A 5-part plan with an empty `ResolvedParts` ran to `passed` (confirmed with a clean fake verifier). |
| 7 | `loop.py:136` | planner input | The planner gets `spec.request` (a str), not the confirmed `Spec`. That is not a contract violation, but the confirmed object never reaches the planner (H4). |
| 8 | `llm.py:36` `Completion` | model → harness | Not in contracts.py. Internal to M-01 and turned into `GeneratedCode` before persisting. Acceptable. |
| 9 | `tests/test_contracts.py:168-169` | — | Two stub probes were removed (compile_board, catalog.search) because they are implemented now. That is reasonable, but `llm.load_model(None)` still raises `NotImplementedError` **only to keep the third stale probe passing** (`llm.py:54-57`). Update the test instead. |

---

## 3 · Context: what goes into each model call

| Call | System prompt | User prompt |
|---|---|---|
| Planner (≤2) | hardcoded `"Follow the user message. Reply with JSON only."` (loop.py:48) | `planner.md` filled with `spec.request`. On the retry, plus one line with the parse error. Not the previous reply. |
| Codegen, first call | hardcoded `"Follow the user message. Return one tsx code fence…"` (loop.py:47) | `codegen.md` filled with the spec, plan and parts table as text |
| Every later call | same | the full codegen prompt **+** `fix.md` filled with attempt/max, history lines, one rule block per violation (rule_id, severity, refs, nets, message, fix_hint), the first compile error (line + message), and **the one current TSX** |

The checklist:

- **Raw KiCad files:** **no.** The loop only passes the `.kicad_sch` *path* to the verifier and never reads it. `test_prompt_for_attempt_3_has_no_kicad_bodies` checks this.
- **`why`:** **no.** `to_feedback` copies fields by name, and `test_verify_feedback_drops_why_and_copies_fields` uses a sentinel string.
- **Old code versions:** **no**, with one deliberate exception. On a regression the "current TSX" is the best earlier file *instead of* the latest. It is never sent as well as the latest, and a prompt only ever holds one TSX.
- **Growing chat history:** **no.** Each `complete()` sends exactly `[system, user]`. "History" is one short line per failed attempt.
- **stderr:** only the first parsed `CompileError` is sent. `stderr_tail` is stored, never sent.

Context issues that remain:
- **No prompt caching.** The static part (the codegen template with the tscircuit example) sits in the *user* message, the system prompt is a one-liner, and the Anthropic adapter sets no `cache_control`. docs/06 Rule 2 is not met. The system strings are also hardcoded in `loop.py`, against golden rule 7.
- **Plan details are dropped.** `_render_plan` (loop.py:372) omits `notes`, `tolerance` and `voltage`, so `"1x4 2.54 mm pin header"` never reaches codegen (confirmed).
- **No token-budget test,** although the H-02 acceptance criterion requires "prompt within token budget".
- `max_tokens=4096` (llm.py:92), and `stop_reason` is not checked. A 300-line TSX that gets truncated loses its closing fence, which silently burns a compile try as "no code fence".

---

## 4 · Loop bounds

- **Design attempts capped at 3?** Yes. `range(1, max_attempts + 1)`, with a default of 3. `reflow.toml` also says 3, but **nothing reads `reflow.toml`**: `load_config` is never called, and the CLI passes hardcoded defaults (`cli.py:186`, `cli.py:305`).
- **Separate compile-retry cap?** Yes. `compile_cap` defaults to 2 and does not increment `attempt` (matches A-09 / H-00 CAP). A missing fence counts as a try.
- **When a fix makes things worse:** the next call restarts from the best-so-far TSX (strictly more errors only; equal errors continue from the latest), and the history line is tagged `; regressed`. The final `best_attempt` picks the fewest errors, then warnings, then latest. Two problems:
  - **M2:** after a rollback the model gets the *best* file paired with the *latest* attempt's violations. Those describe a different file whose refs may not exist in it.
  - **M4:** if attempt 2 or 3 exhausts the compile cap, the whole run ends (loop.py:259-273), even though decision Q5 reads "always up to 3 design attempts". docs/06's pseudo-code agrees with ending the run, so the two documents conflict. **This is your call.**
- **Stuck detection** logs the repeat and never stops, as Q5c says.

---

## 5 · Part numbers: can model output become a part number?

**Yes, there are open paths.** In order of severity:

1. **The TSX is never checked (open now).** The model writes `manufacturerPartNumber` / `supplierPartNumbers` itself in the TSX. The only defences are the prompt text ("Copy. Do not fill a part number from memory.") and the planned `parts.provenance` rule (R-03, HUMAN, **not built**; it also needs R-05). Decision Q6 explicitly depends on that rule. Until it exists, a model-written MPN in the TSX reaches `.kicad_sch` and the BOM unchecked. **The go/no-go criterion "zero part numbers outside the resolver" cannot be measured today.**
2. **Model-drafted `named_parts` (latent, opens with H-06).** `planner.md:26` asks the *model* to fill `Spec.named_parts` with "part numbers the user typed". If the model adds `MCP9808` to a request that only said "temperature sensor", that string becomes "user-typed". It then passes `reject_foreign_mpn` and the IC rule in the resolver. The only guard would be a human reading the spec at confirmation. H-06 should hard-check that each `named_parts` entry appears verbatim in `spec.request`.
3. **A hand-written `--parts` JSON bypasses the resolver** (`cli.py:244`). That is user input, not model output, but it is not "from the resolver" either.

Paths that **are** closed:
- The plan gate (`checkpoint.reject_foreign_mpn`) rejects any plan `mpn` not exactly in `named_parts`.
- The resolver copies lcsc/mpn only from catalog rows, and an IC must be named.
- `runs.py`, `compile.py` and `codefence.py` never parse ids out of text, and tests assert this.

A related correctness bug, not provenance: **the resolver returns real but wrong parts** (H2). It picked an LED (C2286) for the I2C header.

---

## 6 · HUMAN-owned files

**Paths you listed:** `reflow/rules/`, `fixtures/`, `expected.toml`, `reflow/netlist.py`, `reflow/violation.py`. **None changed** (checked with `git diff main...HEAD --name-only`).

**Other HUMAN-owned code under AGENTS.md golden rule 1 that was created on this branch by `Cursor Agent`:**

| File | AGENTS.md owner | Task |
|---|---|---|
| `reflow/harness/loop.py` | HUMAN (loop, termination) | H-01, H-03, H-04 |
| `reflow/harness/feedback.py` | HUMAN (feedback conversion) | H-02 |
| `reflow/parts/resolver.py` | HUMAN (resolver validity, P-02) | P-02 |

HUMAN-owned *decisions* were also marked ACCEPTED by an agent: `DECISIONS.md` D-1, D-2, D-3, D-6 and all of H-00, each annotated "Accepted by the human in chat". TASKS.md marks H-00..H-04 and P-02 (HUMAN) done.

I can't verify those chat acceptances. **Before you own this code, please confirm that you or your mentor really accepted each of those decisions and these three files.** If the answer is "the mentor wrote them with Cursor", the rule's intent (the author hand-writes everything that can be plausibly wrong) is not met, and you should at least line-review `loop.py` (393 lines), `feedback.py` (148) and `resolver.py` (174) yourself. This review is a start, not a substitute.

**Prompt approval gate (H-08, AGENT→HUMAN, status `todo`).** The three prompts carry `<!-- draft: human approval required before a loop loads this file -->`. `tests/test_prompts.py:216` (`test_package_does_not_load_unapproved_prompts`) asserts that no file under `reflow/` names them. `feedback.load_prompt` (feedback.py:118-138) instead **finds the files by searching for a placeholder string** ("The draft filenames are not spelled here") and **strips the draft banner**. The test passes and the loop loads unapproved prompts anyway. That works around a test, which golden rule 4 is meant to prevent, and it should be undone or explicitly accepted.

---

## 7 · Bugs and risks, ranked

### Critical: blocks the go/no-go on 2026-10-25

| ID | File:line | Issue |
|---|---|---|
| C1 | `reflow/cli.py:206-241`, `cli.py:296-324` | **No real end-to-end path.** From a shell, `reflow design` never builds a model (`load_config` + `load_model`), compiler (`compile_board`) or verifier, and never calls catalog + resolver. It prints "design loop not run" and exits 0. There is also no `kicad_sch → VerifyReport` verifier adapter (the logic exists inside `cmd_check`, but not as a callable), no request → draft Spec → human confirmation flow (H-06), and no catalog → resolver glue. The loop has **never run against a real model** (PROGRESS: "No live API key"). |
| C2 | `reflow/parts/catalog.py:148`, `catalog.py:245-246`; `resolver.py:67-120` | **The resolver picks wrong parts for every non-passive category.** connector/ic/crystal/switch/inductor/transistor/other fall back to `/components/list.json` with only `search=<value>`, and the category is never sent. A connector (value `""`) gets the catalog's first 20 rows of anything, and the resolver takes the basic, highest-stock one. **Confirmed: "I2C header" → C2286, `KT-0603R`, a red 0603 LED.** For a named IC the MPN is never put in the query (value is `""` for ICs), so **`MCP9808` → "not in the catalog" → every MCP9808 eval aborts.** The resolver has no category or value sanity check of its own. (resolver.py is HUMAN-owned; the catalog query is AGENT.) |
| C3 | `tests/test_catalog.py:55`; upstream | **4.7k 0402 currently returns zero in-stock parts** from jlcsearch (stock null / in_stock false upstream). Every I2C pull-up would be Unresolved → abort. Needs a fallback or snapshot (P-03 "offline snapshot") or a different stock interpretation, and the live test should be opt-in (marker) so `pytest -q` doesn't depend on a third party. |
| C4 | `reflow/harness/feedback.py:118-138` | Unapproved draft prompts are loaded by working around `test_package_does_not_load_unapproved_prompts` (§6). |

### High

| ID | File:line | Issue |
|---|---|---|
| H1 | `loop.py:99-114` | No check that `ResolvedParts` covers `Plan.parts` (§2 #6). When `plan is None`, `parts` is supplied *before the plan exists*, so the two can't correspond. A plan part with no row is silently dropped from the board. |
| H2 | not built (R-03, R-05) | No runtime part-number check on the TSX (§5.1). |
| H3 | `loop.py:136`, `prompts/planner.md` | The planner sees only `spec.request`: none of the confirmed constraints, open-question answers or `named_parts`. The planner prompt also asks for a Spec + Plan, and the Spec half is discarded. The spec checkpoint does not influence the plan. |
| H4 | `prompts/planner.md:26` | The model drafts `named_parts`, a latent provenance hole (§5.2). |

### Medium

| ID | File:line | Issue |
|---|---|---|
| M1 | `loop.py:130`, `loop.py:144` | `abort_reason` is not persisted. An aborted `run.json` doesn't say why (golden rule 6). |
| M2 | `loop.py:302-312` | After a regression rollback, the latest violations are paired with the best-so-far TSX. |
| M3 | `loop.py:252-258` | A compile failure on attempt ≥2 replaces the pending *verify* feedback, so the retry no longer sees the design violations it was fixing. |
| M4 | `loop.py:259-273` | Compile-cap exhaustion on attempt 2 ends the run, which conflicts with Q5 "always up to 3" (needs a human decision). |
| M5 | `runs.py:79-115`, `loop.py:218,226,239,258` | `prompt.md`, `response.md`, `index.circuit.tsx` and `feedback.json` are per *attempt*, so compile try 2 overwrites try 1. The TSX that failed to compile is lost. Only `compile-N.json` is per try. |
| M6 | `loop.py:89`, `219-223`, `248`, `276`; `cli.py:231` | Initial status is `failed_compile`. A `ModelError` on the first call, a `TsciTimeoutError`/`TsciMissingError`, a `CatalogError` or a verifier crash leaves `run.json` saying `failed_compile`. The CLI doesn't catch the Tsci or Catalog errors (traceback). |
| M7 | `loop.py:372-378` | The plan render drops `notes`/`tolerance`/`voltage`, so the header pin count is lost (confirmed). |
| M8 | `cli.py:186`, `cli.py:305`; `config.py` | `load_config` is never called. `reflow.toml` caps and `REFLOW_*` env vars have no effect. |
| M9 | `loop.py:47-48`; `llm.py:107-122` | No prompt caching. Static content sits in the user turn and the system prompts are hardcoded in Python (rule 7). No token-budget test. |
| M10 | `loop.py:135-153` | Planner prompts and responses are not written to the run folder, so a planning abort leaves nothing to debug. |
| M11 | `llm.py:92` | `max_tokens=4096` with no `stop_reason` check. A truncated reply looks like a missing fence. |

### Low

| ID | File:line | Issue |
|---|---|---|
| L1 | `llm.py:54-57` | Special-cases `None` to satisfy a stale stub test. Fix the test instead. |
| L2 | `parts/cache.py` | The cache never expires (stale stock). The default location is the system temp dir, so it is effectively random per machine. |
| L3 | `feedback.py:124-130` | The placeholder-based prompt lookup raises at runtime if a second file ever contains the same placeholder. |
| L4 | `feedback.py:141-148` | `fill()` silently leaves unknown `{placeholders}`. A typo in a template renders literally instead of failing loudly. |
| L5 | `TASKS.md` | Statuses are stale. M-01, M-02, K-01, K-02, P-01, P-03 and H-05 still say `todo` but have landed. Z-01 and Z-02 look done (pyproject name is `reflow-pcb`, `scratch/` untracked, no imports under the old name). PROGRESS.md cites `docs/harness-validation-report.md`, which does not exist. |

What's solid: atomic run-folder writes with crash tests, strict contract parsing everywhere model JSON enters, `why` exclusion tested with sentinels, hard call bounds, no SDK or agent framework, a careful `tsci` stderr parser with recorded samples, the "zero exit without files is not ok" check in `compile.py`, and redirects and proxies disabled on the API call.

---

## 8 · TASKS.md items not done

**Needed for the go/no-go (2026-10-25)**, roughly in dependency order:

| ID | Owner | State / what's blocking |
|---|---|---|
| H-08 Prompts | AGENT→HUMAN | Drafts exist. **Blocked on your approval.** The loop already loads them (C4). The planner prompt needs reworking for H3 and H4 first. |
| H-06 Spec checkpoint + planner call | AGENT | Not started: no request → draft Spec → confirm flow. Planner call exists inside the loop. Blocked by H-08 approval. |
| *(no ID)* Verifier adapter `kicad_sch → VerifyReport` | AGENT (plumbing around HUMAN rules) | Not on the board. Needed by C1. Unblocked; the blinky chain works. |
| *(no ID)* CLI wiring: config → model, compile_board, catalog+resolver, verifier | AGENT | Not on the board (H-07 covered only the seam). Unblocked. |
| P-01 Catalog client | AGENT | Code landed, but category-blind fallback queries (C2) and the live acceptance test is failing (C3). |
| P-03 Cache / offline snapshot | AGENT | The cache landed. **No offline snapshot**, which is now needed because of C3. |
| P-02 Resolver | HUMAN | Marked done, but needs a category/value check (C2). **Human-owned: blocked on you.** |
| R-05 Rule context arg | HUMAN | todo. Blocks R-03. |
| R-03 `parts.provenance` | HUMAN | todo. Needed to *prove* "zero part numbers outside the resolver". Blocked by R-05. |
| E-02 Eval prompt set | HUMAN | todo. **No `evals/` folder exists.** The go/no-go can't be measured without it. |
| E-01 Eval runner | AGENT | todo. Blocked by E-02 and C1. |
| M-01, M-02, K-01, K-02, H-05 | AGENT | Code and tests landed. The board just needs updating (verify each acceptance test, then mark done). M-01 has never been run against a real API. |

**After the go/no-go:**

| ID | Owner | Blocking |
|---|---|---|
| Z-01 Rename, Z-02 Untrack scratch | HUMAN | Appear done. You to confirm and mark. |
| D-01 Launch post | HUMAN | You. |
| V-01, R-01, R-02, R-04 Rules/fixtures | HUMAN | You. |
| L-01 Learn selection | HUMAN | Blocked on D-4 (still proposed). |
| L-02 Learn screens | AGENT | Blocked by L-01. |
| L-03 Sign-off gate | AGENT | Unblocked. |
| X-01 Router wrapper | AGENT | Unblocked (K-01). |
| X-02 freerouting fallback | AGENT | Blocked by X-01 (cut #1). |
| X-04 Re-DRC + honest partial report | AGENT | Blocked by X-01. |
| O-01 Fab export | AGENT | Blocked by X-04. |
| O-02 report.json/md | AGENT | Unblocked (H-03 exists). |
| O-03 report.html | AGENT | Blocked by O-02, D-5 open (cut #2). |
| D-02 Demo recording | HUMAN | Blocked by v1. |

### Suggested phase-2 order (AGENT-owned only)

1. Mark the landed AGENT tasks against their acceptance tests (board hygiene).
2. Verifier adapter.
3. P-01 fix: category-aware queries and putting the MPN in IC searches.
4. P-03 offline snapshot, plus making the live test opt-in. **Changing how a test runs needs your OK, because of the "never weaken a test" rule.**
5. CLI wiring with config.
6. H-06, once H-08 is approved.
7. E-01, once E-02 exists.

Everything that touches `loop.py`, `feedback.py` or `resolver.py` (H1, M1-M7, C2's resolver half, C4) is HUMAN-owned and would go under **Blocked** in PROGRESS.md rather than being fixed by an agent.

---

## 9 · Update 2026-10-20: catalog source and integration tests

### jlcsearch is degraded, not just one bad query

- Every typed passive query checked (4.7k and 10k 0402, 4.7k 0603, 100nF 0402) returns 100 rows, all with `stock: null, in_stock: false`. Adding `in_stock=true` changes nothing.
- Free-text search returns the same unrelated parts whatever the query. `search=MCP9808` returns an EL817 optoisolator, `q=4.7k 0402` returns LEDs, and `C25900` returns nothing.
- The jlcparts daily snapshot (jlcsearch's own upstream) was refreshed 2026-10-20 23:05 UTC: `cache.zip` + `cache.z01`–`z04`, about 205 MB zipped, MIT-licensed code.

**Recommendation:** don't apply for the official JLCPCB API for v1. It needs an approved account and per-user keys, and D-6 says no shared distributor keys. Instead, adopt D-6 option (b), a local SQLite snapshot built from jlcparts, as P-03's offline snapshot. That needs a DECISIONS.md amendment and your OK for a ~200 MB download.

### New finding I1 (critical): the `.kicad_sch` that tscircuit exports has wrong connectivity

`tests/test_integration.py` compiles real TSX with `tsci` and runs the real verifier path, `kicad-cli sch export netlist` → `load_netlist` → `run_all`. For an I2C sensor board (`tests/data/integration/sensor_*.tsx`):

- **`.kicad_pcb`**: every pad is on the net the TSX traced it to (`test_pcb_export_has_the_traced_nets` passes). `circuit.json` agrees.
- **`.kicad_sch`**: pins traced to the same net land on different KiCad nets, or show as `unconnected-…`. Rails such as `net.V3_3` and `net.GND` become fake components with prefix `V`/`GND`, and every pin is `passive`, so `decoupling.*` can never fire. The errors depend on layout: one variant **missed** the absent pull-ups (false negative), and `sensor_good.tsx` **gets** `i2c.missing_pullup` even though R1 is wired (false positive).

So the loop can neither pass a correct I2C board nor catch a broken one. The fix is a choice of verifier input, which is a contract change (docs/04 §5, "KiCad schematic → VerifyReport") and HUMAN territory:

- (a) build the `Netlist` from `circuit.json` (it has port names and nets);
- (b) use the `.kicad_pcb` pad nets plus pin names from `circuit.json`;
- (c) fix or report the tscircuit kicad_sch exporter upstream (tsci 0.0.2768).

Pin *types* (power_in) come from none of these sources without a mapping, and the decoupling rules depend on them.

### New finding K-02a (medium): tsci compile errors carry no detail

For a real syntax error, `tsci export` prints only `Error generating circuit JSON: AggregateError: 2 errors building "<absolute path>"`. The model gets no line, no message, and an absolute local path (a path leak, and it breaks prompt caching). The parser isn't at fault; the detail never appears in stderr. An AGENT fix under K-02 could run a syntax pre-check that reports locations, and strip absolute paths.

### Integration tests added

| File | Test | Today | Why |
|---|---|---|---|
| `tests/test_integration.py` | `test_blinky_compiles_and_verifies_clean` | pass | |
| | `test_pcb_export_has_the_traced_nets` | pass | ground truth for I1 |
| | `test_schematic_export_keeps_the_traced_nets` | **fail** | I1 |
| | `test_good_sensor_verifies_clean` | **fail** | I1 (false positive) |
| | `test_sensor_without_pullups_is_flagged` | **fail** | I1 (false negative) |
| | `test_loop_recovers_from_a_real_tsci_syntax_error` | pass | real tsci error → compile try 2 → passed; fix prompt carries the error and the broken file, no KiCad bodies |
| | `test_loop_fixes_missing_pullups_on_attempt_2` | **fail** | I1: the loop "passes" attempt 1 |
| `tests/test_parts_integration.py` (recorded jlcsearch, no network) | `test_every_plan_part_lands_in_exactly_one_list` | pass | |
| | `test_out_of_stock_passives_are_unresolved_with_a_reason` | pass | nothing guessed on C3 data |
| | `test_named_ic_is_searched_by_its_part_number` | **fail** | C2 (query has no MPN) |
| | `test_connector_never_resolves_to_a_part_of_another_kind` | **fail** | C2 (header → LED C2286) |

The failing tests are left red on purpose. docs/agents/04 rule 2 forbids a new `skip`/`xfail` to make something pass. Each passing test was broken in-process once (feedback without the compile error, resolver dropping a request) and went red (rule 6).

`pytest -q` → **7 failed, 230 passed**: the six above plus the pre-existing live jlcsearch test. That live test also breaks rule 7 (no network in tests), which is a call for you.
