"""V-22: project rules reach the codegen and fix prompts (DECISIONS V-2, V-2a).

One line per rule and one per [[part]]; `why` and `source` never go to the
model. `test_codegen_prompt_carries_the_rules` stays red until loop.py fills
{project_rules} (docs/proposals/V-22-loop-HUMAN.patch, for the human).
"""
import json
import shutil
from pathlib import Path

import pytest

import reflow.cli as cli
from reflow.contracts import CompileResult, Plan, ResolvedParts, Spec, VerifyReport, from_dict
from reflow.harness.loop import run_design
from reflow.llm import Completion
from reflow.project_rules import RulesFileError, load_rules, render_rules, rules_prompt_block

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "docs" / "examples"
RULES = ROOT / "docs" / "proposals" / "examples" / "rules.toml"
KICAD = ROOT / "tests" / "data" / "pinmaps" / "kicad"


def _spec(**changes) -> Spec:
    data = json.loads((EXAMPLES / "spec.json").read_text(encoding="utf-8"))
    data.update(changes)
    return from_dict(Spec, data)


def _plan() -> Plan:
    return from_dict(Plan, json.loads((EXAMPLES / "plan.json").read_text(encoding="utf-8")))


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------

def test_one_line_per_rule_and_part_without_why_or_source():
    rules = load_rules(RULES)
    text = render_rules(rules, _plan())
    lines = text.splitlines()
    assert "U1 is the MCP9808 (plan part p1). Give it reference U1." in lines
    assert "U1.VDD: capacitor to GND, 100nF..1uF" in lines
    assert "U1.SDA: pull-up resistor to V3_3, 4.7k" in lines
    assert "U1.A0: wire directly to GND" in lines
    assert "U1.ALERT: leave unconnected" in lines
    assert len(lines) == len(rules.rule) + len(rules.part)
    for rule in rules.rule:
        assert rule.why not in text and rule.source not in text


def test_every_need_has_wording():
    from reflow.contracts import RULE_NEEDS, ProjectRule, ProjectRules
    rules = ProjectRules(rule=[ProjectRule(on=f"U1.P{i}", need=need, source="s", why="w",
                                           to="GND" if need in {"cap", "pullup", "pulldown", "tie"} else "")
                               for i, need in enumerate(sorted(RULE_NEEDS))])
    lines = render_rules(rules, None).splitlines()
    assert len(lines) == len(RULE_NEEDS)
    assert all(": " in line and line.split(": ", 1)[1] for line in lines)


def test_a_part_with_no_matching_plan_part_is_still_named():
    text = render_rules(load_rules(RULES), Plan(blocks=[], parts=[], nets=[]))
    assert "U1 is the MCP9808. Give it reference U1." in text.splitlines()


def test_no_rules_file_is_none():
    assert rules_prompt_block(_spec(rules_file=""), _plan()) == "none"


def test_a_rules_file_is_read_and_rendered(monkeypatch):
    monkeypatch.setenv("REFLOW_KICAD_SYMBOL_DIR", str(KICAD))  # the [[part]] symbol's pin table is rendered too
    block = rules_prompt_block(_spec(rules_file=str(RULES)), _plan())
    assert "U1.VDD: capacitor to GND, 100nF..1uF" in block


def test_a_missing_rules_file_is_loud(tmp_path):
    with pytest.raises(RulesFileError):
        rules_prompt_block(_spec(rules_file=str(tmp_path / "nope.toml")), _plan())


# ---------------------------------------------------------------------------
# the prompt template and the loop
# ---------------------------------------------------------------------------

def test_codegen_template_has_a_project_rules_section():
    text = (ROOT / "prompts" / "codegen.md").read_text(encoding="utf-8")
    assert "{project_rules}" in text
    assert "reference" in text.split("{project_rules}")[0].rsplit("##", 1)[-1].lower()


class _Recorder:
    def __init__(self):
        self.prompts = []

    def complete(self, system, prompt, *, max_tokens=4096):
        self.prompts.append(prompt)
        return Completion(text="```tsx\nexport default () => <board />\n```", model="fake/rules",
                          input_tokens=1, output_tokens=1)


def test_codegen_prompt_carries_the_rules(tmp_path):
    """Goes green once loop.py fills {project_rules} (V-22-loop-HUMAN.patch)."""
    model = _Recorder()
    run_design(
        _spec(confirmed=True, rules_file=str(RULES)), _plan(), ResolvedParts([], []),
        model=model,
        compiler=lambda tsx, workdir: CompileResult(True, [], "", "", "", "c.json"),
        verifier=lambda path, parts, spec: VerifyReport("c.json", 0, 0, 0, 0, []),
        run_dir=tmp_path / "run",
    )
    prompt = model.prompts[0]
    assert "{project_rules}" not in prompt
    assert "U1.VDD: capacitor to GND, 100nF..1uF" in prompt
    assert "U1 is the MCP9808 (plan part p1). Give it reference U1." in prompt
    assert "Recommended decoupling" not in prompt and "DS20005095B" not in prompt


# ---------------------------------------------------------------------------
# reflow design checks the rules file before anything runs
# ---------------------------------------------------------------------------

def _design_folder(tmp_path: Path, rules_text: str | None, rules_file: str = "rules.toml") -> Path:
    spec = json.loads((EXAMPLES / "spec.json").read_text(encoding="utf-8"))
    spec["rules_file"] = rules_file
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
    shutil.copy(EXAMPLES / "plan.json", tmp_path / "plan.json")
    if rules_text is not None:
        (tmp_path / "rules.toml").write_text(rules_text, encoding="utf-8")
    return tmp_path


