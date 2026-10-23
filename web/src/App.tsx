// reflow learn mode (DECISIONS L-2, phase 1): the board, spot-the-bug, sign-off.
import { useEffect, useMemo, useRef, useState } from "react"
import { api, type RunInfo } from "./api"
import { BoardView } from "./BoardView"
import { partIds } from "./circuit"
import { LearnPanel } from "./LearnPanel"
import { SignOffPanel } from "./SignOffPanel"

export function App() {
  const [run, setRun] = useState<RunInfo | null>(null)
  const [error, setError] = useState("")
  const [attempt, setAttempt] = useState<number | null>(null)
  const [circuits, setCircuits] = useState<Record<number, any[]>>({})
  const [view, setView] = useState<"schematic" | "pcb">("schematic")
  const [selected, setSelected] = useState<string | null>(null)
  const [focus, setFocus] = useState<string | null>(null)
  const [learnDone, setLearnDone] = useState(false)
  const [locked, setLockedState] = useState(false)
  // The viewers may keep the first click handler they're given, so it reads `locked` through a ref.
  const lockedRef = useRef(false)
  const setLocked = (value: boolean) => { lockedRef.current = value; setLockedState(value) }

  useEffect(() => {
    api.run().then((r) => {
      setRun(r)
      setAttempt(r.best_attempt || r.attempts.find((a) => a.has_circuit)?.number || null)
    }, (e) => setError(String(e)))
  }, [])

  useEffect(() => {
    if (attempt === null || circuits[attempt]) return
    api.circuit(attempt).then((c) => setCircuits((all) => ({ ...all, [attempt]: c })), (e) => setError(String(e)))
  }, [attempt])

  const circuit = attempt !== null ? circuits[attempt] : undefined
  const parts = useMemo(() => (circuit ? partIds(circuit).refs : []), [circuit])

  if (error) return <main className="page"><p className="error">{error}</p></main>
  if (!run) return <main className="page"><p>Loading the run…</p></main>

  const current = run.attempts.find((a) => a.number === attempt)
  return (
    <main className="page">
      <header>
        <h1>{run.spec.title}</h1>
        <p className="muted">{run.spec.request} · run {run.status} · {run.path}</p>
      </header>
      <div className="layout">
        <section className="board">
          <div className="toolbar">
            <div role="tablist" aria-label="View">
              <button role="tab" aria-selected={view === "schematic"} onClick={() => setView("schematic")}>Schematic</button>
              <button role="tab" aria-selected={view === "pcb"} onClick={() => setView("pcb")}>PCB</button>
            </div>
            <label>
              Board:{" "}
              <select value={attempt ?? ""} disabled={locked}
                      onChange={(e) => { setAttempt(Number(e.target.value)); setSelected(null); setFocus(null) }}>
                {run.attempts.filter((a) => a.has_circuit).map((a) => (
                  <option key={a.number} value={a.number}>
                    {a.number === run.best_attempt ? "Final board" : "AI's draft"} (attempt {a.number}
                    {locked && a.number === attempt ? "" : `, ${a.errors} error${a.errors === 1 ? "" : "s"}`})
                  </option>
                ))}
              </select>
            </label>
          </div>
          {locked && <p className="muted">Showing the AI's draft. Its check results stay hidden until you answer.</p>}
          {circuit ? (
            <BoardView circuit={circuit} view={view} focusRef={focus}
                       onPartClicked={(ref) => { if (lockedRef.current) setSelected(ref) }} />
          ) : (
            <p>Loading the board…</p>
          )}
          {!locked && current && current.violations.length > 0 && (
            <details className="muted">
              <summary>Checks on this attempt ({current.errors} errors, {current.warnings} warnings)</summary>
              <ul>{current.violations.map((v, i) => <li key={i}>{v.severity}: {v.message}</li>)}</ul>
            </details>
          )}
        </section>
        <aside>
          <LearnPanel
            selectedRef={selected}
            parts={parts}
            onSelect={(ref) => { setSelected(ref); setFocus(ref) }}
            onReveal={(refs) => { setLocked(false); setFocus(refs[0] ?? null) }}
            onShowDraft={(n) => { setAttempt(n); setLocked(true); setSelected(null); setFocus(null); setView("schematic") }}
            onFinished={() => { setLocked(false); setLearnDone(true) }}
          />
          {learnDone && <SignOffPanel />}
        </aside>
      </div>
    </main>
  )
}
