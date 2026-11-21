// The live build view (T-02, docs/proposals/T-2-visual-beginner-front-door.md), served by
// `reflow watch` at /build. It shows a design run as it happens, from the run folder only: each
// attempt and how many problems the verifier found (not which: that's learn mode's job). Every view
// of the board (PCB, schematic, 3D) is drawn by KiCad itself; nothing else draws the board here.
import { useEffect, useState } from "react"
import { buildApi, type BuildAttempt, type BuildStatus } from "./build"
import { KicadView, type KicadViewName } from "./KicadView"

const VERDICT: Record<string, string> = {
  passed: "Passed: the verifier found no problems.",
  failed_verify: "Stopped: the verifier still found problems after the last attempt.",
  failed_compile: "Stopped: the AI's board code didn't compile.",
  aborted: "Stopped before a board was made. The TUI says why.",
}

function line(a: BuildAttempt): string {
  if (!a.compiled) return `Attempt ${a.number}: didn't compile (${a.compile_tries} tries)`
  if (a.problems === 0) return `Attempt ${a.number}: compiled, no problems found`
  return `Attempt ${a.number}: compiled, the verifier found ${a.problems} problem${a.problems === 1 ? "" : "s"}`
}

export function BuildView() {
  const [status, setStatus] = useState<BuildStatus | null>(null)
  const [error, setError] = useState("")
  const [chosen, setChosen] = useState<number | null>(null)
  const [view, setView] = useState<KicadViewName>("pcb")

  useEffect(() => {
    let stop = false
    const poll = () => buildApi.status().then((s) => {
      if (stop) return
      setStatus(s)
      setError("")
      if (!s.finished) window.setTimeout(poll, 1000)
    }, (e) => { if (!stop) { setError(String(e)); window.setTimeout(poll, 2000) } })
    poll()
    return () => { stop = true }
  }, [])
  useEffect(() => { document.title = `reflow build: ${status?.title || "your board"}` }, [status?.title])

  const withBoard = (status?.attempts ?? []).filter((a) => a.has_kicad_pcb)
  const latest = withBoard.length ? withBoard[withBoard.length - 1].number : null
  const shown = chosen ?? latest
  const working = status && status.started && !status.finished

  return (
    <main className="page">
      <header>
        <h1>{status?.title || "Your board"}{status?.finished && status.started ? "" : ": building"}</h1>
        <p className="muted">
          Live from this run's folder. Nothing here is staged: each line is something the run actually did,
          and every view of the board is drawn by KiCad.
        </p>
      </header>
      {error && <p className="error">{error}</p>}
      <section className="build-log" aria-live="polite">
        {!status && <p>Connecting…</p>}
        {status && !status.started && <p>Waiting for the design to start…</p>}
        {status?.attempts.map((a) => (
          <p key={a.number} className={a.compiled && a.problems === 0 ? "good" : a.compiled ? "" : "bad"}>
            {line(a)}
            {a.has_kicad_pcb && (
              <button className="small" onClick={() => setChosen(a.number)} aria-pressed={shown === a.number}>
                show
              </button>
            )}
          </p>
        ))}
        {working && <p className="muted">Working on attempt {(status?.attempts.length ?? 0) + 1}…</p>}
        {status?.finished && status.started && (
          <p className={status.status === "passed" ? "good" : "bad"}>
            <strong>{VERDICT[status.status] ?? status.status}</strong>
            {status.attempts.some((a) => a.problems > 0) &&
              " Which problems, and why, is for you to find: open learn mode from the TUI."}
          </p>
        )}
      </section>

      {shown !== null && (
        <section>
          <div className="row">
            <div role="tablist" aria-label="View">
              <button role="tab" aria-selected={view === "pcb"} onClick={() => setView("pcb")}>PCB</button>
              <button role="tab" aria-selected={view === "schematic"} onClick={() => setView("schematic")}>Schematic</button>
              <button role="tab" aria-selected={view === "3d"} onClick={() => setView("3d")}>3D</button>
            </div>
            <span className="muted">Attempt {shown}, drawn by KiCad</span>
          </div>
          <KicadView key={`${shown}-${view}`} src={`/api/build/kicad/${shown}`} label={`attempt ${shown}`} view={view} />
        </section>
      )}
    </main>
  )
}
