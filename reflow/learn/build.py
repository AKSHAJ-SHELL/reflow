"""The live build view's server.  OWNER: AGENT (task T-02, docs/proposals/T-2-visual-beginner-front-door.md).

Contract
--------
    build_status(run_dir, *, pid) -> dict
    create_build_app(run_dir, *, pid=None) -> fastapi.FastAPI
    serve_build(run_dir, *, pid=None, port=0, open_browser=True) -> None

    GET /api/build              started, finished, status, title, best_attempt, and per attempt:
                                number, compiled, compile_tries, problems, warnings, has_circuit
    GET /api/build/circuit/{n}  attempt n's circuit.json (for the PCB, schematic and 3D viewers)
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
- write anything into the run folder,
- listen anywhere but 127.0.0.1, or let the page talk to anything but this server.
"""
from __future__ import annotations

import json
import os
import threading
import webbrowser
from pathlib import Path

from reflow.contracts import RunResult, from_dict
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
