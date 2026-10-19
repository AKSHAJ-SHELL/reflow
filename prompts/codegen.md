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

Every row is one component. Do not add a component that has no row. Reference designators are yours to assign: U for an IC, R for a resistor, C for a capacitor, L for an inductor, D for a diode or LED, J for a connector. A request_id such as p1 is not a reference designator.

## Part numbers in the TSX

Copy. Do not fill a part number from memory.

- manufacturerPartNumber is the mpn cell of that row, or a string that appears in Spec.named_parts. Omit the prop when neither source has a string for that part.
- supplierPartNumbers is set only from the lcsc cell. The jlcpcb entry is a one-element list holding that lcsc string. Omit supplierPartNumbers when the row has no lcsc.
- jlcpcb here is the supplier key on the component. The value is the lcsc cell from the table.

A passive footprint is the package cell, such as 0402 or 0603. For an IC, use a footprint name for that same package, such as soic8, and still copy lcsc and mpn from the same row.

## tscircuit

The file is a default export of a board. Passives, chips, headers, and traces use this shape:

```tsx
export default () => (
  <board width="25mm" height="20mm">
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
- SDA has one resistor to the positive rail. SCL has one resistor to the positive rail.
- Connect A0, A1, A2, and ADDR to the rail or to GND so the address matches the spec. Each of those pins has a net.
- An LED has a series resistor. Do not tie an LED across a supply by itself.
- The two pins of a resistor, capacitor, inductor, or LED sit on different nets.
- Do not add USB, DDR, Ethernet, or RF nets.
- Set board width and height in mm from the spec constraints. v1 boards stay small, about 20 parts or fewer.

## Output

One tsx fence. Inside it, `export default` and a `<board>` that contains every resolved row, every net connection, and the full `index.circuit.tsx`. No second fence. No diff.
