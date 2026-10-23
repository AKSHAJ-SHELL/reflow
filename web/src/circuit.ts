// Reference designators <-> viewer ids, read from a board's circuit.json.
type Element = { type: string; [key: string]: any }

export type PartIds = {
  refBySchematicId: Map<string, string>
  schematicIdByRef: Map<string, string>
  pcbIdByRef: Map<string, string>
  refs: string[]
}

export function partIds(circuit: Element[]): PartIds {
  const nameBySource = new Map<string, string>()
  for (const e of circuit) if (e.type === "source_component") nameBySource.set(e.source_component_id, e.name)
  const refBySchematicId = new Map<string, string>()
  const schematicIdByRef = new Map<string, string>()
  const pcbIdByRef = new Map<string, string>()
  for (const e of circuit) {
    const ref = nameBySource.get(e.source_component_id)
    if (!ref) continue
    if (e.type === "schematic_component") {
      refBySchematicId.set(e.schematic_component_id, ref)
      schematicIdByRef.set(ref, e.schematic_component_id)
    } else if (e.type === "pcb_component") {
      pcbIdByRef.set(ref, e.pcb_component_id)
    }
  }
  return { refBySchematicId, schematicIdByRef, pcbIdByRef, refs: [...nameBySource.values()].sort() }
}
