"""Model I/O: one prompt-in, text-out interface for every provider.  OWNER: AGENT (task M-01).

Contract
--------
    complete(system: str, prompt: str, *, max_tokens: int) -> Completion

- `system` is the fixed system prompt (loaded from prompts/*.md, cache-friendly).
- `prompt` is the per-call user message built by the harness context builder (HUMAN).
- Returns the raw text plus token counts. No parsing, no retries, no tool calls here.

Must never
----------
- hardcode a model id or API key (read reflow.toml / env vars),
- add conversation history (the harness builds a fresh prompt every call),
- swallow provider errors (raise ModelError with the provider's message).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class ModelError(RuntimeError):
    """The provider call failed (auth, rate limit, network, bad request)."""


@dataclass
class Completion:
    text: str
    model: str            # "provider/model-id"
    input_tokens: int
    output_tokens: int


class Model(Protocol):
    def complete(self, system: str, prompt: str, *, max_tokens: int = 4096) -> Completion: ...


def load_model(config: dict) -> Model:
    """Build the configured adapter (anthropic | openai | openai-compatible/local).

    Stub: see TASKS.md M-01. Decision 1 in DECISIONS.md picks the default provider.
    """
    raise NotImplementedError("M-01: model adapters not built yet")
