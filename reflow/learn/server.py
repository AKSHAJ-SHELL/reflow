"""The local learn server.  OWNER: AGENT (task L-10, DECISIONS L-2).

Contract
--------
    create_app(run_dir, *, vault=None, now=None) -> fastapi.FastAPI
    serve(run_dir, *, port=0, open_browser=True, vault=None) -> None

Serves one run folder to the browser on 127.0.0.1 only. The run folder is the
single source of truth: the server reads it, asks the learn engine
(`reflow.learn.engine`, L-01) what to teach, and writes `learn.json`
(`LearnRecord`) and `signoff.json` (`SignOff`) back into it. The browser
talks only to this server; nothing is sent anywhere else.

    GET  /api/run              spec, plan, parts, run result, attempts with their violations
    GET  /api/circuit/{n}      attempt n's circuit.json (for the schematic and PCB viewers)
    GET  /api/learn/next       the next interaction, without its answer; or done + why;
                               concepts skipped as known, with their recall
    POST /api/learn/unskip     {concept} -> ask a skipped concept anyway
    POST /api/learn/hint       {id} -> the hint; counts as hinted when grading
    POST /api/learn/answer     {id, ref, why} -> try_again + hint, or the outcome with the
                               why, the fix and the right part; learn.json is rewritten
    GET  /api/signoff          whether the run is signed off, and the warnings to acknowledge
    POST /api/signoff          {accepted, overrides} -> SignOff, written with learn.json
    GET  /api/vault/graph      the vault's notes and [[wikilinks]] (L-11)
    POST /api/fix              {base_attempt?, edits} -> FixResult: the user's edits to the AI's draft,
                               compiled with tsci and verified like a run (L-14); 400 for a bad edit
    GET  /api/fixes            the fixes made in this session (a reloaded page gets them back)
    GET  /api/fix/{n}/circuit  fix n's circuit.json
    GET  /api/fix/ai           the AI's own fix (a diff of its final TSX); 403 until the user has tried
    POST /api/sim              {concept, attempt | fix, pcb?} -> SimResult + refs (L-12); a concept with no
                               testbench, or a board the testbench can't represent, says why
    POST /api/route            {attempt | fix} -> RouteResult: what tscircuit routed, checked by our KiCad DRC
    GET  /                     the web UI (reflow/learn/static, built from web/)

Memory (L-11): `vault` (default `reflow.learn.vault.default_vault_dir()`) holds
one fsrs card per concept. A concept recalled above 0.9 is skipped and listed,
and each finished interaction rates its card and writes a mistake note and the
board note. Sign-off updates the board note.

Not yet included: `/api/events` (SSE). In phase 1 the run is finished before
the server starts, so there's nothing to push; simulation (L-12) adds it.

Needs the optional extra: `pip install reflow-pcb[learn]`.

Must never
----------
- listen on anything but 127.0.0.1, or serve a page allowed to reach another origin (CSP),
- send an interaction's answer, why or fix before the user has answered,
- call a model or change any file in the run folder other than learn.json and signoff.json,
- write learning notes anywhere but the vault, or fixes and decks anywhere but the run's learn/,
- show the AI's fix before the user has tried one.
"""
from __future__ import annotations

import json
import threading
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from reflow.contracts import LearnRecord, SignOff, to_dict
from reflow.contracts import FixEdit
from reflow.learn.engine import concept_of, grade, load_run, pick
from reflow.learn.vault import Vault, default_vault_dir
from reflow.signoff import remaining_warnings

HOST = "127.0.0.1"
STATIC = Path(__file__).resolve().parent / "static"
# The page may load and fetch only from this server. The tscircuit viewers carry optional
# CDN imports and part-price lookups; the browser blocks them (DECISIONS L-2: nothing leaves
# the user's machine).
CSP = ("default-src 'self'; connect-src 'self'; script-src 'self' 'wasm-unsafe-eval'; "
       "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; "
       "worker-src 'self' blob:; object-src 'none'; base-uri 'none'; form-action 'self'")


class _Answer(BaseModel):
    id: str
    ref: str
    why: str = ""


class _Hint(BaseModel):
    id: str


class _SignOff(BaseModel):
    accepted: bool
    overrides: list[str] = []


class _Unskip(BaseModel):
    concept: str


class _Edit(BaseModel):
    kind: str
    ref: str = ""
    pin: str = ""
    value: str = ""
    part: str = ""
    a: str = ""
    b: str = ""


class _Fix(BaseModel):
    edits: list[_Edit]
    base_attempt: int | None = None


