"""Contract tests: fail loudly if any stage-boundary schema changes.

Pure Python. No KiCad, no network, no model calls.

If one of these fails because you changed a contract ON PURPOSE:
  1. write the change in DECISIONS.md (human accepts it),
  2. update FROZEN below, reflow/contracts.py, docs/04-contracts.md and
     docs/examples/*.json in the same commit.
Never "fix" a failure here by loosening the test.
"""
import dataclasses
import json
from pathlib import Path

import pytest

from reflow import contracts as c
from reflow.violation import Violation

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "docs" / "examples"

FROZEN = {
    "Violation": ("rule_id", "severity", "message", "why", "fix_hint", "refs", "nets"),
    "OpenQuestion": ("id", "question", "answer"),
    "ProjectRule": ("on", "need", "source", "why", "to", "value"),
    "ProjectRules": ("rule",),
    "Spec": ("request", "title", "power", "interfaces", "constraints", "named_parts",
             "open_questions", "confirmed", "rules_file"),
    "PartRequest": ("id", "role", "category", "value", "package", "tolerance", "voltage",
                    "mpn", "notes"),
    "Block": ("name", "purpose", "part_ids"),
    "Plan": ("blocks", "parts", "nets"),
    "ResolvedPart": ("request_id", "lcsc", "mpn", "manufacturer", "package", "value", "stock",
                     "basic", "unit_price_usd", "source", "fetched_at"),
    "Unresolved": ("request_id", "reason"),
    "ResolvedParts": ("resolved", "unresolved"),
    "GeneratedCode": ("attempt", "compile_try", "tsx", "model", "input_tokens", "output_tokens"),
    "CompileError": ("message", "line", "column", "file"),
    "Citation": ("doc", "locator", "url"),
    "CardPin": ("number", "name", "kind"),
    "PartCard": ("family", "mpns", "lcsc", "package", "pins", "pin_source", "verified_by",
                 "verified_on"),
    "CompileResult": ("ok", "errors", "stderr_tail", "kicad_sch", "kicad_pcb", "circuit_json"),
    "VerifyReport": ("schematic", "components", "nets", "errors", "warnings", "violations"),
    "FeedbackViolation": ("rule_id", "severity", "message", "fix_hint", "refs", "nets"),
    "RetryFeedback": ("kind", "attempt", "max_attempts", "history", "violations", "compile_errors"),
    "AttemptRecord": ("attempt", "compile_tries", "compiled", "errors", "warnings", "rule_ids", "dir"),
    "RunResult": ("run_id", "status", "attempts", "best_attempt", "run_dir", "input_tokens",
                  "output_tokens"),
    "LearnInteraction": ("kind", "concept", "rule_id", "prompt", "user_answer", "correct",
                         "explanation"),
    "LearnRecord": ("interactions", "skipped_concepts"),
    "SignOff": ("accepted", "warnings_acknowledged", "overrides", "at"),
    "DrcSummary": ("errors", "warnings", "unconnected", "report_path"),
    "RouteResult": ("status", "router", "tries", "routed_nets", "total_nets", "unrouted_nets",
                    "refused_nets", "drc", "kicad_pcb"),
    "FabPackage": ("gerbers_dir", "drill", "pos_csv", "bom_csv", "design_md", "report_json",
                   "report_html"),
}

EXAMPLE_FILES = {
    "spec.json": c.Spec,
    "project_rules.json": c.ProjectRules,
    "plan.json": c.Plan,
    "resolved_parts.json": c.ResolvedParts,
    "part_card.json": c.PartCard,
    "generated_code.json": c.GeneratedCode,
    "compile_result.json": c.CompileResult,
    "verify_report.json": c.VerifyReport,
    "retry_feedback.json": c.RetryFeedback,
    "run_result.json": c.RunResult,
    "learn_record.json": c.LearnRecord,
    "signoff.json": c.SignOff,
    "route_result.json": c.RouteResult,
    "fab_package.json": c.FabPackage,
}


def names(cls):
    return tuple(f.name for f in dataclasses.fields(cls))


def test_every_contract_is_frozen():
    registered = set(c.ALL_CONTRACTS) | {"Violation"}
    assert registered == set(FROZEN), (
        "contract added or removed without updating FROZEN: "
        f"missing={sorted(registered - set(FROZEN))} stale={sorted(set(FROZEN) - registered)}"
    )


@pytest.mark.parametrize("name", sorted(FROZEN))
def test_field_names_frozen(name):
    cls = Violation if name == "Violation" else c.ALL_CONTRACTS[name]
    assert names(cls) == FROZEN[name], (
        f"CONTRACT CHANGED: {name} fields are {names(cls)}, expected {FROZEN[name]}. "
        "Record it in DECISIONS.md and update docs/04-contracts.md + docs/examples/."
    )


