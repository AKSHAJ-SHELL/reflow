# reflow/harness/: the design loop (core OWNER: HUMAN)

**Does:** spec checkpoint → planner → resolver → codegen → compile → verify → feedback → retry (≤ 3 design attempts; compile retries capped separately) → `RunResult` + run folder. Design: `docs/06-harness-design.md`.

| Piece | Owner |
|---|---|
| Skeleton, context builder, Violation → `RetryFeedback`, core loop, termination, best-attempt selection | **HUMAN** (H-01 … H-04) |
| Run-folder I/O + resume (`runs.py`) | AGENT (H-05) |
| Spec checkpoint / planner call plumbing | AGENT (H-06) |

No code here yet, on purpose: the author writes the skeleton first (H-01) after answering Q3–Q6 (H-00).

**Contract:** consumes and produces only `reflow/contracts.py` types; persists `run.json` after every step.

**Must never:** grow a chat history across calls; send `why`, raw KiCad files or old code versions to the model; loop without a cap; report success without a `VerifyReport` with zero errors.
