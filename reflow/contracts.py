"""Stage-boundary contracts for reflow v1.

Every arrow in the pipeline (docs/02-architecture.md) passes exactly one of these
objects. This file is the single source of truth for docs/04-contracts.md.
tests/test_contracts.py freezes every field name, so a silent schema change fails
loudly.

Changing a contract means, in ONE commit:
  1. a DECISIONS.md entry (proposed by an agent, accepted by the human),
  2. this file,
  3. the frozen field lists in tests/test_contracts.py,
  4. docs/04-contracts.md and the example JSON in docs/examples/.

Stdlib only. No behaviour lives here: no I/O, no model calls, no rule logic.
"""
from __future__ import annotations

import dataclasses
import typing
from dataclasses import dataclass, field

from reflow.violation import Violation

SCHEMA_VERSION = 1

# ----------------------------------------------------------------------------
# Enumerations (plain string sets so JSON stays simple)
# ----------------------------------------------------------------------------
SEVERITIES = {"error", "warning"}
FEEDBACK_KINDS = {"compile", "verify"}
RUN_STATUSES = {"passed", "failed_verify", "failed_compile", "aborted"}
ROUTE_STATUSES = {"routed", "partial", "refused", "failed"}
ROUTERS = {"tscircuit", "freerouting"}
LEARN_KINDS = {"spot_bug", "make_call"}
PIN_KINDS = {
    "power", "ground", "i2c_sda", "i2c_scl", "address", "input", "output",
    "open_drain_out", "io", "nc", "thermal_pad",
}
RULE_NEEDS = {"cap", "pullup", "pulldown", "tie", "open", "connected"}
PART_CATEGORIES = {
    "resistor", "capacitor", "inductor", "led", "diode", "transistor",
    "ic", "regulator", "connector", "crystal", "switch", "other",
}


# ----------------------------------------------------------------------------
# 0. Request -> Spec  (spec checkpoint, human confirms)
# ----------------------------------------------------------------------------
@dataclass
class OpenQuestion:
    id: str                     # "q1"
    question: str               # asked by the planner
    answer: str = ""            # typed by the user at the checkpoint


@dataclass
class Spec:
    request: str                # the user's sentence, verbatim
    title: str
    power: str                  # e.g. "USB-C 5V -> 3.3V LDO"
    interfaces: list[str]       # e.g. ["4-pin header: 3V3, GND, SDA, SCL"]
    constraints: list[str]      # e.g. ["<= 30x20 mm", "2 layers"]
    named_parts: list[str]      # part numbers the USER typed; the only MPNs the model may copy
    open_questions: list[OpenQuestion] = field(default_factory=list)
    confirmed: bool = False     # True only after the user confirms
    rules_file: str = ""        # path to the project's rules.toml (V-2); "" = none


# ----------------------------------------------------------------------------
# 0b. rules.toml -> ProjectRules  (PROJECT RULES, written by the student; DECISIONS V-2)
#     Each rule goes to codegen as a one-line constraint and is checked at verify.
#     `why` and `source` are for people; they never reach the model.
# ----------------------------------------------------------------------------
@dataclass
class ProjectRule:
    on: str                     # "U1.VDD": part reference + datasheet pin name or number
    need: str                   # one of RULE_NEEDS
    source: str                 # "MCP9808 datasheet, 6.1 Layout Considerations, p.35"
    why: str                    # the student's own words
    to: str = ""                # net on the other side (cap, pullup, pulldown, tie)
    value: str = ""             # "100nF" or "100nF..1uF"; "" = any


@dataclass
class RulePart:
    ref: str                    # "U1": the reference the rules use, and codegen must give this part
    mpn: str                    # the named part it is, e.g. "MCP9808" (a Spec.named_parts string)
    symbol: str = ""            # optional KiCad library id for its pin map, "Sensor_Temperature:MCP9808_MSOP"