def test_feedback_is_violation_minus_why():
    """The model never gets `why` (that's for people). Everything else must match."""
    expected = tuple(n for n in FROZEN["Violation"] if n != "why")
    assert names(c.FeedbackViolation) == expected


@pytest.mark.parametrize("filename", sorted(EXAMPLE_FILES))
def test_examples_parse_strictly(filename):
    data = json.loads((EXAMPLES / filename).read_text())
    obj = c.from_dict(EXAMPLE_FILES[filename], data)
    # round trip must be lossless
    assert c.to_dict(obj) == c.to_dict(c.from_dict(EXAMPLE_FILES[filename], c.to_dict(obj)))


def test_every_example_file_is_checked():
    on_disk = {p.name for p in EXAMPLES.glob("*.json")}
    assert on_disk == set(EXAMPLE_FILES), f"unchecked or missing examples: {on_disk ^ set(EXAMPLE_FILES)}"


def test_unknown_field_rejected():
    with pytest.raises(c.ContractError):
        c.from_dict(c.DrcSummary, {"errors": 0, "warnings": 0, "unconnected": 0,
                                   "report_path": "x", "surprise": 1})


def test_missing_field_rejected():
    with pytest.raises(c.ContractError):
        c.from_dict(c.DrcSummary, {"errors": 0, "warnings": 0, "unconnected": 0})


def test_wrong_type_rejected():
    with pytest.raises(c.ContractError):
        c.from_dict(c.DrcSummary, {"errors": "0", "warnings": 0, "unconnected": 0,
                                   "report_path": "x"})


def test_enums_in_examples():
    fb = c.from_dict(c.RetryFeedback, json.loads((EXAMPLES / "retry_feedback.json").read_text()))
    assert fb.kind in c.FEEDBACK_KINDS
    run = c.from_dict(c.RunResult, json.loads((EXAMPLES / "run_result.json").read_text()))
    assert run.status in c.RUN_STATUSES
    route = c.from_dict(c.RouteResult, json.loads((EXAMPLES / "route_result.json").read_text()))
    assert route.status in c.ROUTE_STATUSES and route.router in c.ROUTERS
    learn = c.from_dict(c.LearnRecord, json.loads((EXAMPLES / "learn_record.json").read_text()))
    assert all(i.kind in c.LEARN_KINDS for i in learn.interactions)
    plan = c.from_dict(c.Plan, json.loads((EXAMPLES / "plan.json").read_text()))
    assert all(p.category in c.PART_CATEGORIES for p in plan.parts)
    report = c.from_dict(c.VerifyReport, json.loads((EXAMPLES / "verify_report.json").read_text()))
    assert all(v.severity in c.SEVERITIES for v in report.violations)
    card = c.from_dict(c.PartCard, json.loads((EXAMPLES / "part_card.json").read_text()))
    assert all(p.kind in c.PIN_KINDS for p in card.pins)
    rules = c.from_dict(c.ProjectRules, json.loads((EXAMPLES / "project_rules.json").read_text()))
    assert rules.rule and all(r.need in c.RULE_NEEDS for r in rules.rule)


def test_plan_only_copies_user_named_mpns():
    """Contract-level guard for 'the AI never picks a part number'."""
    spec = c.from_dict(c.Spec, json.loads((EXAMPLES / "spec.json").read_text()))
    plan = c.from_dict(c.Plan, json.loads((EXAMPLES / "plan.json").read_text()))
    for p in plan.parts:
        assert p.mpn == "" or p.mpn in spec.named_parts, f"{p.id} has a model-chosen MPN {p.mpn}"


def test_cli_json_matches_verify_report():
    """`reflow check --json` output must parse as a VerifyReport."""
    from reflow.cli import render_json

    class FakeNetlist:
        components = {"C1": None, "U1": None}
        nets = {"+3.3V": [], "GND": []}

    v = Violation("decoupling.series", "error", "m", "w", "f", ["C1", "U1"], ["+3.3V"])
    data = json.loads(render_json(Path("x.kicad_sch"), FakeNetlist(), [v]))
    report = c.from_dict(c.VerifyReport, data)
    assert report.errors == 1 and report.violations[0].rule_id == "decoupling.series"


@pytest.mark.parametrize("module, func", [
    ("reflow.llm", "load_model"),
    # compile_board is implemented (K-01, K-02); tests/test_compile.py covers it.
    # catalog search is implemented (P-01, P-03); tests/test_catalog.py covers it.
    ("reflow.route", "route"),
    ("reflow.export", "export_fab"),
])
def test_agent_stubs_exist_and_are_honest(module, func):
    """Stubs import cleanly and refuse to pretend they work."""
    import importlib
    fn = getattr(importlib.import_module(module), func)
    with pytest.raises(NotImplementedError):
        fn(*([None] * fn.__code__.co_argcount))