class _Board(BaseModel):
    attempt: int | None = None
    fix: int | None = None


class _Sim(BaseModel):
    concept: str
    attempt: int | None = None
    fix: int | None = None
    pcb: bool = False
    ic_ref: str = ""


class _Session:
    """What the user has done in this run's learn session."""

    def __init__(self, run_dir: Path, vault: Vault) -> None:
        self.run_dir = run_dir
        self.vault = vault
        self.run = load_run(run_dir)
        concepts = {concept_of(v.rule_id) for a in self.run.attempts if a.verify for v in a.verify.violations}
        self.recall = {c: round(vault.recall(c), 3) for c in sorted(concepts)}
        self.skip = vault.known(concepts)
        self.tries: dict[str, int] = {}
        self.hinted: set[str] = set()
        self.finished: dict[str, object] = {}
        self.mistakes: list[str] = []
        self.fixes: dict[int, object] = {}
        self.draft = next((a.number for a in self.run.attempts if a.compiled and a.verify and a.verify.errors), None)
        self.lock = threading.Lock()
        self.repick()

    def repick(self) -> None:
        self.selection = pick(self.run, skip=self.skip)
        self.by_id = {p.id: p for p in self.selection.interactions}

    def remember(self, item, result) -> None:
        """Rate the concept's card and write the mistake and board notes (L-11)."""
        self.vault.review(item.concept, result.rating, rule_id=item.rule_id, why=item.why)
        note = self.vault.write_mistake(
            board=self.run.spec.title, concept=item.concept, rule_id=item.rule_id, found=item.message,
            answer=result.interaction.user_answer, right_refs=result.answer_refs, correct=result.interaction.correct,
            why=item.why, fix=item.fix_hint,
        )
        self.mistakes.append(note.path)
        self.write_board(signed_off=None)

    def write_board(self, *, signed_off) -> None:
        parts = [f"{p.request_id}: {p.mpn or p.value} ({p.lcsc})" for p in (self.run.parts.resolved if self.run.parts else [])]
        done = [self.by_id[i].concept for i in self.finished if i in self.by_id]
        self.vault.write_board(
            board=self.run.spec.title, request=self.run.spec.request, run_dir=str(self.run_dir.resolve()),
            status=self.run.result.status, parts=parts, concepts=done, mistakes=self.mistakes, signed_off=signed_off,
        )

    def record(self) -> LearnRecord:
        done = [self.finished[p.id] for p in self.selection.interactions if p.id in self.finished]
        return LearnRecord(interactions=done, skipped_concepts=list(self.selection.skipped))

    def write_record(self) -> None:
        _write_json(self.run_dir / "learn.json", to_dict(self.record()))


