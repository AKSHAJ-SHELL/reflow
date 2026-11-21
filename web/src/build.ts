// The live build view's data (T-02): what reflow/learn/build.py sends, a replay of a finished
// board, and a simplified 3D model. Everything here comes from the run's own circuit.json.
type Element = { type: string; [key: string]: any }

export type BuildAttempt = {
  number: number
  compiled: boolean
  compile_tries: number
  problems: number
  warnings: number
  has_circuit: boolean
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
  circuit: (attempt: number) => get<Element[]>(`/api/build/circuit/${attempt}`),
}

const isError = (e: Element) => e.type.endsWith("_error") || e.type.endsWith("_warning")

/** Frames of a finished board: the bare board, then one part at a time, then one trace at a time.
 *  This is a replay of the result. tscircuit doesn't record the order it placed or routed in. */
export function replayFrames(circuit: Element[]): Element[][] {
  const parts = circuit.filter((e) => e.type === "pcb_component")
  const ownedBy = (e: Element) => (e.type !== "pcb_component" && e.pcb_component_id) || null
  const traces = circuit.filter((e) => e.type === "pcb_trace")
  const viasOf = (trace: Element) => circuit.filter((e) => e.type === "pcb_via" && e.pcb_trace_id === trace.pcb_trace_id)
  const base = circuit.filter((e) => e.type !== "pcb_component" && !ownedBy(e) && e.type !== "pcb_trace"
    && e.type !== "pcb_via" && !isError(e))
  const frames: Element[][] = [base]
  let shown = [...base]
  for (const part of parts) {
    shown = [...shown, part, ...circuit.filter((e) => ownedBy(e) === part.pcb_component_id)]
    frames.push(shown)
  }
  const loose = circuit.filter((e) => e.type === "pcb_via" && !traces.some((t) => t.pcb_trace_id === e.pcb_trace_id))
  for (const trace of traces) {
    shown = [...shown, trace, ...viasOf(trace)]
    frames.push(shown)
  }
  frames.push(circuit.length === shown.length + loose.length ? [...shown, ...loose] : circuit)
  return frames
}

export type Board3D = {
  board: { width: number; height: number; x: number; y: number; thickness: number }
  parts: { ref: string; x: number; y: number; width: number; height: number; tall: number; rotation: number; layer: string }[]
  pads: { x: number; y: number; width: number; height: number; layer: string }[]
  traces: { layer: string; width: number; from: [number, number]; to: [number, number] }[]
  vias: { x: number; y: number; diameter: number }[]
  holes: { x: number; y: number; diameter: number }[]
}

// Body heights in mm. These are stand-ins: parts are drawn as boxes, not real 3D models.
const TALL: Record<string, number> = { simple_resistor: 0.45, simple_capacitor: 0.8, simple_chip: 1.0, simple_pin_header: 2.5 }

export function board3d(circuit: Element[]): Board3D {
  const board = circuit.find((e) => e.type === "pcb_board")
  const sources = new Map(circuit.filter((e) => e.type === "source_component").map((e) => [e.source_component_id, e]))
  const parts = circuit.filter((e) => e.type === "pcb_component").map((e) => {
    const source = sources.get(e.source_component_id)
    const holes = circuit.some((h) => h.type === "pcb_plated_hole" && h.pcb_component_id === e.pcb_component_id)
    return {
      ref: source?.name ?? "",
      x: e.center.x, y: e.center.y, width: e.width, height: e.height,
      tall: TALL[source?.ftype] ?? (holes ? 2.5 : 1.0),
      rotation: e.rotation ?? 0, layer: e.layer ?? "top",
    }
  })
  const traces: Board3D["traces"] = []
  for (const trace of circuit.filter((e) => e.type === "pcb_trace")) {
    const points = (trace.route ?? []).filter((p: Element) => p.route_type === "wire")
    for (let i = 1; i < points.length; i++) {
      const a = points[i - 1], b = points[i]
      if (a.layer !== b.layer) continue
      traces.push({ layer: b.layer, width: b.width ?? 0.15, from: [a.x, a.y], to: [b.x, b.y] })
    }
  }
  return {
    board: {
      width: board?.width ?? 20, height: board?.height ?? 20,
      x: board?.center?.x ?? 0, y: board?.center?.y ?? 0, thickness: board?.thickness ?? 1.6,
    },
    parts,
    pads: circuit.filter((e) => e.type === "pcb_smtpad" && e.shape === "rect")
      .map((e) => ({ x: e.x, y: e.y, width: e.width, height: e.height, layer: e.layer })),
    traces,
    vias: circuit.filter((e) => e.type === "pcb_via").map((e) => ({ x: e.x, y: e.y, diameter: e.outer_diameter ?? 0.6 })),
    holes: circuit.filter((e) => e.type === "pcb_plated_hole")
      .map((e) => ({ x: e.x, y: e.y, diameter: e.outer_diameter ?? e.rect_pad_width ?? e.hole_diameter ?? 1 })),
  }
}