@dataclass
class ProjectRules:
    rule: list[ProjectRule]     # named `rule` so a [[rule]] TOML file parses as-is
    part: list[RulePart] = field(default_factory=list)   # [[part]]: which part each rule reference is (V-2a)


# ----------------------------------------------------------------------------
# 1. Spec -> Plan  (PLANNER, LLM)
# ----------------------------------------------------------------------------
@dataclass
class PartRequest:
    id: str                     # "p1", stable within a run
    role: str                   # "decoupling cap for U1 VDD"
    category: str               # one of PART_CATEGORIES
    value: str = ""             # "100nF", "4.7k"; "" for ICs/connectors
    package: str = ""           # "0402"; "" = resolver chooses
    tolerance: str = ""         # "1%"
    voltage: str = ""           # rating, e.g. "10V"
    mpn: str = ""               # ONLY if copied from Spec.named_parts, else ""
    notes: str = ""


@dataclass
class Block:
    name: str                   # "power", "sensor", "interface"
    purpose: str
    part_ids: list[str]         # PartRequest.id values


@dataclass
class Plan:
    blocks: list[Block]
    parts: list[PartRequest]
    nets: list[str]             # intended net names, e.g. ["+3V3", "GND", "SDA", "SCL"]


# ----------------------------------------------------------------------------
# 2. Plan.parts -> ResolvedParts  (PART RESOLVER, deterministic)
# ----------------------------------------------------------------------------
@dataclass
class ResolvedPart:
    request_id: str             # PartRequest.id
    lcsc: str                   # "C25744"
    mpn: str
    manufacturer: str
    package: str
    value: str
    stock: int
    basic: bool                 # JLCPCB basic/preferred part
    unit_price_usd: float
    source: str                 # "jlcparts" | "spec" | ...
    fetched_at: str             # ISO-8601 UTC


@dataclass
class Unresolved:
    request_id: str
    reason: str                 # "no in-stock 4.7k resistor in 0201"


@dataclass
class ResolvedParts:
    resolved: list[ResolvedPart]
    unresolved: list[Unresolved]


# ----------------------------------------------------------------------------
# 2b. Part card  (GROUND TRUTH, HUMAN-verified, read by the verifier; DECISIONS V-1, V-2)
#     The verifier takes an IC's pin names and kinds from a trusted pin map, by
#     physical pin number, never from labels in the TSX. Pin maps come from
#     vendor pin data, then the KiCad symbol library; a signed PartCard
#     overrides both. No trusted pin map: the IC fails.
# ----------------------------------------------------------------------------
@dataclass
class Citation:
    doc: str                    # "Microchip DS20005095B"
    locator: str                # "Table 3-1, p.11 (MSOP column)"
    url: str = ""


@dataclass
class CardPin:
    number: str                 # physical pin / pad number, "1"
    name: str                   # datasheet symbol, "VDD"
    kind: str                   # one of PIN_KINDS


@dataclass
class PartCard:
    family: str                 # "MCP9808"
    mpns: list[str]             # orderable MPNs this card covers
    lcsc: list[str]             # LCSC ids for those MPNs, e.g. ["C129490"]
    package: str                # "MSOP-8"
    pins: list[CardPin]
    pin_source: Citation        # where every pin row was checked
    verified_by: str            # the person who checked it; "" = draft, verifier ignores it
    verified_on: str            # ISO-8601 date; "" for a draft


# ----------------------------------------------------------------------------
# 3. (Spec, Plan, ResolvedParts[, RetryFeedback]) -> GeneratedCode  (CODEGEN, LLM)
# ----------------------------------------------------------------------------
@dataclass
class GeneratedCode:
    attempt: int                # 1-based design attempt (compile retries do NOT increment it)
    compile_try: int            # 1-based try within this attempt
    tsx: str                    # the full index.circuit.tsx
    model: str                  # "provider/model-id"
    input_tokens: int
    output_tokens: int