def create_app(run_dir, *, vault=None, now=None) -> FastAPI:
    session = _Session(Path(run_dir), Vault(vault if vault is not None else default_vault_dir(), now=now))
    app = FastAPI(title="reflow learn", docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def same_origin_only(request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/api/run")
    def run_info() -> dict:
        run = session.run
        return {
            "path": str(run.path),
            "spec": to_dict(run.spec),
            "plan": to_dict(run.plan) if run.plan else None,
            "parts": to_dict(run.parts) if run.parts else None,
            "status": run.result.status,
            "best_attempt": run.best_attempt,
            "attempts": [
                {
                    "number": a.number,
                    "compiled": a.compiled,
                    "has_circuit": a.circuit_json is not None,
                    "errors": a.verify.errors if a.verify else 0,
                    "warnings": a.verify.warnings if a.verify else 0,
                    "violations": [to_dict(v) for v in a.verify.violations] if a.verify else [],
                }
                for a in run.attempts
            ],
        }

    @app.get("/api/circuit/{number}")
    def circuit(number: int):
        attempt = next((a for a in session.run.attempts if a.number == number), None)
        if attempt is None or attempt.circuit_json is None:
            raise HTTPException(404, f"attempt {number} has no circuit.json")
        return json.loads(attempt.circuit_json.read_text(encoding="utf-8"))

    @app.get("/api/learn/next")
    def learn_next() -> dict:
        selection = session.selection
        with session.lock:
            remaining = [p for p in selection.interactions if p.id not in session.finished]
        common = {"skipped": list(selection.skipped)}
        if selection.skipped:
            common["recall"] = {c: session.recall.get(c, 0.0) for c in selection.skipped}
        if not remaining:
            reason = "all done" if selection.interactions else selection.reason
            # The notes name parts and rules, so they come only once nothing is left to answer.
            return {"done": True, "reason": reason, "notes": list(selection.notes), **common}
        item = remaining[0]
        return {
            "done": False,
            "index": selection.interactions.index(item) + 1,
            "total": len(selection.interactions),
            "interaction": {
                "id": item.id, "kind": item.kind, "concept": item.concept, "attempt": item.attempt,
                "prompt": item.prompt, "hint": item.hint,
            },
            **common,
        }

    @app.post("/api/learn/hint")
    def learn_hint(body: _Hint) -> dict:
        item = _open(session, body.id)
        with session.lock:
            session.hinted.add(item.id)
        return {"hint": item.hint}

    @app.post("/api/learn/answer")
    def learn_answer(body: _Answer) -> dict:
        item = _open(session, body.id)
        with session.lock:
            tries = session.tries.get(item.id, 0) + 1
            session.tries[item.id] = tries
            result = grade(item, body.ref, body.why, tries=tries, hinted=item.id in session.hinted)
            if result.outcome == "try_again":
                session.hinted.add(item.id)
                return {"outcome": "try_again", "hint": result.hint}
            session.finished[item.id] = result.interaction
            session.write_record()
            session.remember(item, result)
        return {
            "outcome": result.outcome, "rating": result.rating, "answer_refs": result.answer_refs,
            "why": result.why, "fix_hint": result.fix_hint, "message": result.message,
            "rule_id": item.rule_id, "concept": item.concept,
        }

    @app.post("/api/learn/unskip")
    def learn_unskip(body: _Unskip) -> dict:
        with session.lock:
            session.skip.discard(body.concept)
            session.repick()
        return {"skipped": list(session.selection.skipped)}

    @app.get("/api/vault/graph")
    def vault_graph() -> dict:
        return session.vault.graph()

    @app.post("/api/fix")
    def fix(body: _Fix) -> dict:
        from reflow.learn.fixit import EditError, check_fix

        base = body.base_attempt or session.draft
        if base is None:
            raise HTTPException(409, "there's no failed draft to fix: the AI's first draft passed")
        with session.lock:
            number = len(session.fixes) + 1
            try:
                result = check_fix(session.run, base_attempt=base, number=number,
                                   edits=[FixEdit(**e.model_dump()) for e in body.edits])
            except EditError as exc:
                raise HTTPException(400, str(exc))
            session.fixes[number] = result
        return to_dict(result)

    @app.get("/api/fixes")
    def fixes() -> list:
        return [to_dict(session.fixes[n]) for n in sorted(session.fixes)]

    @app.get("/api/fix/{number}/circuit")
    def fix_circuit(number: int):
        result = session.fixes.get(number)
        if result is None or not result.circuit_json:
            raise HTTPException(404, f"fix {number} has no circuit.json")
        return json.loads(Path(result.circuit_json).read_text(encoding="utf-8"))

    @app.get("/api/fix/ai")
    def ai_fix() -> dict:
        import difflib

        if not session.fixes:
            raise HTTPException(403, "try a fix of your own first")
        best = session.run.best_attempt
        draft = session.run.path / "attempts" / f"{session.draft:02d}" / "index.circuit.tsx"
        final = session.run.path / "attempts" / f"{best:02d}" / "index.circuit.tsx"
        if not best or not draft.is_file() or not final.is_file():
            raise HTTPException(404, "the run has no final board to compare")
        diff = difflib.unified_diff(draft.read_text(encoding="utf-8").splitlines(),
                                    final.read_text(encoding="utf-8").splitlines(),
                                    f"attempt {session.draft}", f"attempt {best}", lineterm="", n=1)
        return {"attempt": best, "diff": list(diff)}

    @app.post("/api/sim")
    def simulate(body: _Sim) -> dict:
        return _simulate(session, body)

    @app.post("/api/route")
    def route_status(body: _Board) -> dict:
        from reflow.route import route_report

        circuit, folder = _board_files(session, body.fix, body.attempt)
        pcb = circuit.parent / "board.kicad_pcb"
        if not pcb.is_file():
            raise HTTPException(404, "this board has no .kicad_pcb in the run folder")
        result = route_report(circuit, pcb, session.run_dir / "learn" / "route" / folder)
        return to_dict(result)

    @app.get("/api/signoff")
    def signoff_state() -> dict:
        return {"signed": (session.run_dir / "signoff.json").is_file(), "warnings": _warnings(session)}

    @app.post("/api/signoff")
    def signoff(body: _SignOff) -> dict:
        signed = SignOff(
            accepted=body.accepted,
            warnings_acknowledged=_warnings(session),
            overrides=[o.strip() for o in body.overrides if o.strip()],
            at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        with session.lock:
            session.write_record()
            _write_json(session.run_dir / "signoff.json", to_dict(signed))
            session.write_board(signed_off=body.accepted)
        return to_dict(signed)

    if (STATIC / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")

    @app.get("/", response_class=HTMLResponse)
    def index():
        page = STATIC / "index.html"
        if not page.is_file():
            return HTMLResponse(
                "<!doctype html><title>reflow learn</title><div id=\"root\"></div>"
                "<p>The web UI isn't built. Run <code>npm run build</code> in web/.</p>"
            )
        return FileResponse(page)

    return app


def serve(run_dir, *, port: int = 0, open_browser: bool = True, vault=None) -> None:
    import socket

    import uvicorn

    app = create_app(run_dir, vault=vault)
    if port == 0:
        with socket.socket() as probe:
            probe.bind((HOST, 0))
            port = probe.getsockname()[1]
    url = f"http://{HOST}:{port}/"
    print(f"reflow learn: {url}  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=HOST, port=port, log_level="warning")


def _simulate(session: _Session, body: _Sim) -> dict:
    from reflow.contracts import SimResult
    from reflow.learn import sim
    from reflow.learn.board_values import decoupling_board, i2c_board, supply_volts
    from reflow.learn.fixit import bound_netlist

    if body.fix is not None:
        fixed = session.fixes.get(body.fix)
        if fixed is None or not fixed.circuit_json:
            raise HTTPException(404, f"fix {body.fix} has no board")
        circuit, variant, folder = Path(fixed.circuit_json), "yours", f"fix-{body.fix:02d}"
    else:
        attempt = next((a for a in session.run.attempts if a.number == body.attempt), None)
        if attempt is None or attempt.circuit_json is None:
            raise HTTPException(404, f"attempt {body.attempt} has no board")
        circuit, folder = attempt.circuit_json, f"attempt-{attempt.number:02d}"
        variant = "as_designed" if attempt.number == session.run.best_attempt else "broken"
    if body.pcb:
        folder += "-pcb"

    def refuse(reason: str) -> dict:
        return {**to_dict(SimResult(concept=body.concept, variant=variant, signals=[], exit_code=-1, deck_path="",
                                    ran=False, notes=[reason])), "refs": []}

    if body.concept not in ("decoupling", "i2c-pullup"):
        return refuse(f"can't simulate {body.concept} yet: there's no validated testbench for it")
    netlist = bound_netlist(session.run, circuit)
    ic = body.ic_ref or next((r for r in sorted(netlist.components) if netlist.components[r].prefix == "U"), "")
    supply = supply_volts(session.run.spec.power) or 3.3
    if body.concept == "decoupling":
        found = decoupling_board(netlist, circuit, ic_ref=ic, supply_v=supply, pcb=body.pcb)
    else:
        found = i2c_board(netlist, ic_ref=ic, line="SDA", supply_v=supply)
    if found.board is None:
        return refuse(f"can't simulate this board: {found.reason}")
    workdir = session.run_dir / "learn" / "sim" / folder
    bench = (sim.decoupling if body.concept == "decoupling" else sim.i2c_pullup)(found.board, workdir, variant=variant)
    if supply_volts(session.run.spec.power) is None:
        bench.assumptions.append("supply 3.3 V (the spec doesn't name a voltage)")
    return {**to_dict(bench.to_contract()), "refs": found.refs}


def _board_files(session: _Session, fix: int | None, attempt: int | None) -> tuple[Path, str]:
    if fix is not None:
        fixed = session.fixes.get(fix)
        if fixed is None or not fixed.circuit_json:
            raise HTTPException(404, f"fix {fix} has no board")
        return Path(fixed.circuit_json), f"fix-{fix:02d}"
    found = next((a for a in session.run.attempts if a.number == attempt), None)
    if found is None or found.circuit_json is None:
        raise HTTPException(404, f"attempt {attempt} has no board")
    return found.circuit_json, f"attempt-{found.number:02d}"


def _open(session: _Session, interaction_id: str):
    item = session.by_id.get(interaction_id)
    if item is None:
        raise HTTPException(404, f"no interaction {interaction_id!r}")
    if interaction_id in session.finished:
        raise HTTPException(409, f"interaction {interaction_id!r} is already answered")
    return item


def _warnings(session: _Session) -> list[str]:
    """The same list `reflow export` checks a sign-off against (reflow.signoff, L-03)."""
    return remaining_warnings(session.run_dir)


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
