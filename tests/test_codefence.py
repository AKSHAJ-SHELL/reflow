"""Code-fence extractor: exactly one fence, or None. No run status."""
import ast
import inspect
from pathlib import Path

from reflow.codefence import extract_code_fence
from reflow.contracts import RunResult

ROOT = Path(__file__).resolve().parents[1]
FENCE_PATH = ROOT / "reflow" / "codefence.py"

_ONE = (
    "I generated the board.\n\n"
    "```tsx\n"
    "export default () => <board />\n"
    "```\n\n"
    "Hope this helps.\n"
)

_TWO = (
    "Option A:\n"
    "```tsx\n"
    "export const A = 1\n"
    "```\n"
    "Option B:\n"
    "```tsx\n"
    "export const B = 2\n"
    "```\n"
)


def test_signature_and_source_do_not_decide_status_or_parts():
    sig = inspect.signature(extract_code_fence)
    assert list(sig.parameters) == ["text"]
    src = FENCE_PATH.read_text()
    tree = ast.parse(src)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    assert imported <= {"__future__", "re"}
    lowered = src.lower()
    for banned in ("runresult", "status", "mpn", "lcsc"):
        assert banned not in lowered


def test_no_fence_returns_none():
    assert extract_code_fence("just prose, no block") is None
    assert extract_code_fence("") is None
    assert extract_code_fence("use ```inline``` ticks") is None


def test_unclosed_fence_returns_none():
    assert extract_code_fence("```tsx\nexport const x = 1\n") is None


def test_two_fences_return_none():
    assert extract_code_fence(_TWO) is None


def test_prose_around_one_fence_returns_body():
    assert extract_code_fence(_ONE) == "export default () => <board />\n"


def test_fence_without_language_returns_body():
    text = "```\nconst x = 1\n```\n"
    assert extract_code_fence(text) == "const x = 1\n"


def test_body_stays_opaque_text():
    text = "```tsx\nconst id = \"C12345\"\n```\n"
    assert extract_code_fence(text) == "const id = \"C12345\"\n"


def test_extractor_does_not_set_run_status():
    result = RunResult(
        run_id="r",
        status="passed",
        attempts=[],
        best_attempt=0,
        run_dir="runs/r",
    )
    assert extract_code_fence(_ONE) == "export default () => <board />\n"
    assert extract_code_fence("no fence") is None
    assert result.status == "passed"
