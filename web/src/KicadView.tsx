// One view of a board, drawn by KiCad itself on the server (T-02; learn mode too): the PCB
// (kicad-cli pcb export svg), the schematic (kicad-cli sch export svg of reflow's KiCad schematic)
// or the 3D board (kicad-cli pcb render). No other viewer draws the board on this page.
import { useEffect, useRef, useState } from "react"

export type KicadViewName = "pcb" | "schematic" | "3d"

const CAPTION: Record<KicadViewName, string> = {
  pcb: "KiCad's PCB: front and back copper, silkscreen and the board outline, from this board's .kicad_pcb.",
  schematic: "KiCad's schematic, from the KiCad schematic reflow writes for this board.",
  "3d": "KiCad's 3D render of this board's .kicad_pcb. Chips and resistors show as bare pads: tscircuit's "
    + "footprints carry no KiCad 3D models, so KiCad has no part bodies to draw.",
}

// What KiCad drew, without the page: KiCad fills the whole page with a background, so a
// group as big as the page is left out of the crop (it's still drawn).
function contentBox(svg: SVGSVGElement) {
  const page = svg.getBBox()
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity
  for (const child of Array.from(svg.children)) {
    if (!(child instanceof SVGGraphicsElement)) continue
    const b = child.getBBox()
    if (b.width === 0 && b.height === 0) continue
    if (b.width >= page.width * 0.98 && b.height >= page.height * 0.98) continue
    x0 = Math.min(x0, b.x); y0 = Math.min(y0, b.y); x1 = Math.max(x1, b.x + b.width); y1 = Math.max(y1, b.y + b.height)
  }
  return x1 > x0 ? { x: x0, y: y0, width: x1 - x0, height: y1 - y0 } : page
}

// `src` is the server path without the view, e.g. "/api/build/kicad/2" or "/api/kicad/fix/1";
// `label` names the board in messages ("attempt 2", "your fix 1").
export function KicadView({ src, label, view }: { src: string; label: string; view: KicadViewName }) {
  const [url, setUrl] = useState<string | null>(null)
  const [problem, setProblem] = useState("")
  const [svg, setSvg] = useState<string | null>(null)
  const host = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let made: string | null = null
    let stop = false
    setUrl(null)
    setSvg(null)
    setProblem("")
    fetch(`${src}/${view}`).then(async (response) => {
      if (stop) return
      if (!response.ok) {
        const body = await response.json().catch(() => ({ detail: response.statusText }))
        setProblem(String(body.detail ?? response.statusText))
        return
      }
      const blob = await response.blob()
      made = URL.createObjectURL(blob)
      setUrl(made)
      if (view !== "3d") setSvg(await blob.text())
    }, (e) => { if (!stop) setProblem(String(e)) })
    return () => { stop = true; if (made) URL.revokeObjectURL(made) }
  }, [src, view])

  // KiCad's SVG is drawn inline so it can be cropped to what KiCad drew (a schematic sits on a whole
  // page). Only the viewBox changes; every line and label is KiCad's own.
  useEffect(() => {
    const el = host.current
    if (!el || !svg) return
    const doc = new DOMParser().parseFromString(svg, "image/svg+xml")
    const root = doc.documentElement
    if (root.nodeName !== "svg") return
    const drawn = document.importNode(root, true) as unknown as SVGSVGElement
    drawn.querySelectorAll("script, foreignObject").forEach((n) => n.remove())
    drawn.setAttribute("width", "100%")
    drawn.setAttribute("height", "560")
    el.replaceChildren(drawn)
    const box = contentBox(drawn)
    if (box && box.width > 0 && box.height > 0) {
      const pad = Math.max(box.width, box.height) * 0.03
      drawn.setAttribute("viewBox", `${box.x - pad} ${box.y - pad} ${box.width + 2 * pad} ${box.height + 2 * pad}`)
      drawn.setAttribute("preserveAspectRatio", "xMidYMid meet")
    }
  }, [svg])

  return (
    <div>
      <div className={`viewer kicad-view kicad-${view}`}>
        {url && view === "3d" && <img src={url} alt={`KiCad's 3D render of ${label}`} />}
        {view !== "3d" && <div ref={host} className="kicad-svg" role="img" aria-label={`KiCad's ${view} of ${label}`} />}
        {!url && !problem && <p className="muted">KiCad is drawing {label}'s {view}…</p>}
        {problem && <p className="error">{problem}</p>}
      </div>
      <p className="muted">
        {CAPTION[view]}{" "}
        {url && <a href={url} target="_blank" rel="noreferrer">Open full size</a>}
      </p>
    </div>
  )
}
