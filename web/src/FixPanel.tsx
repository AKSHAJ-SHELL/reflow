// Fix it yourself (DECISIONS L-2a): edit the AI's failed draft, have reflow recompile and
// re-verify it, then simulate the draft, your fix and the AI's final board side by side.
import { useMemo, useState } from "react"
import { api, type FixEdit, type FixResult, type SimResult, type Source } from "./api"
import { Plot } from "./Plot"

type Tool = "add_resistor" | "add_capacitor" | "set_value" | "connect" | "disconnect" | "delete" | "set_label" | "set_trace_limit"
const TOOLS: [Tool, string][] = [
  ["add_resistor", "Add a resistor"], ["add_capacitor", "Add a capacitor"], ["set_value", "Change a value"],
  ["connect", "Connect a pin to a net"], ["disconnect", "Disconnect a pin"], ["delete", "Delete a part"],
  ["set_label", "Set a chip pin's label"], ["set_trace_limit", "Keep a decoupling cap close (trace limit)"],
]
const SIM_CONCEPTS: [string, string][] = [["decoupling", "Decoupling"], ["i2c-pullup", "I²C pull-up"]]
const COLORS = { broken: "#c2410c", yours: "#2463eb", as_designed: "#15803d" }

type Props = {
  concept: string
  draftAttempt: number
  bestAttempt: number
  draftCircuit: any[]
  onFixChecked: (result: FixResult) => void
}

function names(circuit: any[]) {
  const ref = new Map<string, string>()
  for (const e of circuit) if (e.type === "source_component") ref.set(e.source_component_id, e.name)
  const pins = new Set<string>(), nets = new Set<string>()
  for (const e of circuit) {
    if (e.type === "source_port" && ref.has(e.source_component_id)) {
      pins.add(`${ref.get(e.source_component_id)}.${e.name}`)
      pins.add(`${ref.get(e.source_component_id)}.pin${e.pin_number}`)
    }
    if (e.type === "source_net") nets.add(e.name)
  }
  return { parts: [...ref.values()].sort(), pins: [...pins].sort(), nets: [...nets].sort() }
}

function describe(e: FixEdit): string {
  switch (e.kind) {
    case "add_part": return `add a ${e.value} ${e.part} from ${e.a} to ${e.b}`
    case "set_value": return `set ${e.ref} to ${e.value}`
    case "connect": return `connect ${e.a} to ${e.b}`
    case "disconnect": return `disconnect ${e.a}`
    case "delete": return `delete ${e.ref}`
    case "set_label": return `label ${e.ref} pin ${e.pin} "${e.value}"`
    case "set_trace_limit": return `keep ${e.ref} within ${e.value} of its pin`
    default: return e.kind
  }
}

