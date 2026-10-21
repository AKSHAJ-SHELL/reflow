export default () => (
  <board width="20mm" height="15mm">
    <chip name="U1" footprint="soic8" pinLabels={{ pin1: "SDA", pin2: "SCL", pin3: "A0", pin4: "GND", pin5: "A1", pin6: "A2", pin7: "ALERT", pin8: "VDD" }} />
    <capacitor name="C1" capacitance="100nF" footprint="0402" />
    <pinheader name="J1" pinCount={4} />
    <trace from=".J1 > .pin1" to="net.V3_3" />
    <trace from=".J1 > .pin2" to="net.GND" />
    <trace from=".J1 > .pin3" to="net.SDA" />
    <trace from=".J1 > .pin4" to="net.SCL" />
    <trace from=".U1 > .SDA" to="net.SDA" />
    <trace from=".U1 > .SCL" to="net.SCL" />
    <trace from=".U1 > .VDD" to="net.V3_3" />
    <trace from=".U1 > .GND" to="net.GND" />
    <trace from=".U1 > .A0" to="net.GND" />
    <trace from=".U1 > .A1" to="net.GND" />
    <trace from=".U1 > .A2" to="net.GND" />
    <trace from=".C1 > .pin1" to="net.V3_3" />
    <trace from=".C1 > .pin2" to="net.GND" />
  </board>
)
