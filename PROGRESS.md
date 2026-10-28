# PROGRESS (append-only)

Newest entry at the bottom. Never edit or delete old entries. Every session (human or agent) appends one.

Format:
```
## YYYY-MM-DD · <who> · <task IDs>
Did: ...
Tests: <command> → <result>
Next: ...
```

## Blocked

(Agents: add blockers here with date + task ID; the human clears them.)

- 2026-10-20 · verifier input (docs/04 §5) · tscircuit's `.kicad_sch` export has wrong connectivity (traced pins split across nets or `unconnected`, rails become fake `V`/`GND` components, all pins `passive`). The verifier gives both false positives and false negatives on I2C boards; `.kicad_pcb` and `circuit.json` are correct. Choosing a new verifier input is a contract change and HUMAN. Evidence: `tests/test_integration.py`, REVIEW.md §9.
- 2026-10-20 · P-02 (HUMAN) + P-01 · resolver picks a part of the wrong kind (I2C header → LED C2286) and a named IC is never searched by its MPN. Catalog query half is AGENT (P-01); the resolver category check is HUMAN. Evidence: `tests/test_parts_integration.py`.
- 2026-10-22 · i2c rule (HUMAN, reflow/rules/i2c.py) · a pull-up to a rail the chip isn't powered from passes `i2c.missing_pullup`, so a real eval board (Lightning, run 20261022T192231Z attempt 2) was verifier-clean with SDA/SCL pulled up to a dead V3_3. Failing test: `tests/test_i2c_pullup_rail.py::test_pullups_to_an_unpowered_rail_fail_verify`. The human is writing the rule.
- 2026-10-20 · D-6 / P-03 · jlcsearch stock data and free-text search are broken upstream. Proposed: jlcparts SQLite snapshot (~205 MB). Needs a DECISIONS.md amendment and the human's OK to download.

---

## 2026-10-07 → 2026-10-17 · human · (history, summarized from NOTES.md and git log)
Did: toolchain round trip (KiCad → DSN → freerouting → SES → KiCad); switched substrate atopile → tscircuit; netlist loader + generic fixture tests; rules decoupling.series, i2c.missing_pullup/duplicate_pullup, address.floating; `reflow check` CLI; real club board fixtures (clean + original series-cap bug); renamed reflow → reflow.
Tests: `pytest -q` → 33 passed (2026-10-17).
Next: finish rename (Z-01), launch post for `reflow check` (D-01), harness decisions (H-00).

## 2026-10-17 · agent (Claude) · C-01 + docs/scaffold
Did: added `reflow/contracts.py` (22 stage contracts, strict from_dict), `docs/examples/*.json`, `tests/test_contracts.py` (49 tests), stubs `reflow/{llm,compile,route,export}.py`, `reflow/parts/catalog.py`; docs 00–08; README; TASKS.md; AGENTS.md/CLAUDE.md; DECISIONS.md; docs/agents/01–09; module READMEs; `runs/` added to .gitignore. No HUMAN-owned code touched. Rename import edits left uncommitted for the human (Z-01).
Tests: `python3 -m pytest -q --noconftest tests/test_contracts.py` → 49 passed (Linux VM, Python 3.10). KiCad-backed tests not run here (no kicad-cli); run `pytest -q` on the Mac.
Next: human answers H-00 (Q3–Q6) and decisions D-1…D-6.

## 2026-10-19 · agent (integration) · M-02, M-01, K-01, K-02, P-01, P-03, H-08, H-05, H-06, H-07
Did: agent-owned plumbing landed on `shashi`. Config loader (`reflow.toml` / env, `max_attempts=3`, `compile_cap=2`, missing `REFLOW_API_KEY` raises `ConfigError`). Model adapter `complete(system, prompt) -> Completion` with `ModelError` on 401/500, no retry and no tools, plus `extract_code_fence` (`str | None`). `compile_board` via `tsci` (blinky ok, syntax error `ok=False`, missing `tsci` raises). Catalog client and cache for jlcsearch; the client does not rank or pick a winner. Prompt drafts in `prompts/planner.md`, `prompts/codegen.md`, `prompts/fix.md` (human approval still required before a loop loads them). Run-folder writer `reflow/harness/runs.py`. `reflow design` loads a confirmed Spec JSON, refuses `confirmed: false`, and rejects a Plan `mpn` outside `Spec.named_parts`. H-01, H-02, H-03, H-04, P-02, and L-01 were not written. The harness loop is not implemented.
Tests: validation `pytest -q` on `51129f7f3e31bf2a0af9ec5b7df1d212ecc03ffb` → 154 passed. Verdict PASS (`docs/harness-validation-report.md`, worker `bc-3b0eca06-da2e-525f-a07f-096a3c0830e5`). The same run also reported 4 failed and 28 errors in `tests/test_cli.py` and `tests/test_netlist.py`; those match `dde218a` (KiCad 10 fixtures, KiCad 7 CLI) and are not from this plumbing.
Next: human writes H-00 acceptances, the harness loop (H-01..H-04), resolver validity (P-02), and learn-mode selection (L-01). End-to-end `reflow design` stays parked until that loop exists.

## 2026-10-19 · agent · P-02
Did: added `reflow/parts/resolver.py`. `resolve(requests, named_parts, candidates)` returns `ResolvedParts`. Every request is in exactly one of `resolved` / `unresolved`. Package must match the request (same comparison as the catalog client, including a parenthetical suffix). Ranking is JLCPCB basic, then higher stock, then lower price; a tie keeps catalog order. The resolver does not call `catalog.search` and does not sort the candidate list in place. An IC whose mpn is not in `named_parts` is `Unresolved`. A named IC missing from the candidates is `Unresolved` with a reason that names the mpn and the catalog. An LCSC id is copied from the selected candidate only. Notes/TSX are not read. `DECISIONS.md` was not edited. Branch `shashi-resolver` was cut from `origin/shashi` `c7830a2` and is not merged.
Tests: `python3 -m pytest -q tests/test_resolver.py` → 20 passed. Short-circuiting `_pick` to the first candidate failed the three ranking tests; the sort was restored. `python3 -m pytest -q` → 171 passed, 7 skipped, 28 errors. Skips: 5 `kicad-cli` not found (`tests/test_cli.py`), 2 `tsci` not installed (`tests/test_compile.py`). Errors: 28 `FileNotFoundError: kicad-cli` in `tests/test_netlist.py` (pre-existing; KiCad is not installed here).
Next: the harness loop calls `resolve` with each request's `catalog.search` result. Do not merge this branch into `shashi` from here.

## 2026-10-19 · agent · H-00, H-01, H-02, H-03, H-04, H-07
Did: Marked D-1, D-2, D-3, D-6, and H-00 (Q3, Q4, Q5, Q6, COMPILE_CAP, status) ACCEPTED in DECISIONS.md, dated 2026-10-19, accepted by the human in chat. D-4, D-5, and P-1 stayed proposed. Implemented the design loop on `shashi-loop` (cut from `c7830a2`): compact feedback from the fix template, compile cap 2, best-attempt selection, and the abort rules. `reflow design` runs that loop when a model, compiler, and verifier are supplied. No live API key. Learn mode was not implemented. Did not merge `origin/shashi` at `5e561fb` (P-02 resolver) and did not edit resolver files.
Tests: `python3 -m pytest -q` → 171 passed, 7 skipped, 28 errors. The errors are `tests/test_netlist.py` setup (`kicad-cli` missing). The skips are `tests/test_cli.py` (no `kicad-cli`) and `tests/test_compile.py` (no `tsci`). `tests/test_harness.py` and `tests/test_design_cli.py` passed.
Next: bring P-02 onto this branch only when the human wants the resolver in the loop. D-4 (learn mode) stays open. Fresh check: `python3 -m pytest -q tests/test_harness.py tests/test_design_cli.py`.

## 2026-10-20 · agent (Claude) · review + integration tests (no task ID)
Did: reviewed `origin/shashi` (checked out as local `shashi`) into REVIEW.md. Added `tests/test_integration.py` (real tsci + kicad-cli + rules + design loop, scripted model), `tests/test_parts_integration.py` (plan → catalog → resolver on recorded jlcsearch responses in `tests/data/jlcsearch_plan/`), and TSX inputs in `tests/data/integration/`. Found that tscircuit's `.kicad_sch` export loses connectivity (see Blocked). Failing tests are left red; no skip/xfail added. Each passing new test was sabotaged in-process once and went red. No production code, HUMAN-owned file, fixture, or existing test changed.
Tests: `pytest -q` → 7 failed, 230 passed. Failures: 4 integration (schematic connectivity), 2 parts (resolver/catalog C2), 1 pre-existing live jlcsearch test (upstream data). KiCad 10 via `KICAD_CLI`, tsci 0.0.2768.
Next: the human picks the verifier input (circuit.json vs kicad_pcb) and the catalog source (jlcparts snapshot). Then AGENT work: verifier adapter, P-01 query fix, CLI wiring.

## 2026-10-20 · agent (Claude) · V-1 proposal (no task ID yet)
Did: drafted Decision V-1 (proposed, not accepted): verify `circuit.json` instead of tscircuit's `.kicad_sch`, with IC pins taken from HUMAN-verified part cards rather than TSX labels. Wrote `docs/proposals/V-1-circuit-json-ground-truth.md`, `V-1-contract.patch` (new `Citation`/`CardPin`/`PartCard`/`PIN_KINDS`, frozen-list + example updates, docs/02/04/06), `V-1-loop-HUMAN.patch` (one line in HUMAN-owned `loop.py`, for the human to apply), and `V-1-draft-card-MCP9808.toml` (draft, `verified_by` empty) from Microchip DS20005095B Table 3-1, cross-checked against EasyEDA C129490. Added the V-1 row to DECISIONS.md under Proposed. Did not apply either patch to the checkout. Found that the agent-written `tests/data/integration/sensor_*.tsx` uses a wrong MCP9808 pinout (A0 on pin 3; the datasheet says Alert), which is the failure mode V-1 targets.
Tests: both patches applied in a throwaway worktree → `tests/test_contracts.py` 51 passed; `pytest -q` 229 passed, 1 failed (pre-existing live jlcsearch). Example card corrupted twice (bad kind, unknown key) → contract tests red both times. Checkout unchanged: `pytest -q` → 7 failed, 230 passed (same as the previous entry).
Next: the human accepts or edits V-1, applies `V-1-loop-HUMAN.patch`, and verifies the MCP9808 card. Then AGENT: apply the contract patch in one commit, V-10, V-11, V-14, V-16.

## 2026-10-20 · agent (Claude) · V-2 proposal (no task ID yet)
Did: drafted Decision V-2 (proposed): generic rules (Python, maintainers) + a fixed set of requirement kinds (HUMAN rules) + per-chip requirements as data in signed part cards, with citation and verbatim quote. `docs/proposals/V-2-rule-framework.md`, plus a DECISIONS.md row. Confirmed ST's STM32_open_pin_data is BSD-3-Clause and types all 48 STM32F103C8 pins (9 Power, NRST Reset, BOOT0 Boot, 37 I/O). AN2586 capacitor values not verified; the doc's STM32 example marks them as placeholders. No code or contract changed.
Tests: none run (docs only). Checkout state unchanged from the previous entry.
Next: the human decides V-1, then V-2.

## 2026-10-20 · agent (Claude) · V-2 proposal, sources section
Did: added §10 to `docs/proposals/V-2-rule-framework.md`: seed sources (vendor pin data, KiCad libraries, EasyEDA as cross-check only, datasheets cited not redistributed), CC-BY-SA 4.0 proposal for `cards/`, and the contribution flow (card + good/bad board + `reflow card check` + two signatures). Checked the local KiCad 10 library: MCP9808 pins and types match DS20005095B but its Datasheet field points to 22203b; STM32F103C8 VSS pins 35/47 are `passive` while ST data says Power. Docs only.
Tests: none run.
Next: unchanged (human decides V-1, then V-2).

## 2026-10-20 · agent (Claude) · V-2 rewrite: project rules file
Did: replaced the V-2 draft with a shorter design: general rules ship with reflow; a project adds `rules.toml` (six `need` kinds, required `source` and `why`) written by the student from datasheets; reflow sends the rules to codegen as constraints and checks each at verify; a separate Claude skill (draft `docs/proposals/datasheet-tutor-SKILL.md`, not part of reflow) explains datasheets and writes the file on request. V-2 now amends V-1 (b): pin maps come from vendor data, then KiCad, then a hand card override. Added `docs/proposals/examples/rules.toml` (7 rules for the MCP9808 board, from DS20005095B). Updated the V-2 row in DECISIONS.md. Docs only.
Tests: example rules.toml parsed with tomllib; field check passed. No suite run (no code changed).
Next: the human decides V-1 and V-2.

## 2026-10-20 · agent (Claude) · V-1 contract change (commit b444ba2), V-2 contract draft
Did: the human accepted V-1 and V-2 in chat. Committed b444ba2 on `shashi`: V-1 and V-2 marked ACCEPTED in DECISIONS.md; `Citation`, `CardPin`, `PartCard`, `PIN_KINDS` in contracts.py, frozen in test_contracts.py, `docs/examples/part_card.json`; docs/02/04/06. docs/04 §2b/§5 and the contracts.py comment were reworded from the drafted patch to follow V-2's amendment of V-1 (b): pin maps come from vendor data, then KiCad, with a signed card as override. The applied `V-1-contract.patch` was dropped (the commit is the record). `loop.py` is untouched; `docs/proposals/V-1-loop-HUMAN.patch` still applies and is for the human. Drafted `docs/proposals/V-2-contract.patch` (not applied): `RULE_NEEDS`, `ProjectRule`, `ProjectRules`, `Spec.rules_file = ""`, frozen lists, `docs/examples/project_rules.json`, spec.json example, docs/04 §0/§0b. It also adds `rules_file` to the hand-listed round trip in `tests/test_design_cli.py`, because the patch otherwise breaks that test.
Tests: committed HEAD (clean worktree) → 1 failed (live jlcsearch), rest passed. HEAD + V-2 patch → contract + design CLI tests 70 passed; full suite 232 passed, 1 failed (live jlcsearch). V-2 example with an unknown `need` → contract tests red. Working tree with this session's uncommitted integration tests → 7 failed, 234 passed (known failures, REVIEW.md §9).
Next: the human approves V-2-contract.patch and applies V-1-loop-HUMAN.patch. Then AGENT: V-10 (circuit.json loader), pin-map importer, rules.toml parser and `reflow rules check`.

