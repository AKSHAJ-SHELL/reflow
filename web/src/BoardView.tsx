// The one place the tscircuit viewers are used (DECISIONS L-2: they change weekly,
// so a swap touches this file only).
import { PCBViewer, usePcbViewerController } from "@tscircuit/pcb-viewer"
import { SchematicViewer, useSchematicViewerController } from "@tscircuit/schematic-viewer"
import { useEffect, useMemo } from "react"
import { partIds } from "./circuit"

// The schematic viewer's hover card looks up price and stock on jlcsearch.tscircuit.com.
// Learn mode makes no network requests, so that lookup gets a fetch that always fails
// (the card then says "Price unavailable"). The server's CSP blocks it too.
const noNetwork = (async () => {
  throw new Error("reflow learn makes no network requests")
}) as unknown as typeof fetch
const OFFLINE = { platformFetch: noNetwork } as any

type Props = {
  circuit: any[]
  view: "schematic" | "pcb"
  focusRef: string | null
  onPartClicked: (ref: string) => void
}

export function BoardView({ circuit, view, focusRef, onPartClicked }: Props) {
  const ids = useMemo(() => partIds(circuit), [circuit])
  const schematic = useSchematicViewerController()
  const pcb = usePcbViewerController()

  useEffect(() => {
    if (!focusRef) return
    const schematicId = ids.schematicIdByRef.get(focusRef)
    const pcbId = ids.pcbIdByRef.get(focusRef)
    if (view === "schematic" && schematicId) schematic.focusSchematicComponent(schematicId)
    if (view === "pcb" && pcbId) pcb.focusPcbComponent(pcbId)
  }, [focusRef, view, ids])

  if (view === "pcb") {
    return (
      <div className="viewer" data-testid="pcb-viewer">
        <PCBViewer circuitJson={circuit as any} height={560} controller={pcb.controller} focusOnHover />
      </div>
    )
  }
  return (
    <div className="viewer" data-testid="schematic-viewer">
      <SchematicViewer
        circuitJson={circuit as any}
        containerStyle={{ height: 560 }}
        clickToInteractEnabled={false}
        searchEnabled={false}
        platformConfig={OFFLINE}
        controller={schematic.controller}
        onSchematicComponentClicked={({ schematicComponentId }) => {
          const ref = ids.refBySchematicId.get(schematicComponentId)
          if (ref) onPartClicked(ref)
        }}
      />
    </div>
  )
}