# ----------------------------------------------------------------------------
# 4. GeneratedCode -> CompileResult  (COMPILER: tsci, deterministic)
# ----------------------------------------------------------------------------
@dataclass
class CompileError:
    message: str
    line: int = 0
    column: int = 0
    file: str = "index.circuit.tsx"


@dataclass
class CompileResult:
    ok: bool
    errors: list[CompileError]  # empty when ok
    stderr_tail: str            # last <= 40 lines, already trimmed
    kicad_sch: str = ""         # paths; "" when ok is False
    kicad_pcb: str = ""
    circuit_json: str = ""


# ----------------------------------------------------------------------------
# 5. CompileResult -> VerifyReport  (VERIFIER, deterministic, already built)
#    Field names match `reflow check --json` exactly.
#    Input (DECISIONS V-1): `reflow design` verifies CompileResult.circuit_json,
#    with IC pins taken from PartCards; `reflow check` verifies a KiCad schematic.
#    Both build one Netlist and run the same rules. tscircuit's .kicad_sch
#    export is never verified.
# ----------------------------------------------------------------------------
@dataclass
class VerifyReport:
    schematic: str              # file the netlist came from: "board.kicad_sch" or "circuit.json"
    components: int
    nets: int
    errors: int
    warnings: int
    violations: list[Violation]


# ----------------------------------------------------------------------------
# 6. VerifyReport | CompileResult -> RetryFeedback  (HUMAN-owned conversion)
#    What the model sees on the next try. `why` is deliberately excluded:
#    it is written for people (learn mode), not for the fix.
# ----------------------------------------------------------------------------
@dataclass
class FeedbackViolation:
    rule_id: str
    severity: str
    message: str
    fix_hint: str
    refs: list[str] = field(default_factory=list)
    nets: list[str] = field(default_factory=list)


@dataclass
class RetryFeedback:
    kind: str                   # one of FEEDBACK_KINDS
    attempt: int                # the attempt that just failed
    max_attempts: int           # 3 in v1
    history: list[str]          # one line per earlier failed attempt, oldest first
    violations: list[FeedbackViolation] = field(default_factory=list)  # kind == "verify"
    compile_errors: list[CompileError] = field(default_factory=list)   # kind == "compile"


# ----------------------------------------------------------------------------
# 7. Loop state -> RunResult  (HARNESS, HUMAN-owned loop; persisted as run.json)
# ----------------------------------------------------------------------------
@dataclass
class AttemptRecord:
    attempt: int
    compile_tries: int
    compiled: bool
    errors: int
    warnings: int
    rule_ids: list[str]
    dir: str                    # runs/<run_id>/attempts/01


@dataclass
class RunResult:
    run_id: str                 # "20261024-143012-mcp9808-breakout"
    status: str                 # one of RUN_STATUSES
    attempts: list[AttemptRecord]
    best_attempt: int           # 0 if nothing compiled
    run_dir: str
    input_tokens: int = 0       # totals across the run
    output_tokens: int = 0


# ----------------------------------------------------------------------------
# 8. RunResult -> LearnRecord, SignOff  (LEARN MODE + sign-off, human)
# ----------------------------------------------------------------------------
@dataclass
class LearnInteraction:
    kind: str                   # one of LEARN_KINDS
    concept: str                # "decoupling", "i2c-pullup", "address-strap"
    rule_id: str                # the real violation this came from
    prompt: str
    user_answer: str
    correct: bool
    explanation: str            # the Violation.why, shown after answering


@dataclass
class LearnRecord:
    interactions: list[LearnInteraction]
    skipped_concepts: list[str] = field(default_factory=list)


@dataclass
class SignOff:
    accepted: bool
    warnings_acknowledged: list[str]
    overrides: list[str]
    at: str                     # ISO-8601 UTC


# Learn mode v2 memory (DECISIONS L-2): one card per concept, notes in the user's vault.
VAULT_KINDS = {"concept", "mistake", "board"}


