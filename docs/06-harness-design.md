# 06 · Harness design

The harness is the loop that turns a confirmed spec into a verifier-clean board. Its core is **HUMAN-owned**: the loop, retry termination, best-attempt selection and the Violation → feedback conversion. Agents build the plumbing around it (model adapters, compile wrapper, run-folder I/O, CLI).

Status: **design stage. Nothing here is built.** Open decisions are marked **[HUMAN]** with options, not answers.

## Shape

```
design(request)
  spec   = checkpoint(draft_spec(request))           # human confirms
  plan   = planner(spec)                              # LLM
  parts  = resolve(plan.parts, spec.named_parts)      # deterministic; unresolved -> stop
  feedback = None
  for attempt in 1..3:                                # design attempts
      for compile_try in 1..COMPILE_CAP:              # compile retries don't use attempts
          code   = codegen(spec, plan, parts, feedback, last_code)
          result = compile_board(code.tsx)
          if result.ok: break
          feedback = to_feedback(result)              # kind="compile"
      else: -> status failed_compile
      report = verify(result.kicad_sch, parts, spec)
      save(attempt, code, result, report)             # run.json rewritten every step
      if report.errors == 0: -> status passed
      if should_stop_early(history): -> stop          # [HUMAN] Q5
      feedback = to_feedback(report)                  # kind="verify"  [HUMAN] conversion
  best = pick_best(attempts)                          # [HUMAN] Q3
```

The pattern is the "evaluator-optimizer" loop (one model generates, a checker evaluates and feeds back), with a **deterministic** evaluator instead of a second LLM. References: Anthropic, "Building effective agents"; mini-swe-agent's ~100-line loop; AlphaCodium's generate → test → fix flow (pattern only: AlphaCodium is AGPL, don't copy code).

## Context efficiency (the core requirement)

**Rule 1: build a fresh prompt every call** from the run folder. No growing chat history. (mini-swe-agent keeps a linear history; reflow deliberately doesn't.)

**Rule 2: static vs dynamic.** Everything identical across calls goes in a fixed system prompt (`prompts/*.md`) so provider prompt caching applies.

**Rule 3: send only what the next step needs.**

| Piece | Sent? | Est. tokens (unverified estimates) | Changes per attempt? |
|---|---|---|---|
| System prompt: tscircuit syntax notes, output format, part-number rule | yes, cached | 2,000–4,000 | no |
| Spec (as compact text) | yes | 150–300 | no |
| Plan (blocks + nets) | yes | 200–500 | no |
| Resolved parts table (ref, value, package, LCSC, footprint) | yes | 200–600 | no |
| Current `index.circuit.tsx` (whole file; v1 boards are 100–300 lines) | yes | 1,500–4,000 | yes |
| Violations: `rule_id, message, fix_hint, refs, nets` (no `why`) | yes | ~80–150 each | yes |
| History: one line per earlier failed attempt | yes | ~20 each | yes |
| Compile errors (first error + few lines) | when compile failed | 100–300 | yes |
| Raw `.kicad_sch` / `.kicad_pcb`, full netlist, datasheets, earlier code versions | **never** | (tens of thousands) | — |

Target: a fix call around **6–10k input tokens**, most of it cached. Measure it (`RunResult.input_tokens`); publish the median and p90.

**Rule 4: trim at the source.** `compile.py` stores only the stderr tail; the converter sends only the first error. Compilers repeat themselves.

## Decisions already made by the author

| Q | Decision (2026-10-17) |
|---|---|
| Q1 Context | The verifier's output is the core of the feedback. (Open: the full list of what else goes in; the table above is the proposed budget.) |
| Q2 Compile vs verify | A compile error does **not** consume a design attempt; only verifier failures do. A syntax slip isn't a design failure. **Gap to close:** a separate compile-retry cap (`COMPILE_CAP`) so a model that never compiles can't loop forever. |

## Open decisions [HUMAN]

**Q3 · Getting worse.** Attempt 1 has 2 errors, attempt 2 has 4, attempt 3 has 3. What does the user get?
- (a) Fewest errors; ties go to the latest.
- (b) Lexicographic score: errors, then warnings, then distinct rule IDs.
- (c) Always the latest compiled attempt, with all attempts' reports shown.

**Q4 · Crash safety.** Where does state live?
- (a) The run folder in [02-architecture](02-architecture.md), `run.json` rewritten after every step; `reflow design --resume <run_id>` continues from the last completed step.
- (b) Same folder, no resume; a crash means rerun, but nothing is lost for debugging.
- (c) A single append-only `events.jsonl` per run, replayed on resume.

**Q5 · Stopping early.** Attempts 1 and 2 fail on the same rule on the same refs.
- (a) Stop: identical feedback twice means the model is stuck; spend nothing more.
- (b) Continue, but escalate attempt 3 (e.g. include the relevant `why`, or switch to a stronger model).
- (c) Always run all 3; simplest, costs more.

**Q6 · Part-number provenance.** The model writes a part number nobody gave it.
- (a) Verifier rule `parts.provenance` (an error like any other), so it rides the normal retry loop.
- (b) Pre-compile scan of the TSX; reject before compiling with a dedicated compile-style message.
- (c) Both: cheap pre-scan, plus the rule as the final gate.

**Also open:** `COMPILE_CAP` value; feedback rendering format (Decision D-3); whether attempt 3 may use a different model.

## Modules and owners

| Piece | File | Owner | Task |
|---|---|---|---|
| Skeleton: dataclasses + signatures | `reflow/harness/` | **HUMAN** | H-01 |
| Context builder + Violation → feedback | `reflow/harness/` | **HUMAN** | H-02 |
| Core loop | `reflow/harness/` | **HUMAN** | H-03 |
| Termination + best attempt | `reflow/harness/` | **HUMAN** | H-04 |
| Run folder read/write, resume | `reflow/harness/runs.py` (planned) | AGENT | H-05 |
| Spec checkpoint + planner call (CLI side) | `reflow/harness/` | AGENT (prompt HUMAN-approved) | H-06 |
| `reflow design` CLI | `reflow/cli.py` | AGENT | H-07 |
| Model adapters | `reflow/llm.py` | AGENT | M-01 |
| Compile wrapper | `reflow/compile.py` | AGENT | K-01, K-02 |
| Prompts | `prompts/*.md` | AGENT draft, **HUMAN approves** | H-08 |

## Recommended stack (research 2026-10-17; final call is Decision D-2)

- **Loop:** hand-rolled, ~100–200 lines.
- **Model I/O:** one `complete(system, prompt)` protocol with 2–3 small adapters (Anthropic SDK, OpenAI SDK, OpenAI-compatible base URL for local models). LiteLLM as an optional fallback adapter, not a core dependency.
- **Schemas:** stdlib dataclasses (`reflow/contracts.py`) now; Pydantic v2 only if JSON-schema generation for native structured outputs becomes necessary.
- **No agent framework** in v1 (LangGraph, PydanticAI, OpenAI Agents SDK, Claude Agent SDK, smolagents all evaluated; each adds abstraction over a ≤ 3-iteration loop).
- **MCP:** out of v1. Flux's public MCP server and the KiCad MCP servers are spec references only.
