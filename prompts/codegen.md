<!-- draft: human approval required before a loop loads this file -->

# Codegen

Write the whole `index.circuit.tsx` for a small 2-layer board. Reply with one tsx fence and no other code fence. The fence is the entire file. Do not return a diff, a patch, or a partial snippet.

Part numbers may be copied only from the resolved-parts table or Spec.named_parts. mpn stays empty otherwise.

## What you are given

Confirmed spec:

{spec}

Plan (blocks, parts, nets):

{plan}

Resolved-parts table. Columns are request_id, role, value, package, lcsc, and mpn. role is the matching plan part when the table includes it.

{resolved_parts}

Every row is one component. Do not add a component that has no row. Reference designators are yours to assign, except the ones the project rules below fix: U for an IC, R for a resistor, C for a capacitor, L for an inductor, D for a diode or LED, J for a connector. A request_id such as p1 is not a reference designator.

## Project rules: fixed references and pin requirements

These are the project's rules for this board. A line such as "U1 is the MCP9808 (plan part p1). Give it reference U1." fixes that part's reference designator: use exactly that reference. A line such as "U1 pinLabels, from the KiCad symbol ...: pinLabels={{ pin1: "SDA", ... }}" is that chip's pinout from a trusted pin map: copy that line exactly as the chip's pinLabels prop, and name the chip's pins in traces by those labels. Do not use a pinout from memory or from the example below. Every other line is a requirement on one pin, written REF.PIN with the part's own pin name. The finished board is checked against every line, so meet each one.

{project_rules}

## Part numbers in the TSX

Copy. Do not fill a part number from memory.

- manufacturerPartNumber is the mpn cell of that row, or a string that appears in Spec.named_parts. Omit the prop when neither source has a string for that part.
- supplierPartNumbers is set only from the lcsc cell. Its value is an object whose jlcpcb key holds a one-element list with that lcsc string, not a bare list: `supplierPartNumbers={{ jlcpcb: ["<lcsc cell>"] }}`. tscircuit drops a component whose supplierPartNumbers is a bare list. Omit supplierPartNumbers when the row has no lcsc.
- jlcpcb here is the supplier key on the component. The value is the lcsc cell from the table.

A passive footprint is the package cell, such as 0402 or 0603. For an IC, use a footprint name for that same package, such as soic8, and still copy lcsc and mpn from the same row.

## tscircuit

The file is a default export of a board. Passives, chips, headers, and traces use this shape:

```tsx
export default () => (
  <board>
    <chip
      name="U1"
      footprint="soic8"
      pinLabels={{ pin1: "VDD", pin2: "GND" }}
    />
    <capacitor name="C1" capacitance="100nF" footprint="0402" />
    <resistor name="R1" resistance="4.7k" footprint="0402" />
    <resistor name="R2" resistance="1k" footprint="0402" />
    <led name="D1" color="red" footprint="0603" />
    <pinheader name="J1" pinCount={4} />
    <trace from=".C1 > .pin1" to=".U1 > .VDD" />
    <trace from=".C1 > .pin2" to="net.GND" />
    <trace from=".R1 > .pin1" to="net.SDA" />
    <trace from=".R1 > .pin2" to="net.V3_3" />
    <trace from=".R2 > .pin1" to="net.V3_3" />
    <trace from=".R2 > .pin2" to=".D1 > .anode" />
    <trace from=".D1 > .cathode" to="net.GND" />
  </board>
)
```

The example omits manufacturerPartNumber and supplierPartNumbers. Add those props only by the copy rules above.

Selectors follow `.R1 > .pin1`, `.D1 > .anode`, `.D1 > .cathode`, and `net.GND`. Use the plan's net names. A power rail may also be declared with a net element, for example `<net name="GND" />`.

Wiring rules for this board:

- A decoupling capacitor has one pin on the IC supply net and the other pin on GND. Do not insert that capacitor between the rail and the IC pin.
- Give every decoupling capacitor `maxDecouplingTraceLength="5mm"`, for example `<capacitor name="C1" capacitance="100nF" footprint="0402" maxDecouplingTraceLength="5mm" />`. Without it tscircuit limits that cap's traces, to the supply pin and to ground, to 1 mm, and when placement can't meet the limit it routes nothing on the board.
- SDA has one resistor to the positive rail. SCL has one resistor to the positive rail.
- Connect A0, A1, A2, and ADDR to the rail or to GND so the address matches the spec. Each of those pins has a net.
- An LED has a series resistor. Do not tie an LED across a supply by itself.
- The two pins of a resistor, capacitor, inductor, or LED sit on different nets.
- Do not add USB, DDR, Ethernet, or RF nets.
- Write `<board>` with no width or height. tscircuit then places the parts and sizes the board around them, headers included, with clearance to the edge. Set `width` and `height` only when the spec gives a board size. v1 boards stay small, about 20 parts or fewer.
- Do not set pcbX or pcbY on any part. A hand-placed part can sit past the board edge, and then tscircuit routes nothing on the board.

## Output

One tsx fence. Inside it, `export default` and a `<board>` that contains every resolved row, every net connection, and the full `index.circuit.tsx`. No second fence. No diff.
