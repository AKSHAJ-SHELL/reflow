"""T-01: the front door's project flow, without the screen.

A fake planner model stands in for Claude, so these check what reflow itself
decides: part numbers come only from what the user typed, the datasheet must be
a PDF, rules.toml is the user's and must check clean, nothing is designed before
the user confirms, and a fix the user types becomes a new, linked run.
"""
import json
import sys
from pathlib import Path

import pytest

from reflow.contracts import Plan, Spec, from_dict
from reflow.llm import Completion
from reflow.tui.project import Project, ProjectError

ROOT = Path(__file__).resolve().parents[1]
SYMBOLS = ROOT / "tests" / "data" / "pinmaps" / "kicad"

SPEC = {
    "request": "IGNORED, reflow keeps the user's own words",
    "title": "MCP9808 breakout",
    "power": "3.3V on the header",
    "interfaces": ["4-pin header: 3V3, GND, SDA, SCL"],
    "constraints": ["2 layers"],
    "named_parts": ["MCP9808", "LM7805"],
    "open_questions": [{"id": "q1", "question": "Which I2C address?", "answer": ""}],
    "confirmed": True,
}
PLAN = {
    "blocks": [{"name": "sensor", "purpose": "sensor", "part_ids": ["p1", "p2"]}],
    "parts": [
        {"id": "p1", "role": "temperature sensor", "category": "ic", "value": "", "package": "",
         "tolerance": "", "voltage": "", "mpn": "MCP9808", "notes": ""},
        {"id": "p2", "role": "decoupling cap", "category": "capacitor", "value": "100nF", "package": "0402",
         "tolerance": "", "voltage": "", "mpn": "", "notes": ""},
    ],
    "nets": ["V3_3", "GND", "SDA", "SCL"],
}


class FakePlanner:
    def __init__(self, spec=SPEC, plan=PLAN):
        self.spec, self.plan, self.prompts = spec, plan, []

    def complete(self, system, prompt, *, max_tokens=None):
        self.prompts.append(prompt)
        text = f"```json\n{json.dumps(self.spec)}\n```\n\n```json\n{json.dumps(self.plan)}\n```"
        return Completion(text=text, model="fake", input_tokens=1, output_tokens=1)


def _started(tmp_path) -> Project:
    project = Project(tmp_path)
    project.start("MCP9808 temperature sensor breakout, I2C, 3.3V", ["MCP9808"])
    return project


def test_start_keeps_the_users_words_and_part_numbers(tmp_path):
    project = _started(tmp_path)
    again = Project(tmp_path)                     # state survives a restart of the TUI
    assert again.state.request == "MCP9808 temperature sensor breakout, I2C, 3.3V"
    assert again.state.part_numbers == ["MCP9808"]
    assert again.stage == "datasheet"


def test_a_part_number_must_be_typed(tmp_path):
    with pytest.raises(ProjectError, match="part number"):
        Project(tmp_path).start("an accelerometer board", [])


def test_the_datasheet_must_be_a_pdf_and_is_copied_into_the_project(tmp_path):
    project = _started(tmp_path)
    fake = tmp_path / "notes.pdf"
    fake.write_text("not a pdf")
    with pytest.raises(ProjectError, match="PDF"):
        project.add_datasheet(fake)
    real = tmp_path / "elsewhere" / "MCP9808 datasheet.pdf"
    real.parent.mkdir()
    real.write_bytes(b"%PDF-1.7\n...")
    copied = project.add_datasheet(real)
    assert copied.parent == tmp_path and copied.read_bytes().startswith(b"%PDF")
    assert Project(tmp_path).state.datasheet == copied.name
    assert project.stage == "plan"


def test_the_plan_takes_part_numbers_only_from_what_the_user_typed(tmp_path):
    project = _started(tmp_path)
    planner = FakePlanner()
    draft = project.draft_plan(planner)
    assert draft.spec.named_parts == ["MCP9808"]  # the model's extra LM7805 is dropped
    assert draft.spec.request == "MCP9808 temperature sensor breakout, I2C, 3.3V"
    assert draft.spec.confirmed is False          # only the user confirms
    assert draft.spec.rules_file == "rules.toml"
    assert [q.question for q in draft.spec.open_questions] == ["Which I2C address?"]
    assert "MCP9808 temperature sensor breakout" in planner.prompts[0]


