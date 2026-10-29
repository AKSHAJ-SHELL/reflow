export default () => (
  <board minViaPadDiameter="0.4mm">
    <chip
      name="U1"
      footprint="soic16"
      manufacturerPartNumber="PCF8574T/3,518"
      supplierPartNumbers={{ jlcpcb: ["C7605"] }}
      pinLabels={{ pin1: "A0", pin2: "A1", pin3: "A2", pin4: "P0", pin5: "P1", pin6: "P2", pin7: "P3", pin8: "GND", pin9: "P4", pin10: "P5", pin11: "P6", pin12: "P7", pin13: "INT", pin14: "SCL", pin15: "SDA", pin16: "VDD" }}
    />
    <capacitor
      name="C1"
      capacitance="100nF"
      footprint="0402"
      maxDecouplingTraceLength="5mm"
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
      pitch="2.54mm"
      manufacturerPartNumber="HX PZ2.54-1x4P ZZ"
      supplierPartNumbers={{ jlcpcb: ["C32713270"] }}
    />
    <pinheader
      name="J2"
      pinCount={8}
      pitch="2.54mm"
      manufacturerPartNumber="PZ254V-11-08P"
      supplierPartNumbers={{ jlcpcb: ["C492407"] }}
    />

    <trace from=".J1 > .pin1" to="net.V3_3" />
    <trace from=".J1 > .pin2" to="net.GND" />
    <trace from=".J1 > .pin3" to="net.SDA" />
    <trace from=".J1 > .pin4" to="net.SCL" />

    <trace from=".U1 > .VDD" to="net.V3_3" />
    <trace from=".U1 > .GND" to="net.GND" />
    <trace from=".U1 > .A0" to="net.GND" />
    <trace from=".U1 > .A1" to="net.GND" />
    <trace from=".U1 > .A2" to="net.GND" />
    <trace from=".U1 > .SDA" to="net.SDA" />
    <trace from=".U1 > .SCL" to="net.SCL" />

    <trace from=".C1 > .pin1" to="net.V3_3" />
    <trace from=".C1 > .pin2" to="net.GND" />

    <trace from=".R1 > .pin1" to="net.SDA" />
    <trace from=".R1 > .pin2" to="net.V3_3" />
    <trace from=".R2 > .pin1" to="net.SCL" />
    <trace from=".R2 > .pin2" to="net.V3_3" />

    <trace from=".U1 > .P0" to="net.P0" />
    <trace from=".U1 > .P1" to="net.P1" />
    <trace from=".U1 > .P2" to="net.P2" />
    <trace from=".U1 > .P3" to="net.P3" />
    <trace from=".U1 > .P4" to="net.P4" />
    <trace from=".U1 > .P5" to="net.P5" />
    <trace from=".U1 > .P6" to="net.P6" />
    <trace from=".U1 > .P7" to="net.P7" />

    <trace from=".J2 > .pin1" to="net.P0" />
    <trace from=".J2 > .pin2" to="net.P1" />
    <trace from=".J2 > .pin3" to="net.P2" />
    <trace from=".J2 > .pin4" to="net.P3" />
    <trace from=".J2 > .pin5" to="net.P4" />
    <trace from=".J2 > .pin6" to="net.P5" />
    <trace from=".J2 > .pin7" to="net.P6" />
    <trace from=".J2 > .pin8" to="net.P7" />
  </board>
)
