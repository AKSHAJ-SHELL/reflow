# prompts/: LLM prompts as files

Planned files (H-08, AGENT drafts → HUMAN approves): `planner.md` (request → `Spec` draft + `Plan`), `codegen.md` (→ full `index.circuit.tsx`), `fix.md` (template rendering `RetryFeedback` + current code). `tui-agent.md` (T-01): the system prompt for the agent beside the user in `reflow tui`.

**Contract:** loaded at runtime by the harness; placeholders in `{braces}` filled by the HUMAN-owned context builder. Static parts (tscircuit syntax notes, output rules, the part-number rule) are kept identical across calls so provider prompt caching applies.

**Must never:** contain model ids, API keys or provider-specific code; instruct the model to choose part numbers; include `why` text in fix prompts.
