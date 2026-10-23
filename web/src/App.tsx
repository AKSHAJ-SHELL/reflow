// reflow learn mode (DECISIONS L-2, L-2a): the board, spot-the-bug, fix it yourself, sign-off.
import { useEffect, useMemo, useRef, useState } from "react"
import { api, type FixResult, type RunInfo } from "./api"
import { BoardView } from "./BoardView"
import { partIds } from "./circuit"
import { RouteLine } from "./RouteLine"
import { FixPanel } from "./FixPanel"
import { LearnPanel } from "./LearnPanel"
import { SignOffPanel } from "./SignOffPanel"
import { VaultView } from "./VaultView"

type Key = string // "a1" = attempt 1, "f2" = the user's fix 2

export function App() {
  const [run, setRun] = useState<RunInfo | null>(null)
  const [error, setError] = useState("")
  const [key, setKey] = useState<Key | null>(null)
  const [circuits, setCircuits] = useState<Record<Key, any[]>>({})
  const [fixes, setFixes] = useState<FixResult[]>([])
  const [view, setView] = useState<"schematic" | "pcb" | "vault">("schematic")
  const [selected, setSelected] = useState<string | null>(null)
  const [focus, setFocus] = useState<string | null>(null)
  const [learnDone, setLearnDone] = useState(false)
  const [vaultVersion, setVaultVersion] = useState(0)
  const [revealed, setRevealed] = useState<string | null>(null)
  const [locked, setLockedState] = useState(false)
  // The viewers may keep the first click handler they're given, so it reads `locked` through a ref.
  const lockedRef = useRef(false)
  const setLocked = (value: boolean) => { lockedRef.current = value; setLockedState(value) }

  useEffect(() => {
    api.run().then((r) => {
      setRun(r)
      // Open on the AI's failed draft when there is one, so its final board isn't shown (or fetched) first.
      const draft = r.attempts.find((a) => a.compiled && a.errors > 0 && a.has_circuit)
      const start = draft?.number ?? (r.best_attempt || r.attempts.find((a) => a.has_circuit)?.number)
      setKey(start ? `a${start}` : null)
    }, (e) => setError(String(e)))
    api.fixes().then(setFixes, () => {})
  }, [])

  useEffect(() => {
    if (key === null || circuits[key]) return
    const load = key.startsWith("a") ? api.circuit(Number(key.slice(1))) : api.fixCircuit(Number(key.slice(1)))
    load.then((c) => setCircuits((all) => ({ ...all, [key]: c })), (e) => setError(String(e)))
  }, [key])

  const circuit = key !== null ? circuits[key] : undefined
  const parts = useMemo(() => (circuit ? partIds(circuit).refs : []), [circuit])

  if (error) return <main className="page"><p className="error">{error}</p></main>
  if (!run) return <main className="page"><p>Loading the run…</p></main>

  const draft = run.attempts.find((a) => a.compiled && a.errors > 0)?.number ?? null
  const current = key?.startsWith("a") ? run.attempts.find((a) => `a${a.number}` === key) : undefined
  const currentFix = key?.startsWith("f") ? fixes.find((f) => `f${f.number}` === key) : undefined
  const violations = current?.violations ?? currentFix?.violations ?? []
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
              <button role="tab" aria-selected={view === "vault"} onClick={() => setView("vault")}>Vault</button>
            </div>
            <label>
              Board:{" "}
              <select value={key ?? ""} disabled={locked}
                      onChange={(e) => { setKey(e.target.value); setSelected(null); setFocus(null) }}>
                {run.attempts.filter((a) => a.has_circuit).map((a) => (
                  <option key={a.number} value={`a${a.number}`}>
                    {a.number === run.best_attempt ? "AI's final board" : "AI's draft"} (attempt {a.number}
                    {locked ? "" : `, ${a.errors} error${a.errors === 1 ? "" : "s"}`})
                  </option>
                ))}
                {fixes.filter((f) => f.compiled).map((f) => (
                  <option key={`f${f.number}`} value={`f${f.number}`}>
                    Your fix {f.number} ({f.refused ? "refused" : `${f.errors} error${f.errors === 1 ? "" : "s"}`})
                  </option>
                ))}
              </select>
            </label>
          </div>
          {locked && <p className="muted">Showing the AI's draft. Its check results stay hidden until you answer.</p>}
          {view === "vault" ? (
            <VaultView key={vaultVersion} />
          ) : circuit ? (
            <BoardView circuit={circuit} view={view} focusRef={focus}
                       onPartClicked={(ref) => { if (lockedRef.current) setSelected(ref) }} />
          ) : (
            <p>Loading the board…</p>
          )}
          {view === "pcb" && !locked && key && (
            <RouteLine source={key.startsWith("a") ? { attempt: Number(key.slice(1)) } : { fix: Number(key.slice(1)) }} />
          )}
          {!locked && violations.length > 0 && (
            <details className="muted">
              <summary>Checks on this board ({violations.filter((v) => v.severity === "error").length} errors)</summary>
              <ul>{violations.map((v, i) => <li key={i}>{v.severity}: {v.message}</li>)}</ul>
            </details>
          )}
        </section>
        <aside>
          <LearnPanel
            selectedRef={selected}
            parts={parts}
            onSelect={(ref) => { setSelected(ref); setFocus(ref) }}
            onReveal={(refs, concept) => { setLocked(false); setFocus(refs[0] ?? null); setVaultVersion((v) => v + 1); setRevealed(concept) }}
            onShowDraft={(n) => { setKey(`a${n}`); setLocked(true); setSelected(null); setFocus(null); setView("schematic") }}
            onFinished={() => { setLocked(false); setLearnDone(true) }}
          />
          {(revealed || learnDone) && draft !== null && circuits[`a${draft}`] && (
            <FixPanel
              concept={revealed ?? "decoupling"}
              draftAttempt={draft}
              bestAttempt={run.best_attempt}
              draftCircuit={circuits[`a${draft}`]}
              onFixChecked={(r) => {
                setFixes((all) => [...all.filter((f) => f.number !== r.number), r])
                if (r.compiled) { setKey(`f${r.number}`); setView("schematic") }
              }}
            />
          )}
          {learnDone && <SignOffPanel />}
        </aside>
      </div>
    </main>
  )
}