@dataclass
class ConceptCard:
    concept: str                # "decoupling", same names as LearnInteraction.concept
    fsrs: str                   # the scheduler's card as JSON (fsrs 6.3.2 Card.to_dict()); opaque to reflow
    last_reviewed: str = ""     # ISO-8601 UTC; "" = never reviewed
    ratings: list[str] = field(default_factory=list)   # "2026-10-22T12:00:00Z good", oldest first


@dataclass
class VaultNote:
    path: str                   # relative to the vault: "concepts/decoupling.md"
    kind: str                   # one of VAULT_KINDS
    title: str
    links: list[str]            # [[wikilink]] targets without .md: "boards/mcp9808-breakout"


# ----------------------------------------------------------------------------
# 9. kicad_pcb -> RouteResult  (ROUTER, deterministic)
# ----------------------------------------------------------------------------
@dataclass
class DrcSummary:
    errors: int
    warnings: int
    unconnected: int
    report_path: str


@dataclass
class RouteResult:
    status: str                 # one of ROUTE_STATUSES
    router: str                 # one of ROUTERS
    tries: int
    routed_nets: int
    total_nets: int
    unrouted_nets: list[str]
    refused_nets: list[str]     # high-speed / RF nets we refuse to autoroute
    drc: DrcSummary             # from OUR re-run of kicad-cli, never the router's report
    kicad_pcb: str


# ----------------------------------------------------------------------------
# 10. Routed board -> FabPackage  (OUTPUT, deterministic)
# ----------------------------------------------------------------------------
@dataclass
class FabPackage:
    gerbers_dir: str
    drill: str
    pos_csv: str
    bom_csv: str
    design_md: str
    report_json: str
    report_html: str = ""


ALL_CONTRACTS = {
    cls.__name__: cls for cls in (
        OpenQuestion, Spec, ProjectRule, RulePart, ProjectRules, PartRequest, Block, Plan, ResolvedPart, Unresolved,
        ResolvedParts, Citation, CardPin, PartCard, GeneratedCode, CompileError, CompileResult, VerifyReport,
        FeedbackViolation, RetryFeedback, AttemptRecord, RunResult,
        LearnInteraction, LearnRecord, SignOff, ConceptCard, VaultNote, DrcSummary, RouteResult, FabPackage,
    )
}


# ----------------------------------------------------------------------------
# Strict (de)serialisation. Unknown keys and missing required keys both raise.
# ----------------------------------------------------------------------------
class ContractError(ValueError):
    """Data does not match a contract."""


def to_dict(obj) -> dict:
    return dataclasses.asdict(obj)


def from_dict(cls, data: dict):
    if not isinstance(data, dict):
        raise ContractError(f"{cls.__name__}: expected an object, got {type(data).__name__}")
    hints = typing.get_type_hints(cls)
    names = {f.name for f in dataclasses.fields(cls)}
    unknown = set(data) - names
    if unknown:
        raise ContractError(f"{cls.__name__}: unknown field(s) {sorted(unknown)}")
    kwargs = {}
    for f in dataclasses.fields(cls):
        if f.name not in data:
            required = f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING
            if required:
                raise ContractError(f"{cls.__name__}: missing required field '{f.name}'")
            continue
        kwargs[f.name] = _coerce(hints[f.name], data[f.name], f"{cls.__name__}.{f.name}")
    return cls(**kwargs)


def _coerce(hint, value, where):
    origin = typing.get_origin(hint)
    if dataclasses.is_dataclass(hint):
        return from_dict(hint, value)
    if origin is list:
        if not isinstance(value, list):
            raise ContractError(f"{where}: expected a list")
        (item,) = typing.get_args(hint)
        return [_coerce(item, v, f"{where}[]") for v in value]
    if hint is bool:
        if not isinstance(value, bool):
            raise ContractError(f"{where}: expected bool")
        return value
    if hint is int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ContractError(f"{where}: expected int")
        return value
    if hint is float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ContractError(f"{where}: expected number")
        return float(value)
    if hint is str:
        if not isinstance(value, str):
            raise ContractError(f"{where}: expected string")
        return value
    return value
