// The final yes/no (L-03): remaining warnings, overrides, then sign-off.
import { useEffect, useState } from "react"
import { api, type SignOffState } from "./api"

export function SignOffPanel() {
  const [state, setState] = useState<SignOffState | null>(null)
  const [overrides, setOverrides] = useState("")
  const [answer, setAnswer] = useState<boolean | null>(null)

  useEffect(() => { api.signoffState().then(setState) }, [])
  if (!state) return null

  const submit = async (accepted: boolean) => {
    await api.signoff(accepted, overrides.split("\n"))
    setAnswer(accepted)
    setState({ ...state, signed: true })
  }

  return (
    <section className="panel" aria-label="Sign-off">
      <h2>Sign-off</h2>
      {state.warnings.length > 0 ? (
        <>
          <p>These warnings are still on the final board:</p>
          <ul>{state.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
        </>
      ) : (
        <p>The final board has no remaining warnings.</p>
      )}
      <label className="why">
        Anything you're choosing to override (one per line, optional):
        <textarea value={overrides} onChange={(e) => setOverrides(e.target.value)} rows={2} disabled={answer !== null} />
      </label>
      {answer === null ? (
        <div className="actions">
          <button className="primary" onClick={() => submit(true)}>Yes, I understand this board</button>
          <button onClick={() => submit(false)}>No, not yet</button>
        </div>
      ) : (
        <p className="reveal correct">
          {answer ? "Signed off. Saved to signoff.json in the run folder." : "Not signed off. Saved to signoff.json; nothing goes on to export."}
        </p>
      )}
    </section>
  )
}