def _design(folder: Path, seen: list) -> int:
    def codegen(spec, plan):
        seen.append(spec)
    return cli.main(["design", "--spec", str(folder / "spec.json"), "--plan", str(folder / "plan.json")],
                    codegen=codegen)


def test_design_resolves_the_rules_file_next_to_the_spec(tmp_path, monkeypatch):
    folder = _design_folder(tmp_path / "board", RULES.read_text(encoding="utf-8"))
    monkeypatch.chdir(tmp_path)
    seen = []
    assert _design(folder, seen) == 0
    assert Path(seen[0].rules_file) == (folder / "rules.toml").resolve()


@pytest.mark.parametrize("rules_text, fragment", [
    (None, "rules.toml"),
    ("[[rule]]\non = \"U1.VDD\"\nneed = \"cap\"\nto = \"GND\"\nsource = \"s\"\n", "why"),
    (RULES.read_text(encoding="utf-8").replace('mpn    = "MCP9808"', 'mpn    = "LM75"'), "LM75"),
])
def test_design_refuses_a_bad_rules_file(tmp_path, capsys, rules_text, fragment):
    seen = []
    assert _design(_design_folder(tmp_path, rules_text), seen) == 2
    assert seen == []
    assert fragment in capsys.readouterr().err


def test_design_without_a_rules_file_is_unchanged(tmp_path):
    seen = []
    assert _design(_design_folder(tmp_path, None, rules_file=""), seen) == 0
    assert seen[0].rules_file == ""


# ---------------------------------------------------------------------------
# reflow rules check uses [[part]] (V-2a)
# ---------------------------------------------------------------------------

def test_rules_check_takes_pin_maps_from_the_part_table(monkeypatch, capsys):
    monkeypatch.setenv("REFLOW_KICAD_SYMBOL_DIR", str(KICAD))
    assert cli.main(["rules", "check", str(RULES)]) == 0
    out = capsys.readouterr().out
    assert "0 errors" in out and "U1.GND" in out and "no pin map" not in out


def test_rules_check_warns_about_a_reference_missing_from_the_part_table(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("REFLOW_KICAD_SYMBOL_DIR", str(KICAD))
    text = RULES.read_text(encoding="utf-8") + '\n[[rule]]\non = "U2.VDD"\nneed = "cap"\nto = "GND"\nsource = "s"\nwhy = "w"\n'
    path = tmp_path / "rules.toml"
    path.write_text(text, encoding="utf-8")
    assert cli.main(["rules", "check", str(path)]) == 0
    assert "U2" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# pin tables: each [[part]]'s trusted pin map goes into the codegen prompt
# ---------------------------------------------------------------------------
# A real run (evals 20261022T193720Z) guessed the AT24C02 and PCF8574 pinouts and
# never got them right in 3 attempts of per-pin fix hints. The pin map V-12 checks
# against is known before codegen, so the model gets it up front.

MCP9808_LABELS = ('U1 pinLabels, from the KiCad symbol Sensor_Temperature:MCP9808_MSOP: '
                  'pinLabels={{ pin1: "SDA", pin2: "SCL", pin3: "Alert", pin4: "GND", '
                  'pin5: "A2", pin6: "A1", pin7: "A0", pin8: "VDD" }}')


def test_each_part_gets_its_pin_table_right_after_its_reference_line():
    from reflow.parts.pinmap import from_kicad_symbol

    pin_map = from_kicad_symbol("Sensor_Temperature:MCP9808_MSOP", symbols_dir=KICAD)
    lines = render_rules(load_rules(RULES), _plan(), {"U1": pin_map}).splitlines()
    assert lines[0].startswith("U1 is the MCP9808")
    assert lines[1] == MCP9808_LABELS
    assert sum(line.startswith("U1 pinLabels") for line in lines) == 1


def test_pins_are_in_physical_order():
    from reflow.contracts import CardPin, Citation
    from reflow.parts.pinmap import PinMap

    pins = [CardPin(n, f"P{n}", "io") for n in ("10", "2", "1", "16", "9")]
    pin_map = PinMap(part="X", package="SOIC-16", pins=pins, source=Citation("test", "test"))
    text = render_rules(load_rules(RULES), None, {"U1": pin_map})
    assert 'pinLabels={{ pin1: "P1", pin2: "P2", pin9: "P9", pin10: "P10", pin16: "P16" }}' in text


def test_rules_prompt_block_reads_each_parts_symbol(monkeypatch):
    monkeypatch.setenv("REFLOW_KICAD_SYMBOL_DIR", str(KICAD))
    block = rules_prompt_block(_spec(rules_file=str(RULES)), _plan())
    assert MCP9808_LABELS in block.splitlines()


def test_a_symbol_that_cant_be_read_is_loud(tmp_path, monkeypatch):
    from reflow.parts.pinmap import PinMapError

    monkeypatch.setenv("REFLOW_KICAD_SYMBOL_DIR", str(KICAD))
    bad = tmp_path / "rules.toml"
    bad.write_text('rule = []\n\n[[part]]\nref = "U1"\nmpn = "MCP9808"\nsymbol = "Nope:Nothing"\n', encoding="utf-8")
    with pytest.raises(PinMapError):
        rules_prompt_block(_spec(rules_file=str(bad)), _plan())


def test_the_codegen_prompt_carries_the_pin_table(monkeypatch):
    """What the loop sends: loop.py fills {project_rules} from rules_prompt_block."""
    from reflow.harness.loop import _codegen_text

    monkeypatch.setenv("REFLOW_KICAD_SYMBOL_DIR", str(KICAD))
    text = _codegen_text(_spec(rules_file=str(RULES)), _plan(), ResolvedParts(resolved=[], unresolved=[]))
    assert MCP9808_LABELS in text.splitlines()
    assert "copy that line exactly" in text
