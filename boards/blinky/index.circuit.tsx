export default () => (
  <board>
    <resistor name="R1" resistance="1k" footprint="0402" />
    <led name="D1" color="red" footprint="0603" />
    <pinheader name="J1" pinCount={2} />
    <trace from=".R1 > .pin2" to=".D1 > .anode" />
    <trace from=".D1 > .cathode" to="net.GND" />
  </board>
)
