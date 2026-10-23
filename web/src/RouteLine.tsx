// What tscircuit routed on the board being shown, checked by reflow's own KiCad DRC (X-04).
import { useEffect, useState } from "react"
import { api, type RouteResult, type Source } from "./api"

export function RouteLine({ source }: { source: Source }) {
  const [route, setRoute] = useState<RouteResult | null>(null)
  const [note, setNote] = useState("Checking the routing…")
  useEffect(() => {
    setRoute(null); setNote("Checking the routing…")
    api.route(source).then(setRoute, () => setNote("No PCB file for this board in the run folder."))
  }, [JSON.stringify(source)])
  if (!route) return <p className="muted">{note}</p>
  const label = { routed: "routed", partial: "partly routed", failed: "not routed", refused: "refused" }[route.status] ?? route.status
  return (
    <p className={route.status === "routed" ? "route ok" : "route"}>
      <strong>Routing ({route.router}): {label}.</strong> {route.routed_nets}/{route.total_nets} nets in copper
      {route.unrouted_nets.length > 0 && <> · unrouted: {route.unrouted_nets.slice(0, 6).join(", ")}{route.unrouted_nets.length > 6 ? "…" : ""}</>}
      {" "}· KiCad DRC (the board's default rules): {route.drc.errors} error{route.drc.errors === 1 ? "" : "s"}, {route.drc.unconnected} unconnected
    </p>
  )
}
