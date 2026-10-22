"""The eval runner must not override the configured reply budget (M-03).

Its model wrapper once passed max_tokens=4096 on every call, so a run with
max_tokens = 12000 in reflow.toml was cut off at 4096 anyway (first real
`reflow eval`, 2026-10-21).
"""
from reflow.evals import _Counting
from reflow.llm import Completion


class _Budget:
    def __init__(self):
        self.seen = []

    def complete(self, system, prompt, *, max_tokens=None):
        self.seen.append(max_tokens)
        return Completion(text="x", model="m/1", input_tokens=1, output_tokens=1)


def test_the_wrapper_leaves_the_budget_to_the_model():
    inner = _Budget()
    wrapped = _Counting(inner)
    wrapped.complete("s", "p")
    wrapped.complete("s", "p", max_tokens=2000)
    assert inner.seen == [None, 2000]
    assert wrapped.ids == {"m/1"}
