export default () => (
  <board width="25mm" height="20mm">
    <net name="V3_3" />
    <net name="GND" />
    <net name="SDA" />
    <net name="SCL" />

    <chip
      name="U1"
      footprint="soic8"
      manufacturerPartNumber="MCP9808T-E/MS"
      supplierPartNumbers={{ jlcpcb: ["C129490"] }}
      pinLabels={{
        pin1: "SDA",
        pin2: "SCL",
        pin3: "NC",
        pin4: "GND",
        pin5: "A2",
        pin6: "A1",
        pin7: "VDD",
        pin8: "A0",
      }}
    />
    <capacitor
      name="C1"
      capacitance="100nF"
      footprint="0402"
      manufacturerPartNumber="CL05B104KB54PNC"
      supplierPartNumbers={{ jlcpcb: ["C307331"] }}
    />
    <resistor
      name="R1"
      resistance="4.7k"
      footprint="0402"
      manufacturerPartNumber="0402WGF4701TCE"
      supplierPartNumbers={{ jlcpcb: ["C25900"] }}
    />
    <resistor
      name="R2"
      resistance="4.7k"
      footprint="0402"
      manufacturerPartNumber="0402WGF4701TCE"
      supplierPartNumbers={{ jlcpcb: ["C25900"] }}
    />
    <pinheader
      name="J1"
      pinCount={4}
      manufacturerPartNumber="HX PZ2.54-1x4P ZZ"
      supplierPartNumbers={{ jlcpcb: ["C32713270"] }}
      pinLabels={{
        pin1: "3V3",
        pin2: "GND",
        pin3: "SDA",
        pin4: "SCL",
      }}
    />

    <trace from=".J1 > .pin1" to="net.V3_3" />
    <trace from=".J1 > .pin2" to="net.GND" />
    <trace from=".J1 > .pin3" to="net.SDA" />
    <trace from=".J1 > .pin4" to="net.SCL" />

    <trace from=".U1 > .VDD" to="net.V3_3" />
    <trace from=".U1 > .GND" to="net.GND" />
    <trace from=".U1 > .SDA" to="net.SDA" />
    <trace from=".U1 > .SCL" to="net.SCL" />

    <trace from=".C1 > .pin1" to="net.V3_3" />
    <trace from=".C1 > .pin2" to="net.GND" />

    <trace from=".R1 > .pin1" to="net.SDA" />
    <trace from=".R1 > .pin2" to="net.V3_3" />

    <trace from=".R2 > .pin1" to="net.SCL" />
    <trace from=".R2 > .pin2" to="net.V3_3" />

    <trace from=".U1 > .A0" to="net.GND" />
    <trace from=".U1 > .A1" to="net.GND" />
    <trace from=".U1 > .A2" to="net.GND" />
  </board>
)
