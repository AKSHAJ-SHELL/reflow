// The learn server's API (reflow/learn/server.py). The browser talks to nothing else.
export type Violation = {
  rule_id: string
  severity: string
  message: string
  why: string
  fix_hint: string
  refs: string[]
  nets: string[]
}

export type Attempt = {
  number: number
  compiled: boolean
  has_circuit: boolean
  errors: number
  warnings: number
  violations: Violation[]
}

export type RunInfo = {
  path: string
  spec: { title: string; request: string; [key: string]: unknown }
  status: string
  best_attempt: number
  attempts: Attempt[]
}

export type Interaction = {
  id: string
  kind: string
  concept: string
  attempt: number
  prompt: string
  hint: string
}

type NextCommon = { skipped: string[]; recall?: Record<string, number> }

export type Next =
  | ({ done: false; index: number; total: number; interaction: Interaction } & NextCommon)
  | ({ done: true; reason: string; notes: string[] } & NextCommon)

export type VaultNode = { id: string; kind: string; title: string; path: string; obsidian: string }
export type VaultGraph = { nodes: VaultNode[]; links: { source: string; target: string }[] }

export type Answer =
  | { outcome: "try_again"; hint: string }
  | {
      outcome: "correct" | "wrong"
      rating: string
      answer_refs: string[]
      why: string
      fix_hint: string
      message: string
      rule_id: string
      concept: string
    }

export type SignOffState = { signed: boolean; warnings: string[] }

async function call<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers: body === undefined ? undefined : { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!response.ok) throw new Error(`${path}: ${response.status} ${await response.text()}`)
  return (await response.json()) as T
}

export const api = {
  run: () => call<RunInfo>("/api/run"),
  circuit: (attempt: number) => call<any[]>(`/api/circuit/${attempt}`),
  next: () => call<Next>("/api/learn/next"),
  hint: (id: string) => call<{ hint: string }>("/api/learn/hint", { id }),
  answer: (id: string, ref: string, why: string) => call<Answer>("/api/learn/answer", { id, ref, why }),
  unskip: (concept: string) => call<{ skipped: string[] }>("/api/learn/unskip", { concept }),
  vaultGraph: () => call<VaultGraph>("/api/vault/graph"),
  signoffState: () => call<SignOffState>("/api/signoff"),
  signoff: (accepted: boolean, overrides: string[]) => call<unknown>("/api/signoff", { accepted, overrides }),
}
