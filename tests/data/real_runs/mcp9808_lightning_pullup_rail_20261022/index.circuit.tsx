export default () => (
  <board width="25mm" height="20mm">
    <chip
      name="U1"
      footprint="soic8"
      pinLabels={{ pin1: "SDA", pin2: "SCL", pin3: "Alert", pin4: "GND", pin5: "A2", pin6: "A1", pin7: "A0", pin8: "VDD" }}
      manufacturerPartNumber="MCP9808T-E/MS"
      supplierPartNumbers={{ jlcpcb: ["C129490"] }}
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
    />
    <trace from=".C1 > .pin1" to=".U1 > .VDD" />
    <trace from=".C1 > .pin2" to="net.GND" />
    <trace from=".R1 > .pin1" to="net.SDA" />
    <trace from=".R1 > .pin2" to="net.V3_3" />
    <trace from=".R2 > .pin1" to="net.SCL" />
    <trace from=".R2 > .pin2" to="net.V3_3" />
    <trace from=".U1 > .pin1" to="net.SDA" />
    <trace from=".U1 > .pin2" to="net.SCL" />
    <trace from=".U1 > .pin5" to="net.GND" />
    <trace from=".U1 > .pin6" to="net.GND" />
    <trace from=".U1 > .pin7" to="net.GND" />
    <trace from=".U1 > .pin4" to="net.GND" />
    <trace from=".J1 > .pin1" to=".U1 > .VDD" />
    <trace from=".J1 > .pin2" to="net.GND" />
    <trace from=".J1 > .pin3" to="net.SDA" />
    <trace from=".J1 > .pin4" to="net.SCL" />
    <net name="V3_3" />
    <net name="GND" />
  </board>
)
