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
- 2026-10-20 · D-6 / P-03 · jlcsearch stock data and free-text search are broken upstream. Proposed: jlcparts SQLite snapshot (~205 MB). Needs a DECISIONS.md amendment and the human's OK to download.

---

## 2026-10-07 → 2026-10-17 · human · (history, summarized from NOTES.md and git log)
Did: toolchain round trip (KiCad → DSN → freerouting → SES → KiCad); switched substrate atopile → tscircuit; netlist loader + generic fixture tests; rules decoupling.series, i2c.missing_pullup/duplicate_pullup, address.floating; `reflow check` CLI; real AVBotz board fixtures (clean + original series-cap bug); renamed OpenFlux → reflow.
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
Tests: failed first (module missing), then 17 passed, including the AVBotz KiCad 10 board vs its own schematic netlist via kicad-cli (fixture read only). Three in-process sabotages (read the net number instead of the name; drop the conflict check; drop the fp_text fallback) → red each time. `pytest -q` → 7 failed, 280 passed: the same 7 known failures, none new.
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
