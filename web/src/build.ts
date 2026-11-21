// The live build view's data (T-02): what reflow/learn/build.py sends. Every board view is drawn by
// KiCad on the server; this file only knows the run's status.
export type BuildAttempt = {
  number: number
  compiled: boolean
  compile_tries: number
  problems: number
  warnings: number
  has_circuit: boolean
  has_kicad_pcb: boolean
}

export type BuildStatus = {
  started: boolean
  finished: boolean
  status: string
  title: string
  best_attempt: number
  attempts: BuildAttempt[]
}

async function get<T>(path: string): Promise<T> {
  const response = await fetch(path)
  if (!response.ok) throw new Error(`${path}: ${response.status} ${await response.text()}`)
  return response.json() as Promise<T>
}

export const buildApi = {
  status: () => get<BuildStatus>("/api/build"),
}