export function FixPanel({ concept, draftAttempt, bestAttempt, draftCircuit, onFixChecked }: Props) {
  const lists = useMemo(() => names(draftCircuit), [draftCircuit])
  const [tool, setTool] = useState<Tool>("connect")
  const [form, setForm] = useState({ ref: "", pin: "", value: "", a: "", b: "" })
  const [edits, setEdits] = useState<FixEdit[]>([])
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<FixResult | null>(null)
  const [aiDiff, setAiDiff] = useState<string[] | null>(null)
  const [simConcept, setSimConcept] = useState(SIM_CONCEPTS.some(([c]) => c === concept) ? concept : "decoupling")
  const [pcb, setPcb] = useState(false)
  const [sims, setSims] = useState<SimResult[] | null>(null)
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value })

  const edit = (): FixEdit | null => {
    switch (tool) {
      case "add_resistor": return { kind: "add_part", part: "resistor", value: form.value, a: form.a, b: form.b }
      case "add_capacitor": return { kind: "add_part", part: "capacitor", value: form.value, a: form.a, b: form.b }
      case "set_value": return { kind: "set_value", ref: form.ref, value: form.value }
      case "connect": return { kind: "connect", a: form.a, b: form.b }
      case "disconnect": return { kind: "disconnect", a: form.a }
      case "delete": return { kind: "delete", ref: form.ref }
      case "set_label": return { kind: "set_label", ref: form.ref, pin: form.pin, value: form.value }
      case "set_trace_limit": return { kind: "set_trace_limit", ref: form.ref, value: form.value }
    }
  }

  const check = async () => {
    setBusy(true); setError("")
    try {
      const r = await api.fix(edits)
      setResult(r); onFixChecked(r); setSims(null)
    } catch (e) {
      setError(String(e).replace(/^Error: /, ""))
    } finally { setBusy(false) }
  }

  const simulate = async () => {
    setBusy(true)
    const sources: Source[] = [{ attempt: draftAttempt }]
    if (result?.compiled) sources.push({ fix: result.number })
    if (bestAttempt && bestAttempt !== draftAttempt) sources.push({ attempt: bestAttempt })
    try { setSims(await Promise.all(sources.map((s) => api.sim(simConcept, s, pcb)))) } finally { setBusy(false) }
  }

  const needs = {
    ref: ["set_value", "delete", "set_label", "set_trace_limit"].includes(tool),
    pin: tool === "set_label",
    value: ["add_resistor", "add_capacitor", "set_value", "set_label", "set_trace_limit"].includes(tool),
    a: ["add_resistor", "add_capacitor", "connect", "disconnect"].includes(tool),
    b: ["add_resistor", "add_capacitor", "connect"].includes(tool),
  }

  return (
    <section className="panel" aria-label="Fix it yourself">
      <h2>Fix it yourself</h2>
      <p className="muted">Edit the AI's draft. reflow recompiles it and runs the same checks as a real run. No AI involved.</p>
      <datalist id="fix-parts">{lists.parts.map((p) => <option key={p} value={p} />)}</datalist>
      <datalist id="fix-pins">{lists.pins.map((p) => <option key={p} value={p} />)}</datalist>
      <datalist id="fix-ends">{[...lists.nets, ...lists.pins].map((p) => <option key={p} value={p} />)}</datalist>
      <label className="field">Tool{" "}
        <select value={tool} onChange={(e) => setTool(e.target.value as Tool)}>
          {TOOLS.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
        </select>
      </label>
      <div className="fields">
        {needs.ref && <label className="field">Part <input list="fix-parts" value={form.ref} onChange={set("ref")} placeholder="U1" /></label>}
        {needs.pin && <label className="field">Pin number <input value={form.pin} onChange={set("pin")} placeholder="8" /></label>}
        {needs.value && <label className="field">{tool === "set_label" ? "Label" : tool === "set_trace_limit" ? "Within" : "Value"} <input value={form.value} onChange={set("value")} placeholder={tool === "set_label" ? "VDD" : tool === "set_trace_limit" ? "3mm" : tool === "add_capacitor" ? "100nF" : "4.7k"} /></label>}
        {needs.a && <label className="field">{tool === "disconnect" ? "Pin" : "From"} <input list={tool === "disconnect" ? "fix-pins" : "fix-ends"} value={form.a} onChange={set("a")} placeholder="U1.SDA" /></label>}
        {needs.b && <label className="field">To <input list="fix-ends" value={form.b} onChange={set("b")} placeholder="V3_3" /></label>}
      </div>
      <div className="actions">
        <button onClick={() => { const e = edit(); if (e) setEdits([...edits, e]) }}>Add this edit</button>
      </div>
      {edits.length > 0 && (
        <ol className="edits">
          {edits.map((e, i) => (
            <li key={i}>{describe(e)} <button className="small" onClick={() => setEdits(edits.filter((_, j) => j !== i))}>remove</button></li>
          ))}
        </ol>
      )}
      <div className="actions">
        <button className="primary" disabled={!edits.length || busy} onClick={check}>{busy ? "Checking…" : "Check my fix"}</button>
        {result && <button onClick={() => api.aiFix().then((a) => setAiDiff(a.diff))}>Show the AI's fix</button>}
      </div>
      {error && <p className="error">{error}</p>}
      {result && (
        <div className={!result.compiled || result.refused || result.errors ? "reveal wrong" : "reveal correct"}>
          {!result.compiled && <p><strong>It doesn't compile:</strong> {result.compile_errors[0]}</p>}
          {result.refused && <p><strong>The verifier won't take it:</strong> {result.refused}</p>}
          {result.compiled && !result.refused && (
            <p><strong>Your fix {result.number}:</strong> {result.errors === 0 ? "passes every check." : `${result.errors} error${result.errors === 1 ? "" : "s"} left.`}</p>
          )}
          {result.violations.filter((v) => v.severity === "error").slice(0, 6).map((v, i) => <p key={i} className="muted">• {v.message}</p>)}
        </div>
      )}
      {aiDiff && (
        <details open>
          <summary>The AI's fix (its final attempt vs this draft)</summary>
          <pre className="diff">{aiDiff.map((l, i) => <span key={i} className={l.startsWith("+") ? "add" : l.startsWith("-") ? "del" : ""}>{l}{"\n"}</span>)}</pre>
        </details>
      )}

      <h3>Simulate</h3>
      <div className="fields">
        <label className="field">Concept{" "}
          <select value={simConcept} onChange={(e) => setSimConcept(e.target.value)}>
            {SIM_CONCEPTS.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
          </select>
        </label>
        {simConcept === "decoupling" && (
          <label className="field"><input type="checkbox" checked={pcb} onChange={(e) => setPcb(e.target.checked)} /> include the PCB path from the cap to the pin</label>
        )}
      </div>
      <button disabled={busy} onClick={simulate}>{busy ? "Simulating…" : "Simulate the draft, your fix and the AI's board"}</button>
      {sims && (
        <div className="sims">
          {sims.map((s, i) => (
            <div key={i} className="sim">
              <h4>{s.variant === "broken" ? "AI's draft" : s.variant === "yours" ? "Your fix" : "AI's final"}{s.ran ? ` · ${s.verdict}` : ""}</h4>
              {s.ran && s.signals[0] ? <Plot signal={s.signals[0]} color={COLORS[s.variant as keyof typeof COLORS] ?? "#555"} /> : null}
              {s.notes.map((n, j) => <p key={j} className={s.ran ? "" : "muted"}>{n}</p>)}
            </div>
          ))}
        </div>
      )}
      {sims && sims.some((s) => s.assumptions.length) && (
        <details className="muted">
          <summary>What the simulation assumes (not on the board)</summary>
          <ul>{[...new Set(sims.flatMap((s) => s.assumptions))].map((a) => <li key={a}>{a}</li>)}</ul>
        </details>
      )}
    </section>
  )
}
