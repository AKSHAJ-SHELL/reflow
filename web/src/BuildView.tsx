// The live build view (T-02, docs/proposals/T-2-visual-beginner-front-door.md), served by
// `reflow watch` at /build. It shows a design run as it happens, from the run folder only:
// each attempt, how many problems the verifier found (not which: that's learn mode's job),
// and the board in PCB, schematic and a simplified 3D view, with a replay of the finished board.
import { useEffect, useMemo, useRef, useState } from "react"
import { Board3D } from "./Board3D"
import { BoardView } from "./BoardView"
import { buildApi, replayFrames, type BuildAttempt, type BuildStatus } from "./build"

type View = "pcb" | "schematic" | "3d"

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
  const [circuits, setCircuits] = useState<Record<number, any[]>>({})
  const [chosen, setChosen] = useState<number | null>(null)
  const [view, setView] = useState<View>("pcb")
  const [frame, setFrame] = useState<number | null>(null)
  const timer = useRef<number | null>(null)

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

  const withBoard = (status?.attempts ?? []).filter((a) => a.has_circuit)
  const latest = withBoard.length ? withBoard[withBoard.length - 1].number : null
  const shown = chosen ?? latest

  useEffect(() => {
    if (shown === null || circuits[shown]) return
    buildApi.circuit(shown).then((c) => setCircuits((all) => ({ ...all, [shown]: c })), (e) => setError(String(e)))
  }, [shown, circuits])

  const circuit = shown !== null ? circuits[shown] : undefined
  const frames = useMemo(() => (circuit ? replayFrames(circuit) : []), [circuit])
  useEffect(() => () => { if (timer.current) window.clearInterval(timer.current) }, [])
  useEffect(() => { stopReplay() }, [shown])

  function stopReplay() {
    if (timer.current) window.clearInterval(timer.current)
    timer.current = null
    setFrame(null)
  }
  function replay() {
    stopReplay()
    setFrame(0)
    timer.current = window.setInterval(() => {
      setFrame((f) => {
        if (f === null || f + 1 >= frames.length) { if (timer.current) window.clearInterval(timer.current); timer.current = null; return null }
        return f + 1
      })
    }, 250)
  }

  useEffect(() => { document.title = `reflow build: ${status?.title || "your board"}` }, [status?.title])
  const board = circuit && frame !== null ? frames[frame] : circuit
  const working = status && status.started && !status.finished

  return (
    <main className="page">
      <header>
        <h1>{status?.title || "Your board"}{status?.finished && status.started ? "" : ": building"}</h1>
        <p className="muted">
          Live from this run's folder. Nothing here is staged: each line is something the run actually did.
        </p>
      </header>
      {error && <p className="error">{error}</p>}
      <section className="build-log" aria-live="polite">
        {!status && <p>Connecting…</p>}
        {status && !status.started && <p>Waiting for the design to start…</p>}
        {status?.attempts.map((a) => (
          <p key={a.number} className={a.compiled && a.problems === 0 ? "good" : a.compiled ? "" : "bad"}>
            {line(a)}
            {a.has_circuit && (
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

      {circuit && (
        <section>
          <div className="row">
            <div role="tablist" aria-label="View">
              <button role="tab" aria-selected={view === "pcb"} onClick={() => setView("pcb")}>PCB</button>
              <button role="tab" aria-selected={view === "schematic"} onClick={() => setView("schematic")}>Schematic</button>
              <button role="tab" aria-selected={view === "3d"} onClick={() => setView("3d")}>3D</button>
            </div>
            {view !== "schematic" && (
              <button onClick={frame === null ? replay : stopReplay}>
                {frame === null ? "Replay the build" : "Stop"}
              </button>
            )}
            <span className="muted">Attempt {shown}</span>
          </div>
          {frame !== null && (
            <p className="muted">
              Replay of attempt {shown}'s finished board: parts first, then traces ({frame + 1}/{frames.length}).
              tscircuit doesn't record the order it placed or routed in, so this order is reflow's.
            </p>
          )}
          {view === "3d"
            ? <Board3D circuit={board!} />
            : <BoardView circuit={board!} view={view} focusRef={null} onPartClicked={() => {}} />}
        </section>
      )}
    </main>
  )
}
