"""H-08 prompt drafts.

The files under prompts/ are drafts. A human must approve them before any
loop loads them. This module checks the draft text only; it does not call a
model and it does not parse a board.
"""
import re
from pathlib import Path

from reflow.contracts import PART_CATEGORIES

ROOT = Path(__file__).resolve().parents[1]
PROMPTS = ROOT / "prompts"

FILES = {
    "planner": PROMPTS / "planner.md",
    "codegen": PROMPTS / "codegen.md",
    "fix": PROMPTS / "fix.md",
}

DRAFT_MARKER = (
    "<!-- draft: human approval required before a loop loads this file -->"
)

# The sentence the model must be told, in each file.
PART_RULE = (
    "Part numbers may be copied only from the resolved-parts table or "
    "Spec.named_parts. mpn stays empty otherwise."
)

PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
DOUBLED_PLACEHOLDER_RE = re.compile(r"\{\{[A-Za-z_][A-Za-z0-9_]*\}\}")

ALLOWED_PLACEHOLDERS = {
    "planner": {"request"},
    "codegen": {"spec", "plan", "resolved_parts"},
    "fix": {
        "attempt",
        "max_attempts",
        "history",
        "rule_id",
        "severity",
        "refs",
        "nets",
        "message",
        "fix_hint",
        "compile_line",
        "compile_message",
        "tsx",
    },
}

# Substrings that must not appear, case-insensitive.
FORBIDDEN_SUBSTRINGS = ("invent a part number", "why")

# Model providers and model ids. jlcpcb is a supplier key on a tscircuit
# component, not a model provider, so it is not in this list.
PROVIDER_OR_MODEL_RE = re.compile(
    r"(?i)\b("
    r"anthropic|openai|chatgpt|claude|gpt-\d|gpt4|gemini|ollama|litellm|"
    r"mistral|llama|grok|deepseek|cohere|sonnet|haiku|opus|openrouter|qwen"
    r")\b"
)

API_KEY_RE = re.compile(
    r"(?i)("
    r"sk-[A-Za-z0-9]|"
    r"api[_ -]?key|"
    r"x-api-key|"
    r"AKIA[0-9A-Z]{8}|"
    r"bearer\s+[A-Za-z0-9]|"
    r"secret[_ -]?key"
    r")"
)

# Imperatives that would let the model pick an MPN. A prohibition is a
# different sentence; these patterns are the granting ones.
AUTHORIZING_MPN_RE = re.compile(
    r"(?i)("
    r"you (may|can|should) (choose|pick|select|suggest|recommend)|"
    r"\b(choose|pick|select) (an?|the) (mpn|part|lcsc)|"
    r"\bsearch_parts\b|"
    r"\blook up (an?|the) (part|mpn|lcsc)|"
    r"\bfrom (your )?knowledge\b|"
    r"\bwhatever (mpn|part)\b|"
    r"\bany (mpn|part number) you\b|"
    r"\bmake up (an?|the) (mpn|part)"
    r")"
)

SPEC_FIELDS = (
    "request", "title", "power", "interfaces", "constraints", "named_parts",
    "open_questions", "confirmed",
)
PART_FIELDS = (
    "id", "role", "category", "value", "package", "tolerance", "voltage",
    "mpn", "notes",
)
BLOCK_FIELDS = ("name", "purpose", "part_ids")
PLAN_FIELDS = ("blocks", "parts", "nets")


def _read(name: str) -> str:
    path = FILES[name]
    assert path.is_file(), f"missing draft {path}"
    return path.read_text(encoding="utf-8")


def test_prompt_files_exist_and_are_drafts():
    for name, path in FILES.items():
        text = _read(name)
        assert text.startswith(DRAFT_MARKER), (
            f"{path.name} must start with the draft marker so a loop does not "
            "treat an unapproved file as loadable"
        )
        assert len(text) > 400, f"{path.name} is too short to be a real draft"


def test_placeholders_use_single_braces():
    for name in FILES:
        text = _read(name)
        assert DOUBLED_PLACEHOLDER_RE.search(text) is None, (
            f"{name}: placeholders are {{name}}, not doubled braces"
        )
        found = set(PLACEHOLDER_RE.findall(text))
        assert found, f"{name}: expected at least one {{placeholder}}"
        assert found == ALLOWED_PLACEHOLDERS[name], (
            f"{name}: placeholders {sorted(found)} != "
            f"{sorted(ALLOWED_PLACEHOLDERS[name])}"
        )


def test_no_model_id_key_provider_or_forbidden_substrings():
    for name in FILES:
        text = _read(name)
        lowered = text.lower()
        for needle in FORBIDDEN_SUBSTRINGS:
            assert needle not in lowered, f"{name} contains {needle!r}"
        assert PROVIDER_OR_MODEL_RE.search(text) is None, (
            f"{name} names a model provider or model id: "
            f"{PROVIDER_OR_MODEL_RE.search(text).group(0)}"
        )
        assert API_KEY_RE.search(text) is None, (
            f"{name} looks like it contains an API key"
        )
        assert ".kicad_sch" not in text and ".kicad_pcb" not in text
        assert "datasheet" not in lowered


def test_part_numbers_are_copy_only():
    for name in FILES:
        text = _read(name)
        assert PART_RULE in text, f"{name} is missing the part-number rule"
        match = AUTHORIZING_MPN_RE.search(text)
        assert match is None, (
            f"{name} lets the model choose an MPN: {match.group(0)!r}"
        )


def test_planner_emits_spec_and_plan_schema():
    text = _read("planner")
    for field in SPEC_FIELDS + PLAN_FIELDS + BLOCK_FIELDS + PART_FIELDS:
        assert field in text, f"planner.md omits contract field {field}"
    for category in sorted(PART_CATEGORIES):
        assert re.search(rf"\b{re.escape(category)}\b", text), (
            f"planner.md omits part category {category}"
        )
    assert "confirmed" in text and "false" in text
    assert "json" in text.lower()
    assert "unknown" in text.lower()


def test_codegen_asks_for_a_whole_tsx_file():
    text = _read("codegen")
    assert "index.circuit.tsx" in text
    assert "export default" in text
    assert "<board" in text
    assert "<trace" in text
    assert "resistor" in text and "capacitor" in text and "chip" in text
    assert "supplierPartNumbers" in text
    assert "manufacturerPartNumber" in text
    lowered = text.lower()
    assert "diff" in lowered
    assert "one tsx" in lowered or "one fenced" in lowered or "single" in lowered


def test_fix_is_the_compact_text_template():
    text = _read("fix")
    required = (
        "{attempt}",
        "{max_attempts}",
        "{history}",
        "{rule_id}",
        "{refs}",
        "{nets}",
        "{message}",
        "{fix_hint}",
        "{compile_line}",
        "{compile_message}",
        "{tsx}",
    )
    for token in required:
        assert token in text, f"fix.md missing {token}"
    assert "compile error line" in text.lower()
    assert "current" in text.lower()
    # Compact order: attempt, then history, then the violation fields,
    # then the compile error line, then the current file.
    positions = [text.index(token) for token in required]
    assert positions == sorted(positions), (
        "fix.md fields are out of compact-template order: "
        + ", ".join(required)
    )
    assert "rule_id" in text and "fix_hint" in text


def test_package_does_not_load_unapproved_prompts():
    """Drafts stay on disk. reflow/ must not name these files until a human approves."""
    for path in (ROOT / "reflow").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for name in ("planner.md", "codegen.md", "fix.md"):
            assert name not in text, f"{path} references prompts/{name}"