def test_a_plan_with_a_part_number_the_user_didnt_type_is_refused(tmp_path):
    project = _started(tmp_path)
    plan = json.loads(json.dumps(PLAN))
    plan["parts"][1]["mpn"] = "GRM155R71C104KA88D"
    with pytest.raises(ProjectError, match="GRM155R71C104KA88D"):
        project.draft_plan(FakePlanner(plan=plan))


def test_answers_go_back_to_the_planner_and_are_kept(tmp_path):
    project = _started(tmp_path)
    project.draft_plan(FakePlanner())
    planner = FakePlanner()
    draft = project.draft_plan(planner, answers={"q1": "0x18, all address pins to GND"})
    assert "Which I2C address?" in planner.prompts[0] and "0x18, all address pins to GND" in planner.prompts[0]
    assert draft.spec.open_questions[0].answer == "0x18, all address pins to GND"


def test_accepting_the_plan_writes_spec_and_plan_unconfirmed(tmp_path):
    project = _started(tmp_path)
    project.accept_plan(project.draft_plan(FakePlanner()))
    spec = from_dict(Spec, json.loads((tmp_path / "spec.json").read_text()))
    from_dict(Plan, json.loads((tmp_path / "plan.json").read_text()))
    assert spec.confirmed is False
    assert project.stage == "rules"


def test_the_rules_template_names_the_part_and_leaves_the_rules_to_the_user(tmp_path):
    project = _started(tmp_path)
    path = project.write_rules_template("Sensor_Temperature:MCP9808_MSOP")
    text = path.read_text()
    assert 'mpn    = "MCP9808"' in text and 'symbol = "Sensor_Temperature:MCP9808_MSOP"' in text
    assert "\n[[rule]]" not in text               # rule examples are commented out: the user writes them
    with pytest.raises(ProjectError, match="exists"):
        project.write_rules_template("Sensor_Temperature:MCP9808_MSOP")   # never overwrite the user's file


def test_symbol_candidates_come_from_the_kicad_library(tmp_path, monkeypatch):
    monkeypatch.setenv("REFLOW_KICAD_SYMBOL_DIR", str(SYMBOLS))
    assert "Sensor_Temperature:MCP9808_MSOP" in Project(tmp_path).symbol_candidates("MCP9808T-E/MS")


def test_rules_must_check_clean_before_confirming(tmp_path, monkeypatch):
    monkeypatch.setenv("REFLOW_KICAD_SYMBOL_DIR", str(SYMBOLS))
    project = _started(tmp_path)
    project.accept_plan(project.draft_plan(FakePlanner()))
    with pytest.raises(ProjectError, match="rules.toml"):
        project.confirm()                         # no rules file yet
    project.write_rules_template("Sensor_Temperature:MCP9808_MSOP")
    rules = tmp_path / "rules.toml"
    rules.write_text(rules.read_text() + '\n[[rule]]\non = "U1.NOPE"\nneed = "cap"\nto = "GND"\n'
                     'source = "datasheet p.1"\nwhy = "mine"\n')
    result = project.check_rules()
    assert result.errors
    with pytest.raises(ProjectError, match="error"):
        project.confirm()
    rules.write_text(rules.read_text().replace("U1.NOPE", "U1.VDD"))
    assert not project.check_rules().errors
    project.confirm()
    assert json.loads((tmp_path / "spec.json").read_text())["confirmed"] is True
    assert project.stage == "design"


def test_the_design_command_runs_reflow_design_on_claude_code(tmp_path, monkeypatch):
    monkeypatch.delenv("REFLOW_PROVIDER", raising=False)
    project = _started(tmp_path)
    run_dir = project.next_run_dir()
    argv, env = project.design_command(run_dir)
    assert argv[:4] == [sys.executable, "-m", "reflow", "design"]
    assert argv[argv.index("--spec") + 1] == str(tmp_path / "spec.json")
    assert argv[argv.index("--plan") + 1] == str(tmp_path / "plan.json")
    assert argv[argv.index("--run-dir") + 1] == str(run_dir)
    assert env["REFLOW_PROVIDER"] == "claude-code"
    assert run_dir.parent == tmp_path / "runs" and not run_dir.exists()
    monkeypatch.setenv("REFLOW_PROVIDER", "openrouter")
    assert project.design_command(run_dir)[1]["REFLOW_PROVIDER"] == "openrouter"   # the user's choice wins


