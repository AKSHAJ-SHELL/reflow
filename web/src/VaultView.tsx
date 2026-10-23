// The vault as a graph (DECISIONS L-2): concepts, mistakes and boards, linked by [[wikilinks]].
// Clicking a note opens it in Obsidian; the files are plain markdown in the vault folder.
import ForceGraph2D from "react-force-graph-2d"
import { useEffect, useRef, useState } from "react"
import { api, type VaultGraph, type VaultNode } from "./api"

const COLORS: Record<string, string> = { concept: "#2463eb", mistake: "#c2410c", board: "#15803d" }

export function VaultView() {
  const [graph, setGraph] = useState<VaultGraph | null>(null)
  const [picked, setPicked] = useState<VaultNode | null>(null)
  const box = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(800)

  useEffect(() => { api.vaultGraph().then(setGraph) }, [])
  useEffect(() => {
    const el = box.current
    if (!el) return
    const observer = new ResizeObserver(() => setWidth(el.clientWidth))
    observer.observe(el)
    return () => observer.disconnect()
  }, [graph])

  if (!graph) return <p>Loading your vault…</p>
  if (graph.nodes.length === 0) {
    return <p className="muted">Your vault is empty. Notes appear here after you answer a spot-the-bug question.</p>
  }
  return (
    <div>
      <div className="viewer vault" ref={box} data-testid="vault-graph">
        <ForceGraph2D
          graphData={{ nodes: graph.nodes.map((n) => ({ ...n })), links: graph.links.map((l) => ({ ...l })) }}
          width={width}
          height={520}
          backgroundColor="#ffffff"
          nodeLabel={(n: any) => `${n.kind}: ${n.title}`}
          nodeColor={(n: any) => COLORS[n.kind] ?? "#555"}
          nodeRelSize={6}
          linkColor={() => "#9aa1ac"}
          onNodeClick={(n: any) => setPicked(n as VaultNode)}
        />
      </div>
      <p className="muted legend">
        <span style={{ color: COLORS.concept }}>● concepts</span> <span style={{ color: COLORS.mistake }}>● mistakes</span>{" "}
        <span style={{ color: COLORS.board }}>● boards</span> · {graph.nodes.length} notes
      </p>
      {picked && (
        <p>
          <strong>{picked.title}</strong> <span className="muted">({picked.path})</span>{" "}
          <a href={picked.obsidian}>Open in Obsidian</a>
        </p>
      )}
      <ul className="note-list">
        {graph.nodes.map((n) => (
          <li key={n.id}>
            <span style={{ color: COLORS[n.kind] }}>●</span> <a href={n.obsidian}>{n.title}</a>{" "}
            <span className="muted">{n.path}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
