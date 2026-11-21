"""The live build view's server.  OWNER: AGENT (task T-02, docs/proposals/T-2-visual-beginner-front-door.md).

Contract
--------
    build_status(run_dir, *, pid) -> dict
    create_build_app(run_dir, *, pid=None) -> fastapi.FastAPI
    serve_build(run_dir, *, pid=None, port=0, open_browser=True) -> None

    GET /api/build              started, finished, status, title, best_attempt, and per attempt:
                                number, compiled, compile_tries, problems, warnings, has_circuit
    GET /api/build/circuit/{n}  attempt n's circuit.json
    GET /api/build/kicad/{n}/{view}   attempt n drawn by KiCad itself (the human: every view from KiCad):
                                pcb        kicad-cli pcb export svg of board.kicad_pcb (copper, silkscreen, outline)
                                schematic  kicad-cli sch export svg of reflow's KiCad schematic of the attempt
                                           (reflow.schematic.write_schematic; 422 when it refuses to draw a part)
                                3d         kicad-cli pcb render of board.kicad_pcb, a PNG
                                404 without a board or for another view, 503 without KiCad
    GET /build                  the web UI (the same bundle as learn mode, which opens its build page)
    GET /                       redirects to /build

Shows a design run while it happens. The run folder is read fresh on every
request; nothing is cached, invented or animated that the run didn't write.
`pid` is the design process: while it's alive the run isn't finished, and the
status run.json carries is a placeholder, so it's sent as "". With no pid (a
finished run opened later), the run is finished.

Must never
----------
- name a problem (rule id, message, part): spot-the-bug belongs to learn mode,
- write anything into the run folder (KiCad renders a copy of the board in a temporary folder),
- listen anywhere but 127.0.0.1, or let the page talk to anything but this server.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import threading
import webbrowser
from pathlib import Path

from reflow.cli import find_kicad_cli
from reflow.contracts import RunResult, from_dict
from reflow.schematic import SchematicError, _rules_path, symbols_from_rules, write_schematic
from reflow.learn.server import CSP, HOST, STATIC


def build_status(run_dir, *, pid) -> dict:
    run_dir = Path(run_dir)
    finished = pid is None or not _alive(pid)
    status = {"started": False, "finished": finished, "status": "", "title": "", "best_attempt": 0,
              "attempts": []}
    path = run_dir / "run.json"
    if not path.is_file():
        return status if pid is not None else {**status, "finished": True}
    try:
        run = from_dict(RunResult, json.loads(path.read_text(encoding="utf-8")))
    except (ValueError, OSError):                 # caught mid-rewrite: the next poll gets it
        return {**status, "started": True}
    spec = run_dir / "spec.json"
    try:
        title = json.loads(spec.read_text(encoding="utf-8")).get("title", "") if spec.is_file() else ""
    except (ValueError, OSError):
        title = ""
    return {
        "started": True,
        "finished": finished,
        "status": run.status if finished else "",
        "title": title,
        "best_attempt": run.best_attempt if finished else 0,
        "attempts": [
            {
                "number": a.attempt,
                "compiled": a.compiled,
                "compile_tries": a.compile_tries,
                "problems": a.errors,
                "warnings": a.warnings,
                "has_circuit": _circuit(run_dir, a.attempt).is_file(),
                "has_kicad_pcb": _kicad_pcb(run_dir, a.attempt).is_file(),
            }
            for a in run.attempts
        ],
    }


def create_build_app(run_dir, *, pid=None):
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
    from fastapi.staticfiles import StaticFiles

    run_dir = Path(run_dir)
    app = FastAPI(title="reflow build", docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def same_origin_only(request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/api/build")
    def status() -> dict:
        return build_status(run_dir, pid=pid)

    @app.get("/api/build/circuit/{number}")
    def circuit(number: int):
        path = _circuit(run_dir, number)
        if not path.is_file():
            raise HTTPException(404, f"attempt {number} has no board yet")
        return json.loads(path.read_text(encoding="utf-8"))

    renders = Path(tempfile.mkdtemp(prefix="reflow-watch-"))

    @app.get("/api/build/kicad/{number}/{view}")
    def kicad(number: int, view: str):
        if view not in _VIEWS:
            raise HTTPException(404, f"no {view} view; KiCad draws pcb, schematic and 3d")
        pcb = _kicad_pcb(run_dir, number)
        if not pcb.is_file():
            raise HTTPException(404, f"attempt {number} has no KiCad board yet")
        cli = find_kicad_cli()
        if cli is None:
            raise HTTPException(503, "KiCad isn't installed (no kicad-cli), so there's nothing to draw it with")
        media, suffix = _VIEWS[view]
        out = renders / f"{number:02d}-{view}-{pcb.stat().st_mtime_ns}{suffix}"
        if not out.is_file():
            _draw(cli, run_dir, number, view, out)
        return FileResponse(out, media_type=media)

    if (STATIC / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")

    @app.get("/build", response_class=HTMLResponse)
    def page():
        index = STATIC / "index.html"
        if not index.is_file():
            return HTMLResponse("<!doctype html><title>reflow build</title>"
                                "<p>The web UI isn't built. Run <code>npm run build</code> in web/.</p>")
        return FileResponse(index)

    @app.get("/")
    def home():
        return RedirectResponse("/build")

    return app


def serve_build(run_dir, *, pid=None, port: int = 0, open_browser: bool = True) -> None:
    import socket

    import uvicorn

    app = create_build_app(run_dir, pid=pid)
    if port == 0:
        with socket.socket() as probe:
            probe.bind((HOST, 0))
            port = probe.getsockname()[1]
    url = f"http://{HOST}:{port}/build"
    print(f"reflow watch: {url}  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=HOST, port=port, log_level="warning")


def _circuit(run_dir: Path, number: int) -> Path:
    return run_dir / "attempts" / f"{number:02d}" / "build" / "circuit.json"


_VIEWS = {"pcb": ("image/svg+xml", ".svg"), "schematic": ("image/svg+xml", ".svg"), "3d": ("image/png", ".png")}


def _draw(cli: str, run_dir: Path, number: int, view: str, out: Path) -> None:
    """Have KiCad draw one view of attempt `number` into `out`, working on copies beside it."""
    from fastapi import HTTPException

    build = run_dir / "attempts" / f"{number:02d}" / "build"
    work = out.with_suffix("")
    work.mkdir(exist_ok=True)
    board = work / "board.kicad_pcb"
    shutil.copyfile(build / "board.kicad_pcb", board)
    if view == "pcb":
        argv = [cli, "pcb", "export", "svg", "--mode-single", "--layers", "F.Cu,B.Cu,F.Silkscreen,Edge.Cuts",
                "--page-size-mode", "2", "--exclude-drawing-sheet", "--drill-shape-opt", "2",
                "-o", str(out), str(board)]
    elif view == "3d":
        argv = [cli, "pcb", "render", "--side", "top", "--rotate", "-35,0,25", "--perspective", "--quality", "basic",
                "-w", "1400", "-h", "900", "--background", "opaque", "-o", str(out), str(board)]
    else:
        spec = json.loads((run_dir / "spec.json").read_text(encoding="utf-8")) if (run_dir / "spec.json").is_file() else {}
        try:
            rules = _rules_path(run_dir, spec.get("rules_file", ""))
            symbols = symbols_from_rules(rules) if rules else {}
            project = build / "board.kicad_pro"
            sch = write_schematic(build / "circuit.json", work, symbols=symbols,
                                  project=project if project.is_file() else None)
        except SchematicError as exc:
            raise HTTPException(422, f"reflow won't draw this schematic: {exc}") from exc
        argv = [cli, "sch", "export", "svg", "--exclude-drawing-sheet", "-o", str(work), str(sch)]
    done = subprocess.run(argv, capture_output=True, text=True, timeout=120, check=False)
    if view == "schematic" and done.returncode == 0:
        made = sorted(work.glob("*.svg"))
        if made:
            shutil.move(str(made[0]), out)
    if done.returncode != 0 or not out.is_file():
        tail = " ".join((done.stderr or done.stdout).split()[-30:])
        raise HTTPException(502, f"KiCad couldn't draw the {view} of attempt {number}: {tail}")


def _kicad_pcb(run_dir: Path, number: int) -> Path:
    return run_dir / "attempts" / f"{number:02d}" / "build" / "board.kicad_pcb"


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:                       # someone else's process: it exists
        return True
    try:                                          # our own child that exited but wasn't reaped
        done, _ = os.waitpid(pid, os.WNOHANG)
        return done == 0
    except ChildProcessError:
        return True
