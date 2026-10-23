// Spot-the-bug (DECISIONS D-4): commit to a part and a reason first, then see the why.
import { useEffect, useState } from "react"
import { api, type Answer, type Next } from "./api"

type Props = {
  selectedRef: string | null
  parts: string[]
  onSelect: (ref: string) => void
  onReveal: (refs: string[], concept: string) => void
  onShowDraft: (attempt: number) => void
  onFinished: () => void
}

export function LearnPanel({ selectedRef, parts, onSelect, onReveal, onShowDraft, onFinished }: Props) {
  const [next, setNext] = useState<Next | null>(null)
  const [why, setWhy] = useState("")
  const [hint, setHint] = useState("")
  const [result, setResult] = useState<Answer | null>(null)
  const [submitted, setSubmitted] = useState<string | null>(null)
  const [error, setError] = useState("")

  const load = () => {
    setWhy("")
    setHint("")
    setResult(null)
    setSubmitted(null)
    api.next().then((n) => {
      setNext(n)
      if (!n.done) onShowDraft(n.interaction.attempt)
      else onFinished()
    }, (e) => setError(String(e)))
  }
  useEffect(load, [])

  if (error) return <section className="panel"><p className="error">{error}</p></section>
  if (!next) return <section className="panel"><p>Loading…</p></section>

  const extras = (
    <>
      {next.skipped.length > 0 && (
        <div className="skipped">
          {next.skipped.map((concept) => (
            <p key={concept} className="muted">
              Skipped: {concept}, you've got it
              {next.recall?.[concept] !== undefined ? ` (recall ${Math.round(next.recall[concept] * 100)}%)` : ""}.{" "}
              <button onClick={() => api.unskip(concept).then(load)}>Do it anyway</button>
            </p>
          ))}
        </div>
      )}
      {next.done && next.notes.length > 0 && (
        <details className="muted">
          <summary>Why some checks aren't asked</summary>
          <ul>{next.notes.map((n) => <li key={n}>{n}</li>)}</ul>
        </details>
      )}
    </>
  )

  if (next.done) {
    return (
      <section className="panel" aria-label="Learn">
        <h2>Learn</h2>
        <p>{next.reason === "all done" ? "That's everything for this board." : `Nothing to spot: ${next.reason}.`}</p>
        {extras}
      </section>
    )
  }

  const item = next.interaction
  const finished = result && result.outcome !== "try_again"

  const check = async () => {
    if (!selectedRef) return
    const answer = await api.answer(item.id, selectedRef, why)
    setSubmitted(selectedRef)
    setResult(answer)
    if (answer.outcome === "try_again") setHint(answer.hint)
    else onReveal(answer.answer_refs, answer.concept)
  }

  return (
    <section className="panel" aria-label="Learn">
      <h2>Spot the bug <span className="muted">({next.index} of {next.total})</span></h2>
      <p>{item.prompt}</p>

      <p className="pick">
        Your pick: <strong data-testid="selected-part">{(finished ? submitted : selectedRef) ?? "nothing yet; click a part"}</strong>
      </p>
      <div className="part-buttons" aria-label="Or pick a part">
        {parts.map((ref) => (
          <button key={ref} className={ref === selectedRef ? "part selected" : "part"}
                  disabled={!!finished} onClick={() => onSelect(ref)}>{ref}</button>
        ))}
      </div>

      <label className="why">
        What's wrong with it, in one sentence:
        <textarea value={why} disabled={!!finished} onChange={(e) => setWhy(e.target.value)} rows={2} />
      </label>

      {!finished && (
        <div className="actions">
          <button className="primary" disabled={!selectedRef} onClick={check}>Check my answer</button>
          {!hint && (
            <button onClick={() => api.hint(item.id).then((h) => setHint(h.hint))}>I'd like a hint</button>
          )}
        </div>
      )}
      {hint && !finished && (
        <p className="hint">
          {result?.outcome === "try_again" ? "Not that one. " : ""}Hint: {hint}
        </p>
      )}

      {result && result.outcome !== "try_again" && (
        <div className={result.outcome === "correct" ? "reveal correct" : "reveal wrong"}>
          <h3>{result.outcome === "correct" ? "Right." : `It was ${result.answer_refs.join(" / ")}.`}</h3>
          <p><strong>What the check found:</strong> {result.message}</p>
          <p><strong>Why it matters:</strong> {result.why}</p>
          {why.trim() && <p><strong>You said:</strong> {why.trim()}</p>}
          <p><strong>The fix:</strong> {result.fix_hint}</p>
          <p className="muted">Check: {result.rule_id} · noted in your vault under concepts/{result.concept}</p>
          <button className="primary" onClick={load}>Next</button>
        </div>
      )}
      {extras}
    </section>
  )
}
