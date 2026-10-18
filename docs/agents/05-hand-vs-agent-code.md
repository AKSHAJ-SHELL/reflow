# 05 · Hand vs agent code

**The test: if this code has a bug, does it crash, or does it produce a plausible wrong answer?**

- **Plausible wrong → HUMAN writes it.** A rule that misses a series cap still prints "no issues." A feedback converter that drops a violation still produces a prompt. A best-attempt picker that picks the wrong attempt still ships a board.
- **Crashes loudly → AGENT may write it.** A bad subprocess call errors out. A wrong API URL raises. A broken argparse prints usage.
- **Parsers and converters → AGENT writes, then round-trip verified.** Plausible-wrong risk, but mechanically testable: parse a known file, assert known values (e.g. `U1.8` is on `Net-(U1-V_{DD})`), re-serialize, compare.

| Area | Owner |
|---|---|
| Every rule in `reflow/rules/` | HUMAN |
| Test fixtures + `expected.toml` | HUMAN |
| Harness core loop | HUMAN |
| Retry termination + best-attempt selection | HUMAN |
| Violation → `RetryFeedback` conversion + context builder | HUMAN |
| Part-resolver validity + ranking | HUMAN |
| Learn-mode selection + grading | HUMAN |
| Prompts | AGENT drafts → HUMAN approves |
| `kicad-cli` calls, DSN/SES I/O, `tsci` wrapper | AGENT |
| Model adapters, catalog/API clients | AGENT |
| CLI, config, logging, CI, packaging, README plumbing | AGENT |
| Netlist / compile-error / DRC-JSON parsers | AGENT, then round-trip verified |
| Contracts (`reflow/contracts.py`) | AGENT drafts, changes only via accepted DECISIONS.md |