## 2026-10-20 · agent (Claude) · V-2 contract change (commit 6d47281)
Did: the human approved V-2-contract.patch in chat, including the `tests/test_design_cli.py` round-trip change. Committed 6d47281 on `shashi`: `RULE_NEEDS`, `ProjectRule`, `ProjectRules`, `Spec.rules_file = ""` in contracts.py; frozen lists and the example check in test_contracts.py; `docs/examples/project_rules.json`; `rules_file` in docs/examples/spec.json; docs/04 §0 row and §0b; `rules_file` in the hand-listed round trip in test_design_cli.py. DECISIONS.md V-2 row records the approval. The applied patch file was removed.
Tests: committed HEAD in a clean worktree → 232 passed, 1 failed (live jlcsearch). Working tree with this session's uncommitted integration tests → 7 failed, 237 passed (known, REVIEW.md §9). `V-1-loop-HUMAN.patch` still applies.
Next: the human applies `V-1-loop-HUMAN.patch`. AGENT: circuit.json loader (V-10), pin-map importer, rules.toml parser and `reflow rules check`. Still uncommitted: REVIEW.md, the integration tests and `tests/data/`, the `tests/README.md` rows, and PROGRESS.md.

## 2026-10-20 · agent (Claude) · V-10
Did: added `reflow/circuit_netlist.py`: `load_circuit_json(path) -> Netlist` from tscircuit's source_* elements, as in docs/04 §5. Nets are grouped by `subcircuit_connectivity_map_key`, named from `source_net`, else `Net-(<ref>-<pin>)` or `unconnected-(…)`. `pintype` is always "" (pin kinds come from the pin map, V-12), and `function` is the raw port name. Strict: a malformed file, missing key, duplicate ref or pin, unknown component, one net name on two nets, or more than one subcircuit raises `CircuitJsonError`. Two named nets on one key (net.V3_3 traced to net.GND) raise `MergedNetsError` rather than hiding the short. Added recorded inputs in `tests/data/circuit_json/` (tsci 0.0.2768; sensor_good full, three source_*-only trims, each beside its .tsx) and `tests/test_circuit_netlist.py` (26 tests). Clarified docs/04 §5 wording: a named net keeps its name even with one port, so a lone traced SDA still reaches the I²C rule. Added the V-1/V-2 tasks (V-10..V-22, R-07, R-10) to TASKS.md and README rows. No HUMAN-owned file changed.
Tests: `tests/test_circuit_netlist.py` failed first (module missing), then 26 passed. Sabotaged in-process three ways (pick one name for merged nets; ignore connectivity keys; set pin types) → red each time. `pytest -q` → 7 failed, 263 passed: the same 7 known failures (6 intentionally red integration tests + live jlcsearch), none new. KiCad 10 via `KICAD_CLI`, tsci 0.0.2768.
Next: how a short between named nets becomes a violation instead of an exception is a HUMAN decision (V-13). AGENT next: V-14 (`.kicad_pcb` pad-net reader) or V-11 (pin-map importer); V-16 wires the loader into the verifier.

## 2026-10-20 · agent (Claude) · V-14
Did: added `reflow/pcb_nets.py`: `load_pcb_pad_nets(path) -> {(ref, pad): net}` from a `.kicad_pcb`, using `reflow.netlist.parse_sexpr` (imported, not edited). It reads both pad-net syntaxes (tscircuit `(net 3 "SDA")`, KiCad 10 `(net "SDA")`) and both reference syntaxes (`property "Reference"`, older `fp_text reference`). A pad with no net is "". Mounting holes and pad-less footprints are skipped, and a split pad on one net is one entry. Unreadable or non-board files, pads with no reference, duplicate references, and one pad on two nets raise `PcbNetsError`. Known limit: after parsing, a pad net written as a bare number is read as "no net", so a net literally named "3" in KiCad 10 syntax would be misread (not seen in any recorded board). Added `tests/test_pcb_nets.py` (17 tests) and the two PCB exports from the same tsci run as the recorded circuit.json (`tests/data/circuit_json/*.kicad_pcb`). The comparison itself (`verify.pcb_mismatch`) is V-13, HUMAN.
Tests: failed first (module missing), then 17 passed, including the club KiCad 10 board vs its own schematic netlist via kicad-cli (fixture read only). Three in-process sabotages (read the net number instead of the name; drop the conflict check; drop the fp_text fallback) → red each time. `pytest -q` → 7 failed, 280 passed: the same 7 known failures, none new.
Next: V-11 (pin-map importer) or V-16 (verifier adapter wiring V-10 + V-14). V-12 and V-13 stay HUMAN.

## 2026-10-20 · agent (Claude) · V-11
Did: added `reflow/parts/pinmap.py`.
- `from_st_pin_data(mpn, st_dir)` reads ST STM32_open_pin_data `mcu/<RefName>.xml`. RefName patterns like `STM32F103C(8-B)Tx` match STM32F103C8T6 / CBT6, with an optional TR suffix.
- `from_kicad_symbol(lib_id, symbols_dir)` reads a KiCad symbol. It follows `extends`, collects every unit, folds identical copies, and raises on one pin number with two names.
- `compare_pin_maps` compares by `base_name`; `import_pin_map` returns the vendor map when there is one, checked against KiCad, with disagreements as text.
- Kinds use `contracts.CardPin`/`Citation`/`PIN_KINDS`. Power vs ground is decided by name (GND*, VSS*, AGND/DGND/PGND), and every kind taken from a name instead of the source's type is recorded in `notes`. Directories come from the arguments, else `REFLOW_ST_PIN_DATA` / `REFLOW_KICAD_SYMBOL_DIR`, else the library next to kicad-cli.
- Test data in `tests/data/pinmaps/`: ST `STM32F103C(8-B)Tx.xml` unmodified (BSD-3-Clause; LICENSE copied, commit 7d1f1514ed55), and four unmodified KiCad 10.0.5 symbols (CC-BY-SA-4.0 WITH KiCad-libraries-exception; notice in `kicad/LICENSE.md`). No new Python dependency (stdlib xml).
Found:
- KiCad's MCP9808_MSOP names and numbers match DS20005095B Table 3-1, but it types Alert as `output` (the datasheet says open-drain), and its Datasheet link is MCP9804's document 22203b. Both are reported as written.
- KiCad types STM32F103C8 VSS pins 35/47 `passive`. They're read as ground by name and noted.
- ST and KiCad agree on the STM32F103C8 once ST's alternate-function suffixes ("PC14-OSC32_IN") are ignored.
Not verified: ST's DS5319 datasheet could not be downloaded (st.com and mirrors blocked), so the STM32 expected pins come from ST's pin data, cross-checked against EasyEDA C8734 and KiCad (all three agree), not from the datasheet itself. The human should confirm against DS5319 Table 5.
Tests: `tests/test_pinmap.py` failed first (module missing), then 29 passed, including the installed KiCad 10 library found next to kicad-cli. Four in-process sabotages (no ground-by-name, compare returns nothing, only the first RefName alternative, ignore `extends`) → red each time. `pytest -q` → 7 failed, 309 passed: the same 7 known failures, none new.
Next: V-12 (bind ICs to pin maps, HUMAN) can use `import_pin_map` + `base_name`. PinMap/PinImport live in pinmap.py; promote them to contracts.py if V-12 needs them across a stage boundary (DECISIONS proposal). AGENT next: V-16 or V-21.

## 2026-10-20 · human decision · V-11
Did: the human decided reflow doesn't need a direct datasheet check for test pin maps. People read datasheets outside reflow (e.g. in a separate chat), and three agreeing sources are enough for test inputs. Dropped the "human to confirm" caveat from V-11 in TASKS.md.
Tests: none (docs only).
Next: unchanged.

## 2026-10-20 · agent (Claude) · V-16
Did: added `reflow/verifier.py`. `verify_circuit_json(circuit_json, parts, spec, *, bind) -> VerifyReport` does load_circuit_json (V-10), then `bind`, then run_all, sorted like `reflow check`. `make_verifier(*, bind)` gives `run_design` its verifier callable.
- `bind` is required (keyword, no default): it's where V-12 (HUMAN) will relabel and type IC pins from pin maps. Until then callers pass an explicit pass-through, so decoupling rules can't fire, and that's visible at the call site.
- A `.kicad_sch` path raises `VerifierInputError` naming `docs/proposals/V-1-loop-HUMAN.patch`. MergedNetsError propagates.
- The `.kicad_pcb` comparison isn't wired: the rule is V-13 (HUMAN).
- `tests/test_verifier.py` (10 tests). `tests/test_integration.py` now verifies through the design verifier (`unbound` pass-through). The old .kicad_sch helper is renamed `verify_kicad_sch` and used only by the schematic-export test and by `_either_file` in the blinky compile-recovery test, so that test stays green before and after the loop patch.
Tests: test_verifier failed first (module missing). One expectation of mine was wrong (I assumed alphabetical order; reflow check orders by severity, rule id, then rule output), fixed before commit. Three in-process sabotages (skip bind, accept .kicad_sch, reverse order) → red each time. `pytest -q` → 5 failed, 321 passed. Now green: test_good_sensor_verifies_clean, test_sensor_without_pullups_is_flagged. Still red, known: test_schematic_export_keeps_the_traced_nets (upstream tscircuit, kept as a record), test_loop_fixes_missing_pullups_on_attempt_2 (needs the loop patch), the two resolver tests (C2), and the live jlcsearch test. In a throwaway worktree with `V-1-loop-HUMAN.patch` applied, the pull-up loop test passes, and test_integration + test_harness + test_design_cli give 41 passed, 1 failed (the schematic-export record).
Waiting on the human: apply `V-1-loop-HUMAN.patch` (one line in loop.py); V-12 bind; V-13 pcb comparison and how shorts surface.
Next AGENT: CLI wiring (config → model, compile_board, catalog + resolver, make_verifier) and the catalog-query half of C2.

## 2026-10-21 · human · V-1 loop change
Did: the human changed `reflow/harness/loop.py:276` to pass `compile_result.circuit_json` to the verifier (`docs/proposals/V-1-loop-HUMAN.patch`). The agent committed it at the human's request.
Tests: `pytest -q` → 4 failed, 322 passed. test_loop_fixes_missing_pullups_on_attempt_2 is now green. Remaining, all known: the schematic-export record (upstream tscircuit), the two resolver tests (C2), the live jlcsearch test.
Next: V-12 bind (HUMAN), V-13 (HUMAN); AGENT: CLI wiring, C2 catalog query.

## 2026-10-21 · agent (Claude) · H-09 (CLI wiring)
Did: wired `reflow design` in `reflow/cli.py`. With nothing injected and a `--plan` (or `--parts`), it builds every piece itself:
- `load_config()` for the caps and model settings, then `load_model(config)`;
- `compile_board` as the compiler;
- parts from `--parts`, else one `catalog_search` per plan part and then `resolve(plan.parts, spec.named_parts, candidates)`;
- `make_verifier(bind=…)`, running `run_design` with the config's caps.
Config, model, catalog, tsci and circuit.json errors exit 2 with their message. With only `--spec` it still accepts the spec and says why the loop didn't start: parts need a plan, and the H-03 loop plans only after it checks parts. That's the H1 order issue in loop.py, HUMAN. `PIN_BINDING = None` is the hook for V-12. Until it's set, every real run prints a stderr warning that pins are untyped and the decoupling rules didn't run. `main(...)` keyword seams for tests are unchanged. Added task H-09 to TASKS.md.
Tests: `tests/test_design_wiring.py` (8) failed first (no hooks on reflow.cli), then passed. Two of my test assumptions were wrong and fixed before commit: the example resolved_parts.json deliberately has an unresolved header. The end-to-end test runs a scripted model through real tsci and the real verifier: attempt 1 (no pull-ups) fails, attempt 2 passes, verify.json says `circuit.json`. Four in-process sabotages (ignore config caps, silence the warning, query the catalog before config, verify the .kicad_sch) → red each time. `pytest -q` → 4 failed, 330 passed: the same 4 known failures (schematic-export record, 2 resolver C2 tests, live jlcsearch). No HUMAN-owned file changed.
Not done: no run against a real model yet (needs REFLOW_API_KEY and base_url in reflow.toml or REFLOW_BASE_URL). Planning from the request alone waits on the loop order (H1) and H-06.
Next AGENT: the catalog-query half of C2.

## 2026-10-21 · agent (Claude) · D-6a proposal (parts data source)
Did: the human chose the jlcparts snapshot over jlcsearch. Downloaded it to the scratchpad only (5 parts, 216 MB). macOS `unzip`/`zip -s 0` fail on the split archive, so it was joined by concatenation and inflated in Python, CRC 0x2215c35f verified → `cache.sqlite3` 1.54 GB, `source-db-v2`, 2,700,372 parts.
Checked: C25900 4.7k 0402 has 16,063,321 in stock and is basic (jlcsearch says out of stock); 100nF 0402 basic caps; three orderable MCP9808 variants (C129490, C94847, C194710); 1x4 2.54 mm headers via the Pitch/Rows/Pins attributes; about 0.25 s per full-scan query; per-row `fetched_at` 2026-09-14..2026-10-21. jlcparts is MIT, pushed today; no separate data licence is stated.
Wrote `docs/proposals/D-6a-jlcparts-snapshot.md` and a D-6a row under Proposed in DECISIONS.md, with sub-questions (connector encoding, family → orderable MPN, disk, data terms) and tasks P-04, P-05, P-02b (HUMAN), P-06. No code changed; nothing in the repo references the downloaded file.
Tests: none run (docs only).
Next: the human accepts or edits D-6a; then AGENT P-04 and P-05 (failing test first), HUMAN P-02b.

## 2026-10-21 · agent (Claude) · D-6a accepted (1bb71cb), P-04
Did: committed D-6a as accepted with sub-answers a–d and added P-04, P-05, P-02b (HUMAN) and P-06 to TASKS.md. Then P-04: `reflow/parts/snapshot.py` and `reflow parts update [--db PATH] [--url URL]`.
- Downloads `cache.zip`, reads its end record for the part count (the central directory is on the last disk), downloads `cache.z01..zNN`.
- Inflates `cache.sqlite3` straight across the parts and checks CRC-32 + size, then opens it read-only and checks `meta.format == source-db-v2`.
- `os.replace`s it into place and writes `snapshot.json` (source, parts, CRC, size, row count, oldest/newest per-row `fetched_at`). On any failure the old database is kept and temp files are removed; zip64 is refused.
- Paths: `--db` / REFLOW_PARTS_DB / ~/.cache/reflow/jlcparts/cache.sqlite3. Source: `--url` / REFLOW_PARTS_URL / jlcparts GitHub Pages. Timeout: REFLOW_PARTS_TIMEOUT.
- Fixture `tests/data/snapshot/`: a jlcparts-format database (real schema, 6 real rows: C25900, C1525, C129490, C94847, C194710, C492412, plus random padding) split with `zip -s 64k` into six parts; README there.
Tests: `tests/test_parts_snapshot.py` failed first (module missing), then 15 passed. I added the stored-data CRC test because a flipped deflate byte might fail inflation before the CRC check ran. Four in-process sabotages (skip the CRC check, fetch only cache.zip, skip the format check, write in place) → red each time. Real run: installed the real 2026-10-21 snapshot from the scratchpad over file:// in 1.5 s. 2,700,372 parts, rows 2026-09-14..2026-10-21, CRC 2215c35f; SHA-256 identical to the earlier manual extraction, and SQLite quick_check ok. `pytest -q` → 4 failed, 345 passed: the same 4 known failures. No HUMAN-owned file changed.
Not done: the real download from GitHub Pages ran during D-6a research (curl), not through this command. The command path was exercised over file://.
Next: P-05 (catalog client on the snapshot, C2 catalog half), using the fixture's six rows. Then P-02b (HUMAN).