def test_a_fix_the_user_types_becomes_a_constraint_for_the_next_run(tmp_path, monkeypatch):
    monkeypatch.setenv("REFLOW_KICAD_SYMBOL_DIR", str(SYMBOLS))
    project = _started(tmp_path)
    project.accept_plan(project.draft_plan(FakePlanner()))
    project.write_rules_template("Sensor_Temperature:MCP9808_MSOP")
    with pytest.raises(ProjectError, match="error"):
        project.confirm()                         # the template alone has no [[rule]]: the rules are the user's
    rules = tmp_path / "rules.toml"
    rules.write_text(rules.read_text() + '\n[[rule]]\non = "U1.VDD"\nneed = "cap"\nto = "GND"\n'
                     'source = "MCP9808 datasheet, 6.1, p.35"\nwhy = "mine"\n')
    project.confirm()
    first = project.next_run_dir()
    project.record_run(first)
    project.add_fix(first, "Move C1 so one pin is on V3_3 and the other on GND.")
    spec = json.loads((tmp_path / "spec.json").read_text())
    assert spec["constraints"][-1] == f"Designer's fix after {first.name}: Move C1 so one pin is on V3_3 and the other on GND."
    assert spec["confirmed"] is True              # the fix is the user's own words
    second = project.next_run_dir()
    assert second != first and second.parent == first.parent
    assert Project(tmp_path).state.fixes == [{"after": first.name, "text": "Move C1 so one pin is on V3_3 and the other on GND."}]
    with pytest.raises(ProjectError, match="empty"):
        project.add_fix(first, "   ")


def test_only_the_plans_chips_get_a_part_entry(tmp_path):
    """A typed shunt resistor is a named part, but not a U: a [[part]] would make codegen call it U2."""
    project = Project(tmp_path)
    project.start("INA226 power monitor with a 10 mOhm shunt", ["INA226AIDGSR", "WSL2512R0100FEA"])
    spec = dict(SPEC, named_parts=["INA226AIDGSR", "WSL2512R0100FEA"], open_questions=[])
    plan = {"blocks": [{"name": "monitor", "purpose": "INA226 and shunt", "part_ids": ["p1", "p2"]}],
            "parts": [{"id": "p1", "role": "power monitor", "category": "ic", "value": "", "package": "",
                       "tolerance": "", "voltage": "", "mpn": "INA226AIDGSR", "notes": ""},
                      {"id": "p2", "role": "current shunt", "category": "resistor", "value": "10m", "package": "2512",
                       "tolerance": "", "voltage": "", "mpn": "WSL2512R0100FEA", "notes": ""}],
            "nets": ["VIN", "VOUT", "GND"]}
    project.accept_plan(project.draft_plan(FakePlanner(spec=spec, plan=plan)))
    text = project.write_rules_template("Sensor_Energy:INA226").read_text()
    assert text.count("[[part]]") == 1
    assert 'mpn    = "INA226AIDGSR"' in text and "WSL2512R0100FEA" not in text.split("# Example")[0]


def test_a_jlc_number_is_not_a_part_number(tmp_path):
    with pytest.raises(ProjectError, match="C49851 is a JLC"):
        Project(tmp_path).start("INA226 power monitor", ["C49851", "VSSOP-10"])


def test_part_problems_names_each_number_the_catalog_doesnt_have(tmp_path):
    from reflow.parts.catalog import CatalogError

    stocked = {"INA226AIDGSR"}

    def search(request):
        return ["row"] if request.mpn in stocked else []

    project = Project(tmp_path)
    problems = project.part_problems(["INA226AIDGSR", "VSSOP-10"], search=search)
    assert len(problems) == 1 and "VSSOP-10" in problems[0] and "parts database" in problems[0]
    assert project.part_problems(["INA226AIDGSR"], search=search) == []

    def no_database(request):
        raise CatalogError("no parts database")

    assert project.part_problems(["anything"], search=no_database) == []   # can't check: don't block


def test_back_goes_one_step_and_unconfirms_the_spec(tmp_path, monkeypatch):
    monkeypatch.setenv("REFLOW_KICAD_SYMBOL_DIR", str(SYMBOLS))
    project = _started(tmp_path)
    fresh = tmp_path / "new"
    fresh.mkdir()
    with pytest.raises(ProjectError, match="first step"):
        Project(fresh).back()
    assert project.back() == "request"
    project.start("MCP9808 temperature sensor breakout, I2C, 3.3V", ["MCP9808"])   # typed again, corrected
    pdf = tmp_path / "d.pdf"
    pdf.write_bytes(b"%PDF-1.7\n")
    project.add_datasheet(pdf)
    project.accept_plan(project.draft_plan(FakePlanner()))
    project.write_rules_template("Sensor_Temperature:MCP9808_MSOP")
    rules = tmp_path / "rules.toml"
    rules.write_text(rules.read_text() + '\n[[rule]]\non = "U1.VDD"\nneed = "cap"\nto = "GND"\n'
                     'source = "MCP9808 datasheet, 6.1, p.35"\nwhy = "mine"\n')
    project.confirm()
    assert project.stage == "design"
    assert project.back() == "rules"
    assert json.loads((tmp_path / "spec.json").read_text())["confirmed"] is False   # change rules, confirm again
    assert Project(tmp_path).stage == "rules"
    assert project.back() == "plan" and project.back() == "datasheet"


