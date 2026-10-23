// A plain SVG line plot for a simulated signal. Every point ngspice returned is drawn
// (the server already thinned it keeping each bucket's min and max), so spikes show.
import type { SimSignal } from "./api"

const W = 320, H = 170, PAD = { l: 44, r: 8, t: 10, b: 28 }

function timeUnit(span: number): [number, string] {
  if (span < 2e-6) return [1e9, "ns"]
  if (span < 2e-3) return [1e6, "µs"]
  return [1e3, "ms"]
}

export function Plot({ signal, color }: { signal: SimSignal; color: string }) {
  const { t, v } = signal
  if (t.length < 2) return <p className="muted">No data.</p>
  const t0 = t[0], t1 = t[t.length - 1]
  let lo = Math.min(...v), hi = Math.max(...v)
  if (hi - lo < 1e-3) { lo -= 0.05; hi += 0.05 }
  const pad = (hi - lo) * 0.08
  lo -= pad; hi += pad
  const x = (tt: number) => PAD.l + ((tt - t0) / (t1 - t0)) * (W - PAD.l - PAD.r)
  const y = (vv: number) => PAD.t + (1 - (vv - lo) / (hi - lo)) * (H - PAD.t - PAD.b)
  const [scale, unit] = timeUnit(t1 - t0)
  const points = t.map((tt, i) => `${x(tt).toFixed(1)},${y(v[i]).toFixed(1)}`).join(" ")
  const ticks = [lo + pad, (lo + hi) / 2, hi - pad]
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="plot" role="img" aria-label={`${signal.name} over time`}>
      <rect x={PAD.l} y={PAD.t} width={W - PAD.l - PAD.r} height={H - PAD.t - PAD.b} className="plot-bg" />
      {ticks.map((tv) => (
        <g key={tv}>
          <line x1={PAD.l} x2={W - PAD.r} y1={y(tv)} y2={y(tv)} className="plot-grid" />
          <text x={PAD.l - 4} y={y(tv) + 3} textAnchor="end" className="plot-label">{tv.toFixed(2)}</text>
        </g>
      ))}
      <polyline points={points} fill="none" stroke={color} strokeWidth={1.5} />
      <text x={PAD.l} y={H - 8} className="plot-label">{(t0 * scale).toFixed(1)} {unit}</text>
      <text x={W - PAD.r} y={H - 8} textAnchor="end" className="plot-label">{(t1 * scale).toFixed(1)} {unit}</text>
      <text x={PAD.l + 4} y={PAD.t + 12} className="plot-label">{signal.name} ({signal.unit})</text>
    </svg>
  )
}
