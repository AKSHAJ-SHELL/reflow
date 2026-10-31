# V-2a · rules.toml says which part each reference is

Status: **ACCEPTED** 2026-10-21 by the human (proposed by agent, Claude). Amends V-2. Binding text: `DECISIONS.md`. The contract patch was applied in the commit that accepted it.

## Problem

A rule says `on = "U1.VDD"`, but nothing says which part U1 is:
- the code generator picks its own reference designators;
- `reflow rules check` only knows because the user passes `--symbol U1=…`.

On a board with two ICs, the model can't tell which chip a rule is about, and the verifier can't either.

## Decision asked

`rules.toml` gains a `[[part]]` table:

```toml
[[part]]
ref    = "U1"                                 # the reference the rules use
mpn    = "MCP9808"                            # a part the user named (Spec.named_parts)
symbol = "Sensor_Temperature:MCP9808_MSOP"    # optional: KiCad symbol for its pin map
```

- **Contract:** new `RulePart{ref, mpn, symbol}`; `ProjectRules.part: list[RulePart]`, defaulting to `[]`, so existing rules files still parse. No other field changes. Applied in the commit that accepted V-2a.
- **Codegen (V-22):** told "U1 is the MCP9808 (plan part p1); give it reference U1". The plan part is found by matching `mpn` to `PartRequest.mpn`.
- **`reflow rules check`:** builds each part's pin map from `symbol` (KiCad), else from `mpn` (vendor pin data). `--symbol`/`--mpn` still override.
- **Only named parts get references.** `mpn` must be a `Spec.named_parts` string. That keeps the "AI never picks a part number" rule: the table names parts the user typed, and passives on the other side of a rule (the cap, the pull-up) don't need references.

## Checked

The patch applied on `378ae20` in a scratch worktree:
- `test_contracts`, `test_project_rules`, `test_prompts`, `test_evals` and `test_repo_hygiene` → 108 passed;
- an unknown key inside a `[[part]]` in the example → contract tests red.

## Then (V-22, after acceptance)

1. `render_rules(rules) -> str`: one line per rule plus one line per part, never `why` or `source`.
2. A `Project rules` section with a `{project_rules}` placeholder in `prompts/codegen.md` (draft, for your review).
3. `docs/proposals/V-22-loop-HUMAN.patch`: `_codegen_text` in `loop.py` fills `{project_rules}`, for you to apply. Until then one test stays red.