def _pdf(path: Path, pages: list[str]) -> Path:
    """A minimal real PDF, one line of Helvetica text per page, so text extraction has something to read."""
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", None, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for text in pages:
        stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
        objs.append(f"<< /Length {len(stream)} >>\nstream\n{stream.decode()}\nendstream")
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {len(objs)} 0 R "
                    "/Resources << /Font << /F1 3 0 R >> >> >>")
        kids.append(f"{len(objs)} 0 R")
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(pages)} >>"
    out, offsets = b"%PDF-1.4\n", []
    for n, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n{body}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(out)
    return path


def test_the_datasheet_gets_a_text_copy_with_page_markers(tmp_path):
    pytest.importorskip("pypdf")
    project = _started(tmp_path / "board")
    pdf = _pdf(tmp_path / "INA226 datasheet.pdf", ["Bypass VS with 0.1 uF", "A0 and A1 set the address"])
    project.add_datasheet(pdf)
    text = (tmp_path / "board" / "INA226 datasheet.txt").read_text()
    assert "=== page 1 ===" in text and "=== page 2 ===" in text
    assert text.index("Bypass VS") < text.index("=== page 2 ===") < text.index("A0 and A1")
    assert Project(tmp_path / "board").state.datasheet_text == "INA226 datasheet.txt"


def test_a_pdf_with_no_text_has_no_text_copy(tmp_path):
    pytest.importorskip("pypdf")
    project = _started(tmp_path / "board")
    project.add_datasheet(_pdf(tmp_path / "scan.pdf", [""]))
    assert not (tmp_path / "board" / "scan.txt").exists()
    assert project.state.datasheet_text == ""     # a scanned PDF: the agent reads the PDF itself


@pytest.mark.parametrize("dropped", [
    "'{p}'", '"{p}"', "{e}", "file://{u}", "  {p}  \n",
])
def test_a_dragged_path_is_understood(tmp_path, dropped):
    from urllib.parse import quote

    from reflow.tui.project import dropped_path

    folder = tmp_path / "My Datasheets"
    folder.mkdir()
    pdf = folder / "INA226 (rev B).pdf"
    pdf.write_bytes(b"%PDF-1.7\n")
    escaped = str(pdf).replace(" ", "\\ ").replace("(", "\\(").replace(")", "\\)")   # how Terminal pastes it
    text = dropped.format(p=pdf, e=escaped, u=quote(str(pdf)))
    assert dropped_path(text) == pdf
    assert dropped_path("just some words") is None


def test_an_empty_upload_keeps_the_datasheet_or_says_what_to_do(tmp_path):
    project = _started(tmp_path)
    with pytest.raises(ProjectError, match="Drag the datasheet PDF"):
        project.add_datasheet("")                 # nothing uploaded yet: not ". isn't a file"
    pdf = tmp_path / "d.pdf"
    pdf.write_bytes(b"%PDF-1.7\n")
    project.add_datasheet(pdf)
    project.back()
    assert project.stage == "datasheet"
    assert project.add_datasheet("   ") == tmp_path / "d.pdf"   # back here after uploading: keep it
    assert project.stage == "plan"


def test_the_planner_is_given_the_typed_part_numbers_to_copy(tmp_path):
    """A request that says "INA226" made the planner write mpn "INA226"; it must see "INA226AIDGSR"."""
    project = Project(tmp_path)
    project.start("INA226 power monitor with a shunt", ["INA226AIDGSR", "25121WF100MT4E"])
    plan = json.loads(json.dumps(PLAN))
    plan["parts"][0]["mpn"] = "INA226AIDGSR"
    planner = FakePlanner(plan=plan)
    project.draft_plan(planner)
    assert "INA226AIDGSR" in planner.prompts[0] and "25121WF100MT4E" in planner.prompts[0]
    assert "exactly" in planner.prompts[0]
