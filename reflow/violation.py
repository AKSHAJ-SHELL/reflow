from dataclasses import dataclass, field


@dataclass
class Violation:
    rule_id: str
    severity: str
    message: str
    why: str
    fix_hint: str
    refs: list = field(default_factory=list)
    nets: list = field(default_factory=list)