## 2026-10-21 · agent (Claude) · P-05
Did: added `reflow/parts/local_catalog.py`: `search(request: PartRequest, *, db_path=None) -> list[CatalogPart]` on the read-only snapshot, plus `reflow_category(jlc_category, jlc_subcategory)`.
- Queries: named `mpn` → MPN prefix (case-insensitive, LIKE wildcards escaped), any category, optional package. Resistors → fixed-resistor subcategories, value compared as a number, tolerance at least as tight. Capacitors → value, minimum voltage, tolerance. Connectors → pin headers only, `value` "RxC" + `package` pitch (D-6a a), right-angle (弯) excluded. Every other category without an MPN raises CatalogError. Only in-stock rows, ordered by LCSC id, not ranked.
- `CatalogPart` gains `category` and `fetched_at` (defaults "", so the jlcsearch client is unchanged); `catalog.parse_value` made public.
- `reflow design` now resolves through the local catalog (`catalog_search(part)`), and the fakes in `tests/test_design_wiring.py` take the request. The jlcsearch client is no longer used by the CLI but stays until P-06.
- Fixture `tests/data/parts_db/cache.sqlite3`: 27 real rows (README lists each and why).
Found / for the human:
- The resolver (HUMAN, P-02b) leaves the header unresolved: it compares `package` "2.54mm" to the row's package text ("插件,P=2.54mm"). Under D-6a (a) a connector's package is the pitch. I didn't fake the row's package (that would lose through-hole vs SMD); P-02b in TASKS.md now says so. The IC still waits on family → orderable matching.
- `reflow_category` is a hand-made table over JLC's 105 categories; please review it. 472,439 snapshot rows have no category and map to "other", including at least one 13M-stock 0402 resistor. Passive queries skip them; a category check in P-02b would reject them.
- Planner prompt (H-08) still says a connector's value is empty; it needs D-6a (a)'s "1x4" / "2.54mm" before a model-made plan can resolve a header.
Tests: `tests/test_local_catalog.py` failed first (module missing). One expectation of mine was wrong (that the resolver would accept the header today) and was moved to assert the catalog side only. Then 32 passed. Five in-process sabotages (ignore value, keep right-angle headers, category from the request, unescaped MPN, keep no-stock rows) → red each time. Real snapshot: the MCP9808 plan's five requests return 3 / 144 / 38 / 38 / 58 candidates in about 0.3 s each, all of the right kind; the resolver picks C307331 and C25900. `pytest -q` → 4 failed, 377 passed: the same 4 known failures (the two jlcsearch C2 tests stay red until P-06 replaces them).
Next: P-02b (HUMAN); the planner prompt line for headers (H-08, AGENT→HUMAN); P-06 (needs the human's OK to remove the jlcsearch tests).

## 2026-10-21 · agent (Claude) · H-08 (planner draft: header encoding)
Did: updated the planner draft `prompts/planner.md` for D-6a (a). The `value` field says a connector is "rows x pins per row, such as 1x4", and the `package` field says a connector's is "the pin pitch, such as 2.54mm". A new paragraph says a connector is a straight pin header, and that a missing pitch defaults to 2.54mm plus an open question. The example plan's p5 header is now value "1x4", package "2.54mm". The draft banner is unchanged: still a draft, awaiting your review. H-08 set to doing (awaiting human review). Note: codegen.md says "a passive footprint is the package cell"; for a header the resolved package is the row's text (e.g. "插件,P=2.54mm"), so codegen should take the pin count from the value. Worth a look when you review codegen.md.
Tests: two new tests in `tests/test_prompts.py` failed first. The field lines didn't describe headers, and the example header was ("", ""). One also parses the prompt's example Spec and Plan strictly and checks the local catalog finds a header for each example connector on the 27-row fixture. Both pass now; test_prompts 10 passed. `pytest -q` → 4 failed, 379 passed: the same 4 known failures.
Next: the human reviews planner.md (and approves H-08 when ready); P-02b (HUMAN).

## 2026-10-21 · human review · H-08 (planner.md)
Did: the human reviewed the planner.md header-encoding change (e95dd05) and approved its content. H-08 stays "doing (awaiting human review)" for codegen.md and fix.md. The draft banners stay until the human approves all three.
Tests: none (log only).
Next: codegen.md / fix.md review (H-08); P-02b (HUMAN).

## 2026-10-21 · agent (Claude) · O-1, P-02b (awaiting human review)
Did: the human chose (in chat) to have the agent implement P-02b and draft E-02, with the human reviewing. Recorded as O-1 in DECISIONS.md (these two tasks only; golden rule 1 otherwise unchanged); TASKS.md owners updated. Changed `reflow/parts/resolver.py` (`_resolve_one`, new `_named_matches`, `_is_ordering_code`):
- A candidate with a stated `category` that differs from the request's is never chosen. "" (jlcsearch) isn't filtered.
- A typed family: an exact case-insensitive match wins. Otherwise a prefix match counts only when the rest is an ordering code: nothing, a non-alphanumeric character, or T/R then a non-alphanumeric character. Any other continuation (PCF8574 → PCF8574AT) makes the request Unresolved, listing the variants.
- A named part left in more than one package is Unresolved and asks which package.
- A connector's `package` (the pitch) isn't compared to the row's package text.
- `fetched_at` is the row's own date when set.
Also tightened `tests/test_local_catalog.py`'s plan test to require every part resolved (IC with package MSOP-8).
For the human reviewer:
- The ordering-code rule is a heuristic: it accepts a trailing T/R as packing (Microchip "T-" tape and reel). It will ask more often than strictly needed (AT24C02C vs AT24C02D, TMP102A…) rather than guess.
- AMS1117-3.3 asks for a package, because the snapshot spells SOT-223 as "SOT-223", "SOT-223-3" and "SOT-223-4".
- The planner prompt leaves an IC's package empty, so a model-made plan for MCP9808 will hit the package question until the planner asks the user for it.
Tests: 12 new tests in `tests/test_resolver.py`. 9 failed first (3 already passed: exact match, never matching a shorter MPN, "" category not filtered); the local plan test failed first. One bug in my own test helper (category passed twice) fixed. Then test_resolver + test_local_catalog 64 passed, and every pre-existing P-02 test still passes. Five in-process sabotages (no category check, no variant check, exact-only, ignore row date, literal connector package) → red each time. Real snapshot: MCP9808 asks MSOP-8 or DFN; with MSOP-8 → C129490 MCP9808T-E/MS (row date 2026-10-16); AT24C02 → C688857; KT-0603R → C2286; PCF8574 / PCF8574T / TMP102 ask which variant. `pytest -q` → 4 failed, 391 passed: the same 4 known failures. The jlcsearch C2 test still picks the LED, because jlcsearch gives no category; P-06 replaces it.
Next: the human reviews the resolver.py diff; then E-02 drafts.

## 2026-10-21 · agent (Claude) · E-02 drafts (awaiting human check)
Did: under O-1, drafted five eval boards in `evals/` (README explains the format), each with request.txt, a confirmed spec.json, a hand-written plan.json and expected.toml (`status = "draft"`, `checked_by = ""`):
- mcp9808_breakout: MCP9808, MSOP-8;
- at24c02_eeprom: AT24C02, SOP-8;
- ams1117_regulator: AMS1117-3.3, SOT-223;
- pcf8574_expander: the exact PCF8574T/3,518, because the family "PCF8574" also matches PCF8574A;
- led_indicator: KT-0603R + 1k.
Plans use only what the local catalog supports (resistors, capacitors, D-6a headers, named parts with a package). Only the MCP9808 expectations cite pages that were read (DS20005095B). Every line marked `TO CHECK` (AT24C02, AMS1117, PCF8574, KT-0603R pin names, strap levels and capacitor needs) is unverified. In particular the AMS1117 output-capacitor requirement and the LED cathode pad must be checked against their datasheets. Added `tests/test_evals.py`, a structural checker for every eval folder.
Tests: `tests/test_evals.py` 16 passed. Planting two mistakes (a header with an empty value; a named part not in the request) turned it red, and restoring them turned it green. On the real snapshot, every part of all five plans resolves, 24/24: C129490, C688857, C6186, C7605, C2286, plus basic passives. `pytest -q` → 4 failed, 407 passed: the same 4 known failures.
Next: the human checks each expected.toml against the datasheets and sets status "checked". Then E-01 (eval runner, AGENT).

## 2026-10-21 · agent (Claude) · E-01
Did: added `reflow/evals.py` (`run_evals`) and `reflow eval [--evals DIR] [--out DIR] [--runs DIR] [--only NAME]`. For each eval folder it resolves the plan from the local snapshot, runs `run_design` with the design verifier, and measures the best attempt's board:
- status, attempts, first pass, rule ids per attempt;
- foreign part numbers: every manufacturer or supplier part number in circuit.json that came from neither ResolvedParts nor Spec.named_parts. This measures the go/no-go's "zero part numbers outside the resolver"; it isn't the R-03 rule;
- expectation misses against expected.toml, read on the board's netlist. Kinds map to codegen's ref prefixes; LED anode/cathode are tscircuit's pin 1/2; IC pin names are the design's own labels until V-12;
- tokens.
Clean = passed + no foreign + no misses. Go/no-go is "undecided" while any eval is a draft or there are fewer than 5; otherwise go needs ≥3 clean and zero foreign part numbers. An unresolved part aborts that board before any model call; model, catalog and compile errors are recorded per board and the run continues. Results go to `evals/results/<stamp>.json` with the model id(s), pin binding ("none (V-12 not built)"), parts database and snapshot.json, git commit plus an uncommitted-changes flag, and tsci version. Providers aren't seeded, so a rerun can differ; that's recorded in TASKS.md.
Tests: `tests/test_eval_runner.py` (12) failed first (module missing), then passed (about 2 minutes: real tsci compiles). Four in-process sabotages (no foreign scan, no expectation check, ignore drafts, first pass = passed) → red each time. My first sabotage run used -k filters that matched no tests; rerun with correct filters, all red. `pytest -q` → 4 failed, 419 passed: the same 4 known failures. The suite now takes about 3 minutes.
Not done: no run against a real model; the five evals are still drafts, so any real result is "undecided".
Next: the human reviews P-02b and checks the eval drafts. Then a real `reflow eval` with REFLOW_API_KEY. AGENT next: P-06 (needs the human's OK to remove the jlcsearch tests), or V-21 (rules.toml).

## 2026-10-21 · agent (Claude) · P-06
Did: the human approved removing the jlcsearch client and its tests.
- Removed the HTTP client from `reflow/parts/catalog.py` (search, transport, endpoints, cache dir, REFLOW_CATALOG_* env). Kept `CatalogPart`, `CatalogError` and `parse_value`, which the resolver, local catalog, CLI and evals import.
- Deleted `reflow/parts/cache.py`, `tests/test_parts_integration.py` and `tests/data/jlcsearch_plan/`.
- Replaced `tests/test_catalog.py` (the old jlcsearch client tests, live test included) with tests for what remains: parse_value, CatalogPart defaults, and that the client and cache are gone.
- In `tests/test_resolver.py`, `test_resolver_does_not_call_catalog_search` monkeypatched `reflow.parts.catalog.search`, which no longer exists. It now patches `reflow.parts.local_catalog.search`, the catalog that fetches today. Checked: a resolver that calls it turns the test red.
- Docs: A8 in docs/00, the parts README, the tests README, and the `ResolvedPart.source` comment in contracts.py (comment only; no field changed).
- TASKS: P-01 retired, P-03 done via the snapshot, P-06 done.
Left alone: `reflow/parts/resolver.py` docstrings still say '"" means the source did not say (the jlcsearch client)'. The file is under the human's P-02b review, so the wording is the human's to update.
Tests: new `tests/test_catalog.py` failed first on the two "gone" checks (17 tests; the parse_value cases already passed). `pytest -q` → 1 failed, 425 passed. The one failure is the deliberate record of tscircuit's broken .kicad_sch export (`test_schematic_export_keeps_the_traced_nets`). The live jlcsearch test and both C2 jlcsearch tests are gone with the client. No HUMAN-owned file changed.
Next: the human reviews P-02b and checks the eval drafts; then a real `reflow eval`. AGENT options: V-21 (rules.toml parser), O-02 (report.json/md).

## 2026-10-21 · agent (Claude) · V-21
Did: added `reflow/project_rules.py` and `reflow rules check RULES [--symbol REF=Lib:Symbol] [--mpn REF=MPN]`.
- `load_rules` parses strictly to `ProjectRules`: missing why/source, unknown keys and TOML errors raise RulesFileError.
- `check_rules` reports errors: `on` not REF.PIN; need not in RULE_NEEDS; `to` missing for cap/pullup/pulldown/tie or present for open/connected; unparseable value or a reversed range; blank why/source; a pin not on its part's pin map (matched by number or base_name, citing the pin map's source).
- It reports warnings: a ref with no pin map given; any power, ground, reset or boot pin no rule mentions. Reset/boot are recognised by name (NRST/RESET/RST/MCLR/BOOT*), since neither pin source types them.
- Because a rules file exists before any board, the user says which part each ref is (`--symbol` via V-11 from_kicad_symbol, `--mpn` via import_pin_map). Exit 1 on errors, 2 on unusable input.
- Not wired into `reflow design`: the example spec's rules_file points at a file the design tests don't have, and using the rules in the loop is V-22 / R-10.
Tests: `tests/test_project_rules.py` (26) failed first (module missing), then passed. Four in-process sabotages (any pin accepted, no coverage warnings, no reset/boot names, `to` never checked) → red each time. Real run on the accepted example with the installed KiCad library → 7 rules, 0 errors, 1 warning (U1.GND has no rule). `pytest -q` → 1 failed (the deliberate tscircuit .kicad_sch record), 451 passed.
Next: V-22 (render rules into prompts, AGENT→HUMAN), or R-10 (the six need checks, HUMAN).

## 2026-10-21 · agent (Claude) · fix: test fixtures hidden by .gitignore (V-11, P-04)
Did: while testing the V-2a patch in a clean worktree, found that `.gitignore`'s `kicad/` and `*.zip` patterns had kept two fixtures out of git: `tests/data/pinmaps/kicad/` (V-11, commit 19b7c4a) and `tests/data/snapshot/cache.zip` (P-04, dd4d2e0). Their tests passed locally but would fail on a fresh clone. My clean-worktree runs covered only the contract commits, not those. Added negation lines for exactly those paths, committed the files, and added `tests/test_repo_hygiene.py`, which fails if any file under tests/data, evals, docs/examples or docs/proposals/examples is git-ignored.
Tests: the hygiene test failed first, listing the 4 hidden files, then passed. The full `pytest -q` in a fresh worktree of this commit is recorded below.

## 2026-10-21 · agent (Claude) · fixture fix verified; V-2a proposal
Did: fresh worktree of 378ae20 → `pytest -q` 452 passed, 1 failed (the deliberate tscircuit .kicad_sch record), so a clean clone now passes. For V-22 the human chose (in chat) a `[[part]]` table in rules.toml and a HUMAN patch for loop.py. Drafted V-2a (`docs/proposals/V-2a-rule-parts.md`, `docs/proposals/V-2a-contract.patch`: `RulePart{ref, mpn, symbol}`, `ProjectRules.part`, frozen lists, the example JSON and rules.toml, docs/04 §0b) and a V-2a row under Proposed in DECISIONS.md. Not applied.
Tests: the patch on 378ae20 in a scratch worktree → test_contracts, test_project_rules, test_prompts, test_evals, test_repo_hygiene: 108 passed. An unknown key in a [[part]] → contract tests red.
Next: the human accepts V-2a. Then the agent applies it in one commit and does V-22 (render_rules, codegen.md section, V-22-loop-HUMAN.patch).

## 2026-10-21 · agent (Claude) · V-2a accepted (bbf16ab), V-22 (awaiting human review)
Did: the human accepted V-2a; applied its contract patch in bbf16ab (RulePart, ProjectRules.part; the patch file removed). Then V-22:
- `reflow/project_rules.py`: `render_rules(rules, plan)` gives one line per [[part]] ("U1 is the MCP9808 (plan part p1). Give it reference U1.") and per rule ("U1.VDD: capacitor to GND, 100nF..1uF"), never why or source. `rules_prompt_block(spec, plan)` returns "none" for an empty rules_file and raises for a missing or invalid one. `pin_maps_from_parts(rules)` builds pin maps from [[part]] (symbol, else vendor data via mpn, else a warning). check_rules warns about rule refs missing from [[part]].
- `reflow design` resolves Spec.rules_file next to the spec file. It refuses a missing or invalid file, or a [[part]] whose mpn isn't in Spec.named_parts (exit 2), and passes the spec on with an absolute rules_file. `reflow rules check` now takes pin maps from [[part]]; the flags still override.
- `prompts/codegen.md` (draft) gains "## Project rules: fixed references and pin requirements" with {project_rules}; the existing references sentence now excepts references the project rules fix. Wording avoids "why" and "datasheet", which the prompt tests forbid. tests/test_prompts.py's allowed codegen placeholders gain "project_rules".
- `docs/examples/spec.json` rules_file "rules.toml" → "". The example pointed at a file that doesn't exist next to it, and once the loop reads rules files, every test built from the example would fail on it. Non-empty rules_file is covered by test_rules_prompt.py.
- `docs/proposals/V-22-loop-HUMAN.patch` for the human: one import, plus `"project_rules": rules_prompt_block(spec, plan)` in `_codegen_text`. Fix prompts are the codegen prompt plus fix.md, so they carry the rules too.
Tests: `tests/test_rules_prompt.py` (15) failed first (render_rules missing). Two mistakes of mine fixed before commit: a test helper not creating its folder, and the word "datasheet" in the prompt. Three in-process sabotages (leak why/source, skip the [[part]] mpn check, skip rules-file resolution) → red each time. `pytest -q` → 2 failed, 467 passed. The failures: the deliberate tscircuit record, and `test_codegen_prompt_carries_the_rules`, which is red until the loop patch is applied. The patch-applied run in a scratch worktree is recorded below.
- 2026-10-21 · V-22 check: fresh worktree of 4ad7c07 with `docs/proposals/V-22-loop-HUMAN.patch` applied → `pytest -q` 468 passed, 1 failed (only the deliberate tscircuit .kicad_sch record); test_codegen_prompt_carries_the_rules goes green.

## 2026-10-21 · human · V-22 loop change (30cc4b4)
Did: the human applied `docs/proposals/V-22-loop-HUMAN.patch` to `reflow/harness/loop.py` (the import of `rules_prompt_block`, and `"project_rules": rules_prompt_block(spec, plan)` in `_codegen_text`) and committed it as 30cc4b4. The human also reviewed the codegen.md Project rules section.
Tests: `tests/test_rules_prompt.py` → 15 passed. `pytest -q` → 468 passed, 1 failed. The failure is the deliberate record `test_schematic_export_keeps_the_traced_nets` (tscircuit's .kicad_sch exports R1.pin1 as unconnected instead of on SDA; the verifier reads circuit.json since V-1).
Next: the human decides whether to retire that record test (removing a test needs the human's OK). V-22 can be marked done.
- 2026-10-21 · agent re-run on a68b49c (this checkout, loop change 30cc4b4 in place): `pytest -q` → 468 passed, 1 failed (`test_schematic_export_keeps_the_traced_nets`, the deliberate tscircuit record). It matches the entry above. KiCad 10 via KICAD_CLI, tsci 0.0.2768.

## 2026-10-21 · agent (Claude) · M-03 (reply budget)
Did: for reasoning models (the human's free OpenRouter model has reasoning on by default), reflow's fixed 4096-token reply budget could be spent before any TSX was written.
- `reflow.toml` / REFLOW_MAX_TOKENS gain `max_tokens` (int ≥ 1, default 4096).
- `load_model` takes it as every call's default budget; a call can still pass its own.
- A reply the provider cut off (Anthropic stop_reason "max_tokens", OpenAI finish_reason "length") now raises ModelError "reply was cut off at max_tokens=N; raise the max_tokens setting". Before, it surfaced as a confusing "no code fence" compile try, or "no text" when a reasoning model used the whole budget. The design CLI exits 2 with that message; the eval runner records it on the board.
- tests/test_config.py's key list and clean-env variables gain max_tokens (additions only).
Tests: 12 new checks failed first. One bad-value check passed early only because the key used to be unknown; it now passes because the value is bad. My first error message named reflow.toml, which an existing test forbids in llm.py (the adapter never reads config); reworded. Three in-process sabotages (ignore the config budget, no cut-off check, Anthropic-only check) → red each time. `pytest -q` → 484 passed, 1 failed (the deliberate tscircuit record).
Next: the human sets max_tokens (e.g. 12000) for the reasoning model and runs the smoke eval.

## 2026-10-21 · first real run · fix: the eval runner forced max_tokens=4096
Did: the human ran the real path for the first time (OpenRouter, nvidia/nemotron-3.5-super-vl:free, max_tokens = 12000). `reflow parts update` downloaded and installed the real snapshot over the network: 2,723,372 parts, rows 2026-09-14 to 2026-10-21. `reflow eval --only mcp9808_breakout` ended the board with "ModelError: reply was cut off at max_tokens=4096" despite the config. Cause: my eval runner's model wrapper (`reflow/evals.py` `_Counting.complete`) defaulted max_tokens to 4096 and passed it on every call, overriding the config budget. Its default is now None, which leaves the budget to the model. The design CLI path wasn't affected (the loop never passes a budget).
Tests: new `tests/test_eval_budget.py` failed first ([4096, 2000] instead of [None, 2000]), then passed. `pytest -q` → see the commit message.
Next: the human reruns `reflow eval --only mcp9808_breakout`.
- Same session: the real run also exposed (a) `tests/test_evals.py` treating `evals/results/` (written by `reflow eval`) as a board; it now only takes folders with a spec.json, as the runner already did. And (b) my earlier advice to put provider/model/base_url/max_tokens in `reflow.toml` conflicts with `tests/test_config.py::test_committed_reflow_toml_is_caps_only`, which keeps personal model settings out of the committed file. The human's local reflow.toml edits aren't committed; those settings belong in REFLOW_PROVIDER / REFLOW_MODEL / REFLOW_BASE_URL / REFLOW_MAX_TOKENS / REFLOW_TIMEOUT_S. With the local reflow.toml edits in place, `pytest -q` → 483 passed, 6 failed: the deliberate record, the 2 caps-only config tests (local edits), and the 3 checker cases fixed here. Without the local edits, only the deliberate record fails.

## 2026-10-21 · agent (Claude) · local settings in .env
Did: at the human's request, moved model settings out of `reflow.toml` (restored to caps only, so the caps-only config tests pass again) into a local `.env`. `.env` is now in `.gitignore`, and it's chmod 600 with `REFLOW_API_KEY=` left blank for the human to fill in. Committed `.env.example` (same layout, no secret). reflow still reads only the environment, never .env, so the human loads it with `set -a; source .env; set +a`. The agent never saw or wrote the key.
Tests: config loads every setting from .env (dummy key for the check); with the blank key it raises "REFLOW_API_KEY is not set". test_config + test_repo_hygiene → 31 passed.

## 2026-10-22 · first real board (OpenRouter, nvidia/nemotron-3.5-super-vl:free) · M-01 error detail
Did:
- The human's first rerun failed with "ModelError: Provider returned error". OpenRouter wraps upstream failures that way and puts the cause in error.metadata (provider_name, raw), which the adapter dropped. `reflow/llm.py` now keeps the HTTP status (or the code inside a 200 error reply), the provider name and up to 500 characters of the raw upstream error. An error object inside a 200 reply now raises with those details, instead of "no text". Tests: 2 new in tests/test_llm.py failed first, then 26 passed.
- A tiny direct request with the human's .env worked at both budgets (reasoning tokens 27–56 to say "Hi"), so key and model were fine. Rerunning `reflow eval --only mcp9808_breakout` then worked: passed on attempt 1, 1626 in / 8657 out tokens, about 7 minutes, 0 part numbers outside the resolver. Marked not clean (expectation: no ic.ALERT pin). The earlier provider error didn't recur, so it was likely transient upstream.
- **Finding, the V-1 failure mode in a real run:** the model's MCP9808 pinLabels were wrong. pin3 "NC" (datasheet: Alert), pin7 "VDD" (A0), pin8 "A0" (VDD). Following its own labels it wired 3.3V to pin 7 and the real VDD (pin 8) to GND. The verifier passed the board (0 errors), because without V-12 the rules read the model's labels. It also used footprint "soic8" for an MSOP-8 part, which nothing checks. Comparing the board with the V-11 KiCad pin map by pin number (V-10 loader) flags all three pins, so V-12 binding plus a V-13 pinout.mismatch rule (HUMAN) would turn this into a verify error that goes back to the model as a fix hint. Run folder: `runs/evals/20261022T173550Z/mcp9808_breakout`; results in evals/results/ (uncommitted).
Tests: `pytest -q` → see below.
Next (HUMAN, highest value for the go/no-go): V-12 bind, V-13 pinout.mismatch; consider a footprint-vs-package check.
- 2026-10-22 suite: `pytest -q` → 486 passed, 2 failed. The failures: the deliberate tscircuit record, and test_committed_reflow_toml_is_caps_only, because the local reflow.toml was emptied (uncommitted; defaults are the same caps, so behaviour is unchanged). Restoring the two cap lines makes it pass.

## 2026-10-22 · agent (Claude) · V-12 pin binding (O-1b, awaiting human review)
Did: the human extended O-1 to V-12 (O-1b in DECISIONS.md; TASKS owner AGENT→HUMAN).
- New `reflow/pinbind.py`: `PinBinder(pin_map_for)` identifies each U-prefixed IC by a part number it carries in circuit.json that is a ResolvedParts row (LCSC id first, else MPN), else `pinout.unidentified`. It gets the pin map from `pin_map_for(ref, row)`; none (or PinMapError) gives `pinout.no_pin_map`. Then it relabels every pin by physical number from the map and types it (power/ground → power_in, …). A label that is neither the map's name (base_name) nor generic "pinN", or a pin number the package lacks, gives `pinout.mismatch`. All errors carry a fix_hint naming the pin and the right label. `binder_for_spec(spec)` takes pin maps from the rules file's [[part]] symbol (by ref, else MPN prefix), then vendor pin data.
- `circuit_netlist.part_numbers(path)` reads what each component carries.
- `verifier.py`: bind now gets `(netlist, parts, spec, part_numbers)` and may return a BindResult; its violations join the rules'.
- `reflow design` and `reflow eval` use `binder_for_spec` (PIN_BINDING still overrides); the "V-12 not built" warning is gone. The eval runner resolves each board's rules_file next to its spec.
- Fixtures `tests/data/real_runs/mcp9808_nemotron_20261022/`: the real board (model TSX, circuit.json source_*, parts.json), plus corrected and corrected-without-C1 variants compiled with tsci 0.0.2768.
- This overlaps V-13 (the pinout rule ids). The human asked for mismatches to be reported; `verify.pcb_mismatch` and how shorts surface stay HUMAN.
Tests: `tests/test_pinbind.py` (15) failed first (module missing), then passed. On the real board: pins 3, 7, 8 → 3 pinout.mismatch, and the verifier now fails it. The corrected board is clean; corrected without C1 → decoupling.missing (the rule runs now that pins are typed). Updated tests: 4-arg binder signatures in test_verifier/test_integration; the binding label in test_eval_runner; and the design-wiring end-to-end tests plus the eval CLI test, which bind for real now and use the real local catalog on the parts fixture, a rules file with the MCP9808 symbol, and the corrected real board. New end-to-end: the model's wrong-pinout board fails attempt 1 with 3 pinout.mismatch, the fix prompt carries pin8: "VDD", and attempt 2 passes. Four in-process sabotages (keep design labels, no pin types, skip unidentified, trust any MPN) → red each time.
For the human reviewer:
- Only U-prefixed parts are bound.
- A [[part]] symbol is matched by ref first, then by MPN prefix.
- `pinout.no_pin_map`'s fix_hint asks for a rules.toml [[part]], which the model can't act on; consider rewording.
- The eval boards have rules_file "", so a real eval of them now fails `pinout.no_pin_map` until each gets a rules.toml with a [[part]] symbol (next: eval drafts).
- V-12 suite: `pytest -q` → 502 passed, 2 failed (the deliberate tscircuit record; test_committed_reflow_toml_is_caps_only, because the local reflow.toml was emptied and is uncommitted).

## 2026-10-22 · agent (Claude) · E-02 eval boards get rules.toml pin maps (O-1)
Did: each eval board with an IC now has a `rules.toml` whose `[[part]]` names the KiCad symbol V-12 binds U1 to. Its spec points at it (`"rules_file": "rules.toml"`).
- mcp9808_breakout: a copy of the accepted example (`docs/proposals/examples/rules.toml`): Sensor_Temperature:MCP9808_MSOP plus its 7 rules.
- at24c02_eeprom: Memory_EEPROM:AT24CS02-SSHM. The serial-number variant has the same SOIC-8 pinout; checked pin for pin against EasyEDA C688857.
- ams1117_regulator: Regulator_Linear:AMS1117-3.3. EasyEDA (C6186) names the pins VIN/VOUT and also has tab pin 4 (VOUT). KiCad's 3-pin symbol has no pin 4, so a design that wires the tab as pin4 gets `pinout.mismatch`. The human should decide whether that's right.
- pcf8574_expander: Interface_Expansion:PCF8574T.
- The three non-MCP9808 rule lists are `rule = []` on purpose: rules must be written from the datasheet with a page (V-2).
- led_indicator has no IC, so it keeps rules_file "".
- Expected drafts (agent-written under O-1, still status "draft"): renamed pins to the KiCad symbol's names, since V-12 relabels pins to them. ams1117 regulator.VIN→VI and VOUT→VO; pcf8574 ic.VSS→GND. Each file has a comment noting the EasyEDA names.
Tests:
- Two new tests in tests/test_evals.py: every board with an ic/regulator names a [[part]] for it, with a U ref, a symbol and a spec-named MPN; and each symbol loads from the installed KiCad library and has every pin expected.toml names. 4 boards failed first, then passed.
- test_eval_runner's CLI test copied the MCP9808 board and added a rules file. The board now ships one, so the test asserts that instead.
- Sabotage: removing the AT24C02 [[part]], pointing AMS1117 at the -5.0 symbol, or restoring "regulator.VIN" each turns the suite red.
- `pytest -q` → 512 passed, 2 failed: the deliberate tscircuit record, and test_committed_reflow_toml_is_caps_only (the local reflow.toml was emptied; uncommitted).
- Smoke eval `reflow eval --only mcp9808_breakout` with the human's .env, run twice. Both failed at the model before any board came back, so nothing was compiled or verified, and this run tells us nothing about V-12 binding:
  - 20261022T184351Z: "ModelError: provider response contained no text".
  - 20261022T185803Z: "Upstream idle timeout exceeded (code 504)" from OpenRouter.
  - Both are recorded in evals/results/ (uncommitted) with status error and 0 tokens.
  - Side finding: run.json labels these "failed_compile" with 0 attempts, although nothing was compiled. The status comes from harness/loop.py (HUMAN).
  - Next: rerun when the free model is responsive, or try another model through REFLOW_MODEL.

## 2026-10-22 · agent (Claude) · smoke eval on Nemotron 3.5 Lightning: a false pass
Did: at the human's request, switched the local .env (uncommitted) to `REFLOW_MODEL=nvidia/nemotron-3.5-lightning:free`. A tiny probe answered in 2.2 s.
- Run 20261022T190328Z: cut off at max_tokens=12000, so I raised `REFLOW_MAX_TOKENS` to 32000.
- Run 20261022T190601Z "passed" on attempt 1 (1750 in / 14345 out tokens, 0 foreign part numbers), but the board is empty.
**Finding (integrity, blocks trusting any pass):**
- The model wrote `supplierPartNumbers={["C…"]}` (an array; tscircuit wants `{ jlcpcb: ["C…"] }`). tscircuit could not create any of the 5 components.
- `tsci` still exited 0. circuit.json held 5 `source_failed_to_create_component_error` and 13 `source_trace_not_connected_error`, and no source_component.
- `compile_board` reported ok. The verifier saw 0 components / 0 nets, so 0 violations, and the run was marked passed.
- Only the draft expectation check noticed (every net and part missing).
- The model's pinLabels were wrong again (pin1 VDD …). V-12 would have flagged it if U1 had existed.
Proposed fix (needs the human's OK, not started):
- (a) compile_board (K-02, AGENT) turns every `*_error` element in circuit.json into a CompileError, so the loop sends it back to the model as a compile error;
- (b) the verifier refuses a circuit.json with no components;
- (c) prompts/codegen.md shows the `supplierPartNumbers={{ jlcpcb: ["C…"] }}` shape.

## 2026-10-22 · agent (Claude) · K-02: empty boards no longer pass
Did: at the human's request, closed the false pass from run 20261022T190601Z.
- **compile:** `reflow/compile.py` has `circuit_json_errors(path)`. After tsci exits 0, every `source_*_error` element in circuit.json becomes a CompileError, in file order, on one line, without tscircuit's "Details:" dump. Any of them makes the compile not ok, so the loop sends them to the model as compile errors. An unreadable circuit.json does too.
  - On the real board, the first error is `Could not create chip "U1". Invalid props for chip "U1": supplierPartNumbers (Expected object, received array)`.
  - **Departure from the request ("*_error"), for the human to confirm:** only `source_*` errors count. blinky compiles with a `pcb_port_not_connected_error` (the autorouter left D1.pin2 → GND unrouted). That's a layout result, and the model can't fix the autorouter from TSX. Nothing reports `pcb_*` / `schematic_*` errors yet; that belongs with the PCB checks (V-13, HUMAN).
- **verifier:** `verify_circuit_json` raises VerifierInputError for a circuit.json with no components. `reflow design` exits with an error, and an eval records that board as an error, never as passed.
- **prompts/codegen.md:** shows `supplierPartNumbers={{ jlcpcb: ["<lcsc cell>"] }}`, says it isn't a bare list, and says tscircuit drops a component whose value is a bare list. It uses a placeholder, never a real LCSC id (rule 5).
- **Fixture:** `tests/data/real_runs/mcp9808_lightning_20261022/`: the model's TSX, its circuit.json source_* elements, parts.json and a README.
Tests:
- New, failed first: 7 in test_compile (circuit.json errors from the real board; warnings and layout errors aren't errors; fake tsci exiting 0 with error elements → not ok; unreadable circuit.json; real tsci on the real board → not ok; the same board with codegen's shape compiles all 5 parts), 1 in test_verifier (no components → refused), 1 in test_prompts (shape shown, no real LCSC id).
- Five sabotages each turn the suite red: ignore the circuit.json errors, let the verifier pass an empty board, count layout errors, keep the Details dump, drop the shape from the prompt.
- `pytest -q` → 521 passed, 2 failed: the deliberate tscircuit record, and test_committed_reflow_toml_is_caps_only (the local reflow.toml was emptied; uncommitted).
- Local .env (uncommitted) now has REFLOW_MODEL=nvidia/nemotron-3.5-lightning:free and REFLOW_MAX_TOKENS=32000.

## 2026-10-22 · smoke eval on Lightning after K-02 (run 20261022T192231Z)
`reflow eval --only mcp9808_breakout`, nvidia/nemotron-3.5-lightning:free, max_tokens 32000. Took 2 attempts: 5625 in / 34740 out tokens, 0 part numbers outside the resolver. supplierPartNumbers had the object shape both times, and both attempts compiled.
- **Attempt 1:** 5 parts, 7 nets, 10 errors.
  - 7 pinout.mismatch: the pinout was mirrored, pin1 A2 … pin7 VDD, pin8 ALERT.
  - 2 decoupling.missing, on the real GND pin 4 and on pin 8 (VDD), which the design left unconnected.
  - 1 i2c.missing_pullup: the model's "SCL" landed on GND.
- **Attempt 2:** the pinout is right on every pin and the verifier finds 0 errors, but the board doesn't work.
  - U1.VDD, C1.pin1 and J1.pin1 sit on an unnamed net, `Net-(C1-pin1)`.
  - The pull-ups R1/R2 go to `V3_3`, which connects to nothing else, so they pull SDA/SCL up to a rail nothing powers.
  - Only the draft expectation check caught it ("net V3_3 should include ic.VDD / capacitor / connector"). The run is marked passed, not clean.
**Gap, HUMAN-owned (reflow/rules/, R-10):** no rule checks that a pull-up's rail is the chip's supply, or that a named power rail reaches any supply pin or connector. The MCP9808 rules.toml wouldn't catch it either: "U1.SDA pullup to V3_3" holds, and "U1.VDD cap to GND" holds. Candidates:
- (a) i2c.missing_pullup requires the pull-up rail to be the IC's VDD net;
- (b) a rule for a named rail that has only passive pins on it;
- (c) a project need stating which net U1.VDD must be on.
Until one exists, a verifier pass doesn't mean the board is wired right; the checked expectations (E-02) are the only backstop.
Minor: pinout.mismatch messages say "KiCad symbol library Sensor_Temperature Sensor_Temperature:MCP9808_MSOP" (doc and locator both carry the library name).

## 2026-10-22 · agent (Claude) · failing test for the unpowered pull-up rail (rule is HUMAN)
Did: at the human's request, saved attempt 2 of run 20261022T192231Z as `tests/data/real_runs/mcp9808_lightning_pullup_rail_20261022/`: the model's TSX, its circuit.json source_* elements, parts.json and a README with the net table. Added `tests/test_i2c_pullup_rail.py`. Nothing in reflow/rules/ was touched.
- `test_pullups_to_an_unpowered_rail_fail_verify` (red, on purpose):
  - the board binds with 0 pinout.* errors;
  - verify must give an `i2c.*` error on SDA and one on SCL;
  - each error's fix_hint must name `V3_3` and the chip's supply net `Net-(C1-pin1)`, so the model can act on it;
  - the rule id is the human's to choose.
- `test_pullups_to_the_chips_supply_stay_clean` (green): the corrected first real board, where R1/R2 and U1.VDD share V3_3, keeps 0 i2c errors and 0 errors.
For the human writing the rule:
- The supply is only known once V-12 has bound the IC (power pins become `power_in`). Several tests verify with `unbound` (tests/test_integration.py, tests/test_verifier.py), where no pin is typed. If the rule fires whenever no supply is found, those tests go red; it should probably skip, or warn, when the IC has no typed power pin.
- `fixtures/` boards come through the KiCad netlist with real pin types, so they exercise the rule directly.
Tests: `pytest -q` → 522 passed, 3 failed:
- the new rail test (on purpose);
- the deliberate tscircuit record;
- test_committed_reflow_toml_is_caps_only (the local reflow.toml was emptied; uncommitted).

## 2026-10-22 · all 5 evals on Lightning (run 20261022T193720Z)
`reflow eval`, nvidia/nemotron-3.5-lightning:free, max_tokens 32000. 40,156 in / 233,367 out tokens; 0 part numbers outside the resolver.
- Summary: 2/5 "passed" (led_indicator on attempt 1 and clean; mcp9808_breakout on attempt 2, not clean). Go/no-go undecided, since all 5 expectations are drafts.
- **Measured against the real bar** (verifier-clean and matching the expectations), it's 1/5: only led_indicator.

**Per board:**
- **ams1117_regulator** (failed_compile; 1 attempt of 3):
  - Compile try 1: "Unterminated string literal", with no line from tsci (K-02a).
  - Try 2: `footprint="SOT-223"` is invalid in tscircuit.
  - The compile cap (2) ran out inside attempt 1, and the run ended there, without attempts 2 or 3 (loop.py, HUMAN; is this intended?).
- **at24c02_eeprom** (failed_verify, 3 attempts):
  - Pinout wrong every time: 5, 5, then 7 pinout.mismatch. Attempt 1 is off by one pin (pin4 WP … pin8 VDD).
  - Two of the compile tries had "no code fence" replies, which count against the compile cap.
- **led_indicator** (passed and clean on attempt 1): one "Unterminated string literal" retry first.
- **mcp9808_breakout** ("passed" on attempt 2, a **false pass**):
  - Attempt 1: 7 pinout.mismatch, 2 decoupling.missing, 1 i2c.missing_pullup.
  - Attempt 2 relabelled every pin correctly and the verifier found 0 errors, but:
    - U1.SDA and U1.SCL are unconnected;
    - U1.VDD is on `Net-(C1-pin1)` (C1, C3), not V3_3;
    - U1.GND reaches GND only through C2, a capacitor in series.
- **pcf8574_expander** (failed_verify, 3 attempts; best is attempt 2):
  - Attempt 1: 16 pinout.mismatch.
  - Attempt 2: 1 error (decoupling.missing), but U1 SDA/SCL/GND are unconnected and P0–P7 go to J2 on unnamed nets.
  - Attempt 3 regressed to 16 pinout.mismatch.

**Findings:**
1. **The verifier misses chips that aren't wired:** an IC whose SDA/SCL are unconnected triggers no I2C rule (`find_i2c_nets` skips unconnected pins), and an unconnected GND pin isn't an error. The project needs in rules.toml ("U1.SDA pullup to V3_3") would catch it, but R-10 isn't built (HUMAN).
2. **Wrong feedback led to a wrong fix:** in MCP9808 attempt 1, `decoupling.missing` fired on U1.4, the **GND** pin, which sat on an unconnected net. The model obeyed by adding C2 from the GND pin to GND, which puts a capacitor in series with ground.
   - Cause: V-12 types ground pins `power_in` (the KiCad convention), and `decoupling.check` tells ground from supply only by `is_ground(net name)`.
   - Fix options: the rule (HUMAN) skips pins whose function is a ground name, or the human decides another typing in V-12 (O-1b).
3. **Pinouts don't converge from per-pin hints:** AT24C02 and PCF8574 never got the pinout right in 3 attempts. The codegen prompt has no pin table, so the model guesses the pinout first time. Candidate (AGENT→HUMAN, prompt + cli): put the trusted pin map from the rules [[part]] symbol into the codegen prompt.
4. **Footprint names:** tscircuit rejects "SOT-223", but the prompt only gives soic8 as an example. There's still no footprint-vs-package check (MCP9808 again used soic8 for MSOP-8).
5. **Fragile replies:** "no code fence" replies use up compile tries.

## 2026-10-22 · agent (Claude) · V-22a: each chip's trusted pin table goes into the codegen prompt
Did: at the human's request.
- **Rendering:** `render_rules(rules, plan, pin_maps=None)` now adds, under each `[[part]]` reference line, that chip's pinout from its pin map, pins in physical order: `U1 pinLabels, from the KiCad symbol Sensor_Temperature:MCP9808_MSOP: pinLabels={{ pin1: "SDA", … pin8: "VDD" }}`. It's the same pin map V-12 binds the design to.
- **Loading:** `rules_prompt_block` loads the maps with `pin_maps_from_parts`, and a symbol that can't be read raises PinMapError. loop.py (HUMAN) already fills `{project_rules}` from it, so loop.py is unchanged.
- **codegen.md:** tells the model to copy that line exactly as the chip's pinLabels, to use those labels in traces, and never to take a pinout from memory or from the example.
- **Scope:** the fix prompt doesn't carry `{project_rules}`, so it has no table; per-pin fix hints stay as they were.
Tests:
- 5 new in tests/test_rules_prompt.py failed first: the table comes right after the reference line; physical pin order; the block reads each symbol; an unreadable symbol is loud; the codegen prompt the loop builds carries the table.
- New in tests/test_evals.py: each IC board's table has every pin of its installed KiCad symbol.
- test_a_rules_file_is_read_and_rendered now sets REFLOW_KICAD_SYMBOL_DIR to the test symbols, since rendering reads the symbol.
- Four sabotages each turn the suite red: no pin maps, sorting pins as text, base_name'd labels, dropping the prompt wording.
- `pytest -q` → 532 passed, 3 failed: the unpowered pull-up rail test (on purpose, HUMAN rule), the deliberate tscircuit record, and test_committed_reflow_toml_is_caps_only (local reflow.toml).

## 2026-10-22 · all 5 evals on Lightning with pin tables (run 20261022T204747Z)
`reflow eval` after V-22a (4766725). 20,198 in / 140,784 out tokens (down from 233k); 0 part numbers outside the resolver.
- Summary: 3/5 passed, all on attempt 1 (at24c02, led, pcf8574); 2 clean.
- Every board that compiled had the right pinout on the first try. Before, AT24C02 and PCF8574 never converged.
**Per board:**
- **ams1117_regulator** (failed_verify):
  - Attempt 1: compile try 1 used `footprint="SOT-223"` (invalid); try 2 compiled with 1 error, a pinout.mismatch on pin 4. That's the SOT-223 tab: tscircuit's footprint has a 4th pad, and KiCad's AMS1117-3.3 symbol has 3 pins, so this is a false error from the pin map. It needs the human's call (V-12 review).
  - Attempt 2: "no code fence", then SOT-223 again. The compile cap ran out and the run ended, without attempt 3.
- **at24c02_eeprom** (passed on attempt 1, not clean): pinout correct and everything wired, but WP is tied to V3_3, which write-protects the EEPROM. The draft expects GND. The rules file has no rules yet, so the verifier can't know; a datasheet rule "U1.WP tie GND" would catch it.
- **led_indicator** (passed and clean on attempt 1).
- **mcp9808_breakout** (failed_compile in attempt 1, so the run ended):
  - Compile try 1: the extracted TSX began with a literal "```tsx" line, so tsci saw a backtick template string that never ends ("Unterminated string literal"). The reply probably nested or doubled its fence: `extract_code_fence` returns the body of "```\n```tsx\n…```" with the inner opener included. The try-1 reply itself is lost, because response.md keeps only the last try.
  - Try 2: the reply was bare TSX with no fence → "no code fence".
- **pcf8574_expander** (passed and clean on attempt 1): every pin correct; INT left open.
**Biggest levers now:**
1. Running out of the compile cap ends the whole run (loop.py, HUMAN). That's what ended mcp9808 and ams1117.
2. Code-fence handling (codefence.py, AGENT): tolerate a doubled opener, keep every try's reply.
3. Footprint names in codegen.md (SOT-223 → sot223).
4. The AMS1117 tab pin.
5. Datasheet rules for the AT24C02 (WP).

## 2026-10-22 · agent (Claude) · E-01: eval runner reports stage, retries model calls, repeats runs, hashes prompts
Did: at the human's request, in `reflow/evals.py` and `reflow eval`:
- **Stage:** each board's `stage` says where it stopped: parts, model, compile, pin_binding (a `pinout.*` error in the best attempt's verify.json), rules, part_numbers, expectations, tool, or none (clean). Before, everything collapsed into failed_verify.
- **Model retries:**
  - A failed model call (any ModelError: timeout, empty or cut-off reply, provider error) is retried `model_retries` times (default 2). It waits `retry_wait_s` × the retry number between tries (default 10 s, then 20 s).
  - Each board records `model_retries` and the retried errors.
  - Totals give `model_errors` apart from `design_failures` (compile, pin_binding, rules, part_numbers, expectations), plus `by_stage`.
  - The go/no-go reason mentions runs lost to model errors.
- **Repeats:**
  - `--repeat N` / `repeats=N` runs each board N times. `boards` has one entry per run (`repeat`), and run folders are `<board>/run<N>`.
  - `by_board` gives runs, passed, first_pass, clean, model_errors, pass_rate, clean_rate, stages and `clean_majority`.
  - The go/no-go counts a board clean when more than half its runs were clean. With N = 1 that's the same as before.
- **Prompt hashes:** the run info records `repeats`, `model_retries`, a SHA-256 per prompts/*.md and one `prompts_hash` over them.
- **CLI:** prints each run's stage and retries, per-board rates when N > 1, and "X model error(s), Y design failure(s)".
Not done here: tracking which errors came back attempt after attempt (the loop going in circles).
Tests:
- 8 new in tests/test_eval_runner.py failed first: stage for clean/rules/expectations/compile/parts; pin_binding through a binder's pinout error; a flaky model retried with waits 10, 20; a model that keeps failing (3 calls) counted as a model error, not a design failure; 3 repeats with separate run folders and rates; majority-clean go/no-go over 5 checked boards; prompt hashes; `reflow eval --repeat 2` output.
- Six sabotages each turn the suite red: no retry, no pin_binding stage, shared run folder, one clean run counts, hashing the file name, model errors counted as design failures.
- `pytest -q` → 540 passed, 3 failed: the unpowered pull-up rail test (on purpose, HUMAN rule), the deliberate tscircuit record, and test_committed_reflow_toml_is_caps_only (local reflow.toml).

## 2026-10-22 · agent (Claude) · V-2b proposal: model-drafted rules, visible and confirmed (no code)
Did: at the human's request, wrote `docs/proposals/V-2b-model-drafted-rules.md` and added a PROPOSED row to DECISIONS.md. The proposal has four parts:
- (A) the datasheet-tutor skill writes rules.toml only after the study, or when the student says they've studied it, and marks every line `drafted_by = "model"` with a page and a quote;
- (B) `reflow init` writes the skill, AGENTS.md, CLAUDE.md and a skeleton rules.toml built from the pin map;
- (C) a contract change: `ProjectRule` gains optional `drafted_by` / `quote` / `confirmed_by`, filled only by a TTY-only `reflow rules confirm`; unconfirmed rules still run, but runs are labelled and eval boards with them are left out of the go/no-go;
- (D) `reflow learn REF` opens a separate Claude Code session (`claude --name … "<first message>"`; the flags were checked against the installed CLI).
A hidden instruction for the student's model was considered and rejected; the proposal says why. It lists 5 questions for the human and the tasks that follow acceptance (V-23, V-24, I-01, H-08b, L-04).
Tests: none (no code).

## 2026-10-22 · agent (Claude) · V-2b answers 3–5; skill moved
Did: the human answered three of V-2b's questions in chat:
- Q3: `reflow rules confirm` needs a real terminal.
- Q4: on macOS, `reflow learn` opens a new Terminal window and runs the commands; Windows/Linux print them, later.
- Q5: move the skill.
Recorded them in the proposal and the DECISIONS.md row. Q1 (which rules need confirming) and Q2 (where the `confirmed_by` name comes from) are still open, and V-2b is still PROPOSED.
- Moved `docs/proposals/datasheet-tutor-SKILL.md` → `skills/datasheet-tutor/SKILL.md` (git mv; text unchanged) and updated the pointer in docs/proposals/V-2-rule-framework.md.
Tests: none (docs only).

## 2026-10-22 · agent (Claude) · V-2b answers 1–2
Did: recorded the human's answers in the proposal and the DECISIONS.md row:
- Q1: (a) for students, only model-drafted rules need confirming; eval boards need every rule confirmed.
- Q2: the confirmed_by name is typed at the prompt, defaulting to git user.name.
All five questions are now answered. V-2b stays PROPOSED until the human accepts it, and the contract patch (V-23) waits on that.
Tests: none (docs only).

## 2026-10-22 · agent (Claude) · V-2b accepted; tasks added
Did: the human accepted V-2b in chat. Moved its row to Accepted in DECISIONS.md (2026-10-22), with the answers folded into the decision, and set the proposal's status to ACCEPTED. Added to TASKS.md, all todo:
- V-23: the contract patch and unconfirmed labels (AGENT→HUMAN);
- V-24: `reflow rules confirm`;
- I-01: `reflow init`;
- H-08b: the skill and AGENTS.md text (AGENT→HUMAN);
- L-04: `reflow learn`.
No code.
Tests: none (docs only).

## 2026-10-22 · agent (Claude) · learn mode v2 accepted (L-2, D-4, D-5, O-1c); tasks added
Did: the human pasted their learn-mode v2 system design and answered four questions in chat:
- accept it, with its four contracts;
- O-1c: the agent writes L-01 and the testbenches, and the human reviews them;
- FastAPI as an optional `[learn]` extra;
- phases 1–2 first.
Saved the design as `docs/proposals/L-2-learn-mode-v2.md`, with the choices on top. In DECISIONS.md, D-4 and D-5 moved to Accepted, and L-2 and O-1c were added. TASKS.md: L-01 is now AGENT→HUMAN under O-1c; added L-10 (phase 1), L-11 (phase 2), L-12 (phase 3, after the human looks) and L-13 (phase 4).
Interim answers, for the human to confirm:
- the free-text why is shown, not graded;
- break-it runs only on request;
- V-2b's `reflow learn REF` is renamed `reflow study REF`, so `reflow learn RUN_DIR` opens learn mode.
Dependencies checked (PyPI/npm, 2026-10-22): FastAPI 0.161.1 MIT, uvicorn 0.54.0 BSD-3, fsrs 6.3.2 MIT, httpx 0.28.1 BSD-3; React 19.3.1, Vite 8.3.5, @vitejs/plugin-react 6.1.2, @tscircuit/pcb-viewer 1.11.433, react-force-graph-2d 1.29.2, all MIT. @tscircuit/schematic-viewer 2.0.105 has no license on npm, but its GitHub LICENSE is MIT; its peer dependencies are `tscircuit` and `typescript`.
Tests: none (docs only).

## 2026-10-22 · agent (Claude) · L-01: spot-the-bug selection and grading (O-1c, awaiting human review)
Did: new `reflow/learn/engine.py`: `load_run`, `pick`, `grade`, `concept_of`.
- **What's asked:** interactions come from the first failed attempt's verify errors only, one per concept, at most `limit` (default 3).
- **Root cause first:** a part with `pinout.mismatch` gets that interaction, and that attempt's other errors on the same part are left out as consequences, with a note. The fixture's decoupling error is on the real GND pin, so teaching it would teach wrong physics.
- **The right answer:** the violation's refs; for a violation with no refs (`i2c.missing_pullup`), any part on its nets.
- **What the user sees first:** the prompt never names the part or the rule, and the hint names the area only.
- **Grading** is by the part clicked:
  - right on the first try without the hint → good;
  - right with the hint or on the second try → hard;
  - wrong twice → again, the answer is shown, and the user moves on.
  The free-text why is recorded, not graded (L-2 interim).
- Fixtures: `tests/data/real_runs/learn_mcp9808_20261022/` (eval 20261022T193720Z, attempt 1 failed with 10 errors, attempt 2 passed) and `learn_at24c02_first_pass_20261022/` (passed on attempt 1), with READMEs.
For the human reviewer:
- the consequence rule only keys on `pinout.*`;
- a run with no failed attempt gets no interaction (make-the-call is L-13);
- skip logic arrives with concept cards in L-11.
Tests: tests/test_learn_engine.py (14) failed first (module missing), then passed. Four sabotages each turn it red: teaching consequences, a leaky prompt, retrying until right, ignoring skip. `pytest -q` → 554 passed, 3 failed (the unpowered pull-up rail test on purpose, the deliberate tscircuit record, and the caps-only config test from the local reflow.toml).

## 2026-10-22 · agent (Claude) · L-10: learn mode web UI, phase 1
Did:
- **Server:** `reflow/learn/server.py` (FastAPI, 127.0.0.1 only):
  - `/api/run`, `/api/circuit/{n}`, `/api/learn/next` (without the answer), `/api/learn/hint`, `/api/learn/answer`;
  - `/api/signoff` writes a strict `SignOff` plus `learn.json` (`LearnRecord`), and nothing else in the run folder changes;
  - every response sends a same-origin Content-Security-Policy.
- **Command:** `reflow learn RUN_DIR [--port] [--no-browser]` opens the browser, and says how to install the extra when FastAPI is missing.
- **Packaging:** `pyproject.toml` gets the `[learn]` extra (fastapi 0.161.1, uvicorn 0.54.0, fsrs 6.3.2) and a `[test]` extra (pytest>=8, httpx 0.28.1); reflow/learn/static is package data.
- **Front end:** `web/` (Vite 8.3.5 + React 19.3.1, exact pins), with the schematic viewer 2.0.105 and PCB viewer 1.11.433 wrapped in one component (`BoardView.tsx`). It has:
  - Schematic/PCB tabs and a board picker (the AI's draft vs the final board);
  - the spot-the-bug panel: click a part in the schematic or use part buttons, write a one-sentence why, check, hint, reveal with what the check found, why it matters, your sentence and the fix;
  - sign-off with the remaining warnings and overrides.
  The build (2.7 MB JS) is committed under reflow/learn/static, so users don't need Node.
- **Offline:** the schematic viewer's CDN importer is aliased to a stub, its jlcsearch price lookup gets a failing fetch, and the CSP blocks anything else. A browser check confirmed every request stayed on localhost.
- **Found and fixed in the browser:** duplicate React copies (Vite `dedupe`), and a stale click handler that changed the shown pick after the reveal.
Checked in the built-in browser on a copy of the MCP9808 run:
- the draft schematic renders with the mirrored pinout;
- clicking U1 selects it, and a right answer reveals the why;
- a wrong pick gets the hint, and a second wrong pick shows "It was U1";
- Next → "That's everything" → sign-off writes signoff.json;
- the PCB tab renders (unrouted);
- no console errors.
Not done here (L-11 onward): SSE `/api/events`, concept cards and the vault, simulation. The PCB has no traces because tscircuit didn't route these boards.
Tests: tests/test_learn_server.py (14) and tests/test_learn_cli.py (3) failed first, then passed. Four sabotages each turn them red: leaking the answer, no CSP, no learn.json, listening on 0.0.0.0. `pytest -q` → 571 passed, 3 failed (the same three as before). Upstream warning: Starlette deprecates `httpx` in its test client in favour of `httpx2`.

## 2026-10-22 · agent (Claude) · L-11: concept cards, skip logic and the vault (learn mode phase 2)
Did:
- **Contracts:** `ConceptCard{concept, fsrs, last_reviewed, ratings}` and `VaultNote{path, kind, title, links}` (approved by L-2) in reflow/contracts.py, docs/04 §8, the frozen field list, and `docs/examples/concept_card.json` / `vault_note.json`. The contract loader doesn't check dict fields, so `fsrs` is the scheduler card as a JSON string and VaultNote has no frontmatter field.
- **`reflow/learn/vault.py`:** `Vault(root, now=)`, at `REFLOW_VAULT`, else `~/.reflow/vault`:
  - one fsrs 6.3.2 card per concept, in the frontmatter of `concepts/<concept>.md`, written as JSON values (valid YAML);
  - `known()` = recall above 0.9;
  - `review()` takes good/hard/again from what the user did;
  - `write_mistake()` / `write_board()` write Obsidian-style notes joined by [[wikilinks]], and `graph()` returns the same graph;
  - a concept note's `## My notes` survives rewrites, and the reader also accepts the simple YAML Obsidian might write back.
- **Server:**
  - concepts known in the vault are skipped, with their recall;
  - `POST /api/learn/unskip` asks one anyway;
  - each finished interaction rates its card and writes the mistake and board notes, and sign-off updates the board note;
  - `GET /api/vault/graph`;
  - `reflow learn --vault DIR`.
- **Fixed after a browser check:** the "why some checks aren't asked" notes named the part and the rules in the pending response. They now come only once nothing is left to answer, and the test checks that the whole pending response doesn't name the part.
- **UI:** "Skipped: pinout, you've got it (recall 100%). [Do it anyway]", a Vault tab with a force graph (react-force-graph-2d 1.29.2) plus a note list with obsidian:// links, and "noted in your vault" after a reveal. No scores are shown.
Checked in the built-in browser on a copy of the MCP9808 run with a scratch vault (the user's ~/.reflow was never written):
- answering wrote three linked notes, and the Vault tab drew them;
- a second session on a fresh copy skipped pinout, and Do it anyway brought the question back;
- no console errors.
For the human reviewer:
- one good answer puts recall above 0.9 for about two days, so the next board skips the concept;
- a concept note's "why" is the latest violation's why, which names that board's nets.
Tests: tests/test_learn_vault.py (9) and 6 new in tests/test_learn_server.py failed first, then passed; tests/test_contracts.py covers the two contracts. The server tests now use a temporary vault, so a test run never writes to ~/.reflow. Four sabotages each turn the suite red: never skip, drop My notes, always rate good, no sign-off on the board note.
`pytest -q` → 590 passed, 3 failed (the same three: the pull-up rail test on purpose, the tscircuit record, and the caps-only config test from the local reflow.toml).

## 2026-10-22 · agent (Claude) · L-2a accepted: fix-it tools and simulation; tasks L-12, L-14, X-01
Did: the human asked in chat for fix-it tools with schematic simulation (decoupling, I²C pull-ups), routing, and PCB-level simulation. Wrote that up as `docs/proposals/L-2a-fix-it-and-simulation.md` and added DECISIONS row L-2a (accepted in chat).
- Fix-it edits the draft's TSX and re-verifies it locally with tsci, with no model call.
- The ngspice testbenches each have a hand-calculated value and known-good/bad tests, and their assumptions are labelled.
- PCB-level uses the cap-to-pin path (trace length, or the pad distance as a lower bound) at ~1 nH/mm.
- New contracts: SimRequest, SimResult, SimSignal, FixEdit, FixResult.
- TASKS: L-12 rewritten (doing), L-14 added (doing), X-01 doing.
Tests: none (docs only).

## 2026-10-22 · agent (Claude) · L-12, L-14, X-01, X-04: simulation, fix-it tools, routing (L-2a)
Did: one commit for the three requests (they share server.py, contracts.py and the UI).
- **L-12 testbenches (O-1c, awaiting review):** `reflow/learn/sim.py` runs ngspice as a separate process.
  - Decoupling: wiring 20 nH and 0.05 Ω; a 330 Ω DC load plus a 50 mA step in 1 ns; the cap with 0.01 Ω ESR and 0.4 nH ESL; a series-cap case; and, at PCB level, the cap-to-pin path at 1 nH/mm.
  - I²C: pull-up, 100 pF bus, open-drain switch, 30→70% rise time against UM10204's 1000/300 ns.
  - Measured against hand calculations: no cap 1.012 V (1.0 by hand); 100 nF 22.45 mV (22.36); series cap at τ 1.214 V (1.214); PCB 20 mm 0.506 V (0.505); PCB 2 mm 108 mV (107); 4.7k rise 397 ns (398); 1k 84 ns (84.7); 47k 3.98 µs, bad.
  - Every assumption is listed with the plot. Thinning the plot keeps each bucket's min and max, so spikes aren't hidden. Without ngspice nothing is plotted.
- **Board values:** `reflow/learn/board_values.py` reads the cap and pull-up values, the supply from spec.power, and the PCB path (routed trace length, or the pad distance as a labelled lower bound) from the bound netlist. It refuses a supply pin connected to nothing, or an I²C pin on no bus, and says why.
- **L-14 fix-it:** `reflow/learn/fixit.py` edits the draft's TSX: add_part, set_value, connect, disconnect, delete, set_label, set_trace_limit.
  - Endpoints are validated, so an edit can't inject text into the TSX, and added parts carry no part number.
  - `check_fix` recompiles with tsci and verifies with the run's binder and rules (no model call), saving to `learn/fix/<n>/`. A board the verifier refuses (a short) comes back with `refused` set.
- **Contracts (L-2a):** SimSignal, SimRequest, SimResult, FixEdit (`FIX_KINDS` includes set_trace_limit), FixResult, plus docs/04, the frozen fields, and examples sim_result.json / fix_result.json.
- **Server:** POST /api/fix, GET /api/fixes, GET /api/fix/{n}/circuit, GET /api/fix/ai (a diff of the AI's final vs the draft; 403 until the user has tried a fix), POST /api/sim, POST /api/route.
- **UI:**
  - a Fix it yourself panel (tools, an edit list, Check my fix, Show the AI's fix) with a simulate section: the draft vs your fix vs the AI's final, an SVG plot, verdicts, notes, assumptions, and a PCB-path toggle;
  - the board picker lists your fixes, and the page now opens on the AI's draft (it used to fetch the final board first);
  - the PCB view has a route status line.
- **X-01/X-04 routing:**
  - Found why nothing routed: @tscircuit/core gives a decoupling cap's traces `DEFAULT_MAX_DECOUPLING_TRACE_LENGTH_MM = 1` and skips routing the whole board when placement can't meet it. With 3 mm the eval board routes (C1→VDD 2.89 mm); 2 mm doesn't.
  - codegen.md now asks for `maxDecouplingTraceLength="3mm"` on decoupling caps (H-08, for the human's review).
  - `reflow/route.py` `route_report` reads the router's outcome and runs `kicad-cli pcb drc` itself. It says `routed` only with every net in copper and 0 DRC errors.
  - The routed eval board has 0 unconnected items, but 38 DRC errors against KiCad's default board rules: tscircuit's 0.15 mm tracks vs a 0.2 mm minimum, 0.3/0.2 mm vias, 0.1075 mm clearance. So it's reported as `partial`. Which fab's rules to check against is the human's decision.
- **Fixtures:** the learn fixture gained each attempt's TSX and a copy of rules.toml (spec.json now says "rules.toml", so the folder works when copied); `tests/data/routing/mcp9808_fixed.tsx` + README. `load_run` resolves a relative rules_file against the run folder.
Checked in the built-in browser:
- the real draft fixed through the UI (8 relabels + 4 connects + C1 within 3 mm) passes every check;
- decoupling: the draft is refused (U1.VDD connected to nothing), your fix dips 22 mV, the AI's final 22 mV;
- I²C: the draft never rises, your fix 397 ns, the AI's final is refused (SDA on no bus, the known false pass);
- PCB level on the routed fix: 2.9 mm routed trace → 142 mV (hand: 141.6);
- the route status line shows "partly routed" with the counts.
Found while checking: `kicad-cli pcb drc` hangs when the learn server is started by the desktop app's preview launcher (it runs inside the app's process context), but runs in 0.9 s when `reflow learn` is started from a normal shell. Subprocesses now get an empty stdin anyway.
Tests:
- New, all failing first: tests/test_learn_sim.py (14, ngspice), tests/test_learn_board_values.py (6), tests/test_learn_fixit.py (17, 3 with real tsci), tests/test_route.py (3, tsci + kicad-cli), 9 new in tests/test_learn_server.py, a codegen prompt test, and the contract entries.
- Exception: the /api/fixes test was written together with the endpoint, not before it.
- Sabotages each turn the suite red: ignoring the PCB path, thinning that hides minima, a slow edge, I²C always good (caught only after adding the 47k case), no endpoint check, routed despite DRC errors, an ungated AI fix, simulating an unpowered chip.
`pytest -q` → 648 passed, 3 failed (the same three: the pull-up rail test on purpose, the tscircuit record, and the caps-only config test from the local reflow.toml).

## 2026-10-23 · agent (Claude) · exported boards use JLCPCB standard 2-layer rules
Did: the human chose JLCPCB's standard 2-layer rules. Read https://jlcpcb.com/capabilities/pcb-capabilities (2026-10-23) twice, the second time for verbatim rows:
- track width / spacing (1 oz) 0.10 / 0.10 mm; pad-to-track 0.1 mm;
- via hole / diameter 0.15 / 0.25 mm (0.1/0.2 mm only for boards ≤ 1 mm thick with ENIG/OSP, not used); via diameter 0.1 mm larger than the hole, so a 0.05 mm ring;
- 2-layer drill 0.15–6.3 mm; via hole-to-hole 0.2 mm; copper to a routed edge ≥ 0.2 mm;
- silkscreen line ≥ 0.15 mm, text ≥ 1.0 mm.
The quotes are in tests/test_fab_rules.py.
- **The change:** new `reflow/fab_rules.py` (`JLCPCB_2LAYER`, `write_kicad_project`). `compile_board` now writes `board.kicad_pro` with those minimums next to every exported `board.kicad_pcb`. `kicad-cli pcb drc`, and KiCad when the user opens the board, read it; the board files themselves are unchanged. route.py's docstring now says which rules DRC uses.
- **Result on the routed MCP9808 eval board:** 0 DRC errors and 0 unconnected, so `route_report` says `routed` (it said `partial`, with 38 errors, under KiCad's defaults). 17 warnings remain:
  - 5 silkscreen text below JLCPCB's 1.0 mm (tscircuit writes 0.62 mm);
  - 3 text strokes thinner than 0.15 mm;
  - 4 silkscreen overlaps;
  - 5 "footprint library 'tscircuit' not configured".
  Fab-relevant but not errors.
- **Not modelled:** JLCPCB's surcharges near the minimums (e.g. smaller vias cost more), and rules the page gives no 2-layer number for (they keep KiCad's defaults).
Tests:
- tests/test_fab_rules.py (2) and 2 new in tests/test_route.py failed first (module missing): the routed board passes JLCPCB's rules with status routed, and the known-bad case (one segment thinned to 0.05 mm) still fails with a track_width error, status partial.
- Sabotage: setting min_track_width to 0 turns 2 tests red.
`pytest -q` → 652 passed, 3 failed (the same three: the pull-up rail test on purpose, the tscircuit record, and the caps-only config test from the local reflow.toml).

## 2026-10-24 · agent (Claude) · M-04: REFLOW_PROVIDER=claude-code (model calls on the user's Claude Code login)
Did: at the human's request (to avoid buying API credits).
- **New `reflow/claude_code.py`:** `ClaudeCodeModel.complete` runs `claude -p --output-format json --tools "" --no-session-persistence --system-prompt <system> [--model <REFLOW_MODEL>]`, with:
  - the prompt on stdin;
  - a fresh, empty temporary folder as the working directory, deleted afterwards;
  - `ANTHROPIC_API_KEY` removed from the CLI's environment, so a key in the shell is never billed instead of the login.
  It parses `result`, `usage` (input + cache tokens) and the model that answered. An error reply, a non-zero exit with no JSON, an empty reply, a timeout or a missing CLI each raise ModelError with the reason. max_tokens doesn't apply.
- **Loader:** `reflow.claude_code.load_model` handles "claude-code" and leaves every other provider to `reflow.llm.load_model`, which is unchanged.
- **Config:** `load_config(keyless_providers=...)` skips the REFLOW_API_KEY requirement for the providers the caller names. The CLI passes `reflow.providers.KEYLESS_PROVIDERS = {"claude-code"}`.
- **Why it's split this way:** the existing tests keep llm.py and config.py stdlib-only and free of vendor and model names. Those tests weren't changed; the new code sits beside them.
- **Also:** cli.py uses the new loader; .env.example documents the option. My own eval-runner test stub now accepts keyword arguments.
- **A probe before building:** `claude -p` with tools off answered "ok" in 3.5 s on claude-opus-5-5.
Tests:
- New, failing first: tests/test_claude_code.py (10, a fake `claude` that records argv, stdin, cwd and env) and 2 in tests/test_config.py (no key needed for claude-code; other providers still need one).
- Sabotages each turn the suite red: dropping `--tools ""`, passing ANTHROPIC_API_KEY through.
- Separately: test_committed_reflow_toml_is_caps_only passes again, because the human restored reflow.toml.
`pytest -q` → 665 passed, 2 failed (the unpowered pull-up rail test on purpose, and the deliberate tscircuit record).

## 2026-10-24 · MCP9808 eval on Claude Code (Sonnet 5.5), run 20261024T173321Z
`reflow eval --only mcp9808_breakout` with REFLOW_PROVIDER=claude-code REFLOW_MODEL=sonnet (one-off override; the human's .env unchanged).
- **Result:** passed on attempt 1, clean (matches every draft expectation), 0 part numbers outside the resolver, 0 model retries. 3,334 in / 1,133 out tokens; the model was claude-sonnet-5-5.
- **Pinout:** right on every pin. SDA, SCL, VDD→V3_3, GND and A0–A2→GND are all wired, and Alert is left open.
- **Routing:** the TSX set maxDecouplingTraceLength. `route_report` gives **routed**: 4/4 nets in copper, 0 unconnected, 0 DRC errors under JLCPCB 2-layer rules, 15 warnings (silkscreen and library).
- **Compared with free Lightning:** Lightning took 2 attempts and passed with a broken board. Expectations are still drafts, so the go/no-go stays undecided.

## 2026-10-27 · all 5 evals on Claude Code (Sonnet 5.5), run 20261028T004800Z
`reflow eval --repeat 1` with REFLOW_PROVIDER=claude-code REFLOW_MODEL=sonnet (one-off override; .env unchanged). 59,159 in / 9,539 out tokens; 0 model retries, 0 part numbers outside the resolver.
**4/5 passed on attempt 1, and all 4 are clean** (they match every draft expectation). Go/no-go is undecided only because the 5 expectations are still drafts.
Per board:
- **ams1117_regulator** (failed_verify, stage pin_binding, 3 attempts): each attempt has pins 1-3 right (GND, VO→V3_3, VI→V5) and one `pinout.mismatch` on pin 4, the SOT-223 tab pad that KiCad's 3-pin AMS1117 symbol lacks (known; the human's V-12 call). Attempt 2's first compile try used footprint "sot223_3" (invalid). Attempt 3 wired the tab to V3_3, correct per the datasheet, and was still flagged. Not routed: autorouting skipped (C1 is 3.49 mm from V5, over the 3 mm limit).
- **at24c02_eeprom** (passed, clean): every pin correct, WP to GND (the Lightning runs tied it high). Not routed: autorouting skipped, because C1's ground side is 3.56 mm from GND, over 3 mm.
- **led_indicator** (passed, clean): **routed** 3/3, 0 DRC errors, 8 warnings.
- **mcp9808_breakout** (passed, clean): every pin correct; **routed** 4/4, 0 DRC errors (JLCPCB rules), 15 warnings.
- **pcf8574_expander** (passed, clean): all 16 pins correct, INT open. Not routed: C1's ground side is 3.46 mm from GND.
**Finding:** tscircuit applies maxDecouplingTraceLength to both cap traces, including the ground side to the nearest GND pad. With 3 mm, placement misses by about 0.5 mm on 3 of 5 boards, and routing is skipped for the whole board. Options for the human: ask codegen for 5 mm (it routed the MCP9808 earlier; the PCB-level sim shows the droop cost of the longer path), or have codegen place the cap with pcbX/pcbY next to the pin.

## 2026-10-27 · agent (Claude) · codegen asks for a 5 mm decoupling trace limit
Did: at the human's request, codegen.md now asks for `maxDecouplingTraceLength="5mm"` (was 3 mm). tscircuit applies the limit to both of the cap's traces, including the ground side, and at 3 mm placement missed by ~0.5 mm on 3 of 5 boards in run 20261028T004800Z. Updated the reflow/route.py docstring and tests/data/routing/README.md to match. The fix-it tool's "3mm" example is unchanged (any value in mm works).
Tests: test_codegen_gives_decoupling_caps_a_routable_length_limit now requires 5 mm and no 3 mm; it failed first, then passed.
`pytest -q` (without tests/test_learn_sim.py and the two server tests that call `find_engine`, which another session has in progress for a KiCad libngspice engine) → 649 passed, 2 failed (the unpowered pull-up rail test on purpose, and the deliberate tscircuit record).

## 2026-10-27 · agent (Claude) · L-12: simulation falls back to KiCad's bundled ngspice
Did: at the human's request.
- **Engine order in `reflow/learn/sim.py`:** the ngspice command (REFLOW_NGSPICE, else `ngspice` on PATH) comes first, then KiCad's bundled libngspice (REFLOW_LIBNGSPICE, else the library next to kicad-cli; on macOS KiCad 10 that's Contents/Frameworks/libngspice.0.dylib, ngspice-45.2). New `Engine`, `find_engine`, `find_cli_engine`, `find_kicad_engine`; `find_ngspice` is kept.
- **The KiCad path:** new `reflow/learn/_libngspice.py`, run as a child process (`python -m reflow.learn._libngspice LIB DECK OUT VECTOR`), so the library's global state, a hang or a crash stay out of the learn server, and the 120 s timeout still applies.
  - It loads the library with ctypes, feeds it the deck's circuit lines (the `.control` block is replaced by `run` plus a vector read), and writes the same "time value" rows as `wrdata`. The testbench measurements are unchanged.
  - Found while probing: `ngGet_Vec_Info` returns one struct the library reuses on every call, so each vector is copied out before the next lookup.
- **Results and notes:** each result now ends with "Simulated with the ngspice command (…)" or "Simulated with KiCad's bundled ngspice library (ngspice-45.2 shared library)". With no engine, the note says to install ngspice or KiCad.
- **Both engines against the hand calculations** (CLI ngspice-47 / KiCad 45.2 / by hand):

  | Case | CLI | KiCad | By hand |
  |---|---|---|---|
  | No cap | 1.012 V | 1.012 V | 1.0 V |
  | 100 nF | 22.45 mV | 22.45 mV | 22.36 mV |
  | Series cap at τ | 1.214 V | 1.214 V | 1.214 V |
  | PCB 20 mm | 0.5062 V | 0.5062 V | 0.505 V |
  | PCB 2 mm | 108.3 mV | 108.3 mV | 107.1 mV |
  | 4.7k rise | 397 ns | 400 ns | 398 ns |
  | 1k rise | 84.0 ns | 85.0 ns | 84.7 ns |
  | 47k rise | 3.995 µs | 3.972 µs | 3.982 µs |

  All are within 1.2%. With no pull-up, the KiCad engine also says the line never rises.
Tests:
- tests/test_learn_sim.py now runs every test once per engine (an autouse fixture, skipped when an engine isn't installed): 36 passed here, 18 on each. Plus 4 new tests on engine choice and notes.
- tests/test_learn_server.py's ngspice skips use `find_engine`.
- Sabotage: writing the time vector as the signal in the helper fails 9 tests, all KiCad-engine ones; the CLI tests stay green.
`pytest -q` → 687 passed, 2 failed (the unpowered pull-up rail test on purpose, and the deliberate tscircuit record).

## 2026-10-27 · three unrouted boards rerun on Sonnet with the 5 mm limit (run 20261028T010434Z)
Claude Code, Sonnet 5.5; 18,877 in / 6,449 out tokens; 0 model retries; codegen at 4e59637.
- **ams1117_regulator** (failed_verify, pin_binding, 3 attempts; the same tab-pin-4 mismatch as before):
  - routing now works on all three attempts: 3/3 nets in copper, 0 unconnected;
  - attempts 1 and 3 have 0 DRC errors;
  - attempt 2 has 2 hole_clearance errors (a via 0.216 mm from U1 pad 1).
- **at24c02_eeprom** (passed, clean): 4/4 nets in copper, 0 unconnected, 1 DRC error: hole_clearance, a via 0.198 mm from the SCL track. Status partial.
- **pcf8574_expander** (passed, clean): still not routed, now for a different reason. tscircuit skipped autorouting for 5 placement errors: on a 40×30 mm board, J1 sticks out by 0.56 mm and J2 (8-pin) by 4.64 mm, and three of their plated holes sit at the board edge. KiCad DRC: 1 copper_edge_clearance error, 21 unconnected.
**Hole clearance:** KiCad's `min_hole_clearance` stayed at its 0.25 mm default (fab_rules.py set no number for it). JLCPCB's page (re-read 2026-10-27) gives "Via hole to Track" 0.2 mm and "PTH to Track" 0.28 mm (0.35 recommended). KiCad's base rules have one hole-clearance number for both, so separate via and PTH limits need a custom rules file.
- Under JLCPCB's numbers, the AMS1117 errors (0.216 mm via-to-pad) are false.
- The AT24C02 error (0.198 mm via-to-track) is a real violation, by 0.002 mm.
**Placement:** the PCF8574 board needs more room for its headers. Codegen sets the board size, and tscircuit's packing pushed the headers past the edge.

## 2026-10-27 · agent (Claude) · JLCPCB hole-to-copper rules on exported boards
Did: at the human's request. JLCPCB's page (re-read 2026-10-27) gives "Via hole to Track" 0.2 mm and "PTH to Track" 0.28 mm ("0.35mm is recommended, minimum 0.28mm"). KiCad's board rules have a single hole clearance, so:
- `FabRules` gains `via_hole_clearance` 0.20 and `pth_hole_clearance` 0.28, and `min_hole_clearance` is 0.20 (the via figure, as the floor);
- `write_kicad_project` now also writes `board.kicad_dru` next to the board, with two custom rules: vias (`A.Type == 'Via' || B.Type == 'Via'`) at 0.2 mm, and plated through-hole pads (`A.Pad_Type == 'Through-hole' || ...`) at 0.28 mm.
`kicad-cli` reads both files from the board's folder.
- **Checked against real boards first:**
  - the AT24C02 via 0.198 mm from SCL is flagged under "JLCPCB via hole to track";
  - the AMS1117 via 0.216 mm from a pad passes (KiCad's 0.25 mm default had flagged it);
  - with the PTH rule raised to 2 mm, all 16 hits on the routed MCP9808 are J1 header holes under "JLCPCB PTH hole to track", so the condition matches PTH pads. At 0.28 mm the board is clean (closest 1.25 mm).
- **Re-check of run 20261028T010434Z with the new rules:**
  - ams1117 attempts 1, 2 and 3 are all **routed**, 3/3 nets, 0 DRC errors (attempt 2's 2 errors are gone);
  - at24c02 is partial, 4/4 nets in copper, with 1 real error: the via 0.198 mm from SCL, under JLCPCB's 0.2 mm;
  - pcf8574 is failed, 0/12 nets: placement, not hole clearance (headers off a 40×30 mm board; 1 copper_edge_clearance error).
Tests:
- Fixtures: 3 real .kicad_pcb files in tests/data/routing/ (README).
- tests/test_fab_rules.py has 5 new tests, failing first: the values; the .kicad_dru content; the 0.198 mm via fails by name; the 0.216 mm via passes; the PTH rule applies to PTH pads (2 mm variant fails, 0.28 mm passes).
- Sabotage: a via-only PTH condition fails 4 tests; no via rule fails 3.
`pytest -q` → 692 passed, 2 failed (the unpowered pull-up rail test on purpose, and the deliberate tscircuit record).

## 2026-10-27 · agent (Claude) · L-12: testbenches now match exact solutions to 0.000004%
Did: the human said up to 1.2% from the hand calculations was too much. I measured where it came from.
- **Two parts:**
  - The textbook formulas are approximations of the testbench circuit: L·ΔI/t_r is 0.27% under the exact no-cap droop, and the parallel-inductance formula is 1.0% under at 2 mm.
  - The simulation had numerical error: 0.9% on the no-cap case from a 0.2 ns step, and I²C crossings quantized to the next sample.
- **New `tests/sim_reference.py`:** exact solutions of each testbench without ngspice.
  - Closed forms for the no-cap droop, and for the I²C rise time including the switch's on and off resistance.
  - Exact propagation of the circuit's state equations (matrix exponential, scaling and squaring; the ramps become extra states) for the shunt cap, the PCB path and the series cap.
  - The general solver matches the closed form to 5e-8 when the cap branch is removed.
- **`reflow/learn/sim.py` settings:**
  - The decoupling step now comes at 100 ns: ngspice starts from the DC operating point, so the old 5 µs settle wasn't needed. The run covers 1.5 µs at a 10 ps maximum step.
  - The series cap uses τ/20000; I²C uses RC/5000, with threshold crossings interpolated between samples.
  - `.options method=trap trtol=1`: with the default trtol of 7, the trapezoidal integration rang at the load step's first corner under an inductor and read the 100 nF droop 19% high once the step was fine. Gear needed a 5× smaller step to match.
  - Each run takes ≤ 0.5 s.
- **Result:** every case matches its exact solution to within 0.000004% (worst: PCB 2 mm, 4e-8), on both the ngspice command (47) and KiCad's library (45.2): no cap, 100 nF, series cap at τ and at 3τ, PCB 20 mm and 2 mm, and I²C at 4.7k, 1k and 47k.
Tests:
- tests/test_learn_sim.py now checks each measurement against the exact reference with rel=1e-6 (was 5–15% against the formulas), on both engines.
- New tests pin each textbook formula's gap from the exact answer (0.27%, 0.4%, 0.25%/1.0%, 0.02%, and exact to 8 digits for the rise time), and check that the reference's two methods agree. 52 passed.
- Sabotages each turn the suite red: the default trtol fails the 100 nF case on both engines; no crossing interpolation fails 6 I²C cases.
`pytest -q` → 708 passed, 2 failed (the unpowered pull-up rail test on purpose, and the deliberate tscircuit record).

## 2026-10-27 · agent (Claude) · X-01: codegen leaves board size and placement to tscircuit
Did: the PCF8574 eval board (run 20261028T010434Z) didn't route because the model drew a 40 × 30 mm board and placed parts by hand: J1 sat 0.56 mm and J2 4.64 mm past the edge, and tscircuit skips routing on placement errors.
- **What tscircuit does with the same draft (tsci 0.0.2768):**
  - no width/height and no pcbX/pcbY: tscircuit places the parts and sizes the board around them (23.28 × 21.875 mm); every part is inside the edge and all 12 nets route;
  - no width/height but the model's placement: it fits, but the decoupling traces come out 8.35 and 8.98 mm, over the 5 mm limit.
- **prompts/codegen.md:** the example is now `<board>`; write it with no width or height unless the spec gives a board size; never set pcbX or pcbY. compile.py still never edits the model's code.
- tests/data/routing/pcf8574_40x30.tsx is the real draft, unchanged (README).
Tests:
- tests/test_prompts.py: the prompt asks for `<board>` with no size, sets a size only from the spec, and forbids pcbX/pcbY (failed first).
- tests/test_route.py: the real draft reports J2 outside the board and routing failed; the same board unsized and unplaced has every part ≥ 0.2 mm (JLCPCB copper to edge) inside the edge, 12/12 nets, nothing unconnected, and no copper_edge_clearance error. These two record tscircuit's behaviour and passed on first run.
- Our DRC still finds 2 router vias under JLCPCB's 0.2 mm via-to-track rule on the unsized board; the test doesn't claim "routed".
`pytest -q` → 711 passed, 2 failed (the unpowered pull-up rail test on purpose, and the deliberate tscircuit record).

## 2026-10-27 · agent (Claude) · X-01: PCF8574 rerun on Sonnet with the unsized-board prompt
Did: `REFLOW_PROVIDER=claude-code REFLOW_MODEL=sonnet reflow eval --repeat 1 --only pcf8574_expander` (one-off override, .env unchanged), run 20261028T025622Z.
- Verify: passed on attempt 1, clean, 0 foreign part numbers (expected.toml still draft).
- The model wrote `<board>` with no size and no pcbX/pcbY; tscircuit sized it 23.28 × 21.875 mm, with no placement errors.
- Routing: 12/12 nets in copper, nothing unconnected. Status **partial**: our DRC has 2 errors, both GND vias too close to the SDA track (0.1651 and 0.1592 mm, under JLCPCB's 0.2 mm via-to-track rule). Not called routed.
