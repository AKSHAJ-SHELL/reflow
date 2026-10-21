# Local parts database fixture (P-05)

`cache.sqlite3` is a jlcparts `source-db-v2` database (the real schema, plus
`meta.format`) holding 27 rows copied unmodified from the 2026-10-21 snapshot.

What the MCP9808 eval board needs:
- 4.7k 0402 resistors in stock: C25900 (basic, ±1%), C105871 (±1%), C105870 (±5%)
- 100nF 0402 capacitors: C307331 (50V, basic), C1525 (16V, basic), C60474 (16V), C22435938 (6.3V)
- 1x4 2.54 mm pin headers: C32713270, C124378, C41417361 (SMD, staggered)
- MCP9808: C129490 (MCP9808T-E/MS), C94847 (MCP9808-E/MS), C194710 (MCP9808T-E/MC, DFN)

Rows that must not match:
- C100658: 4.7k 0402, no stock
- C23162: 4.7k 0603
- C93943: 47k 0402
- C22461632: 4.7k potentiometer
- C25499: resistor network
- C52923: 1uF 0402
- C14663: 100nF 0603
- C492412: 1x4 right-angle
- C541858: 1x4 2.0 mm
- C492401: 1x2
- C492421: 2x4 (matches a 2x4 request)
- C27438: female header
- C2286: LED, for category mapping
- C22369186: a 100k 0402 resistor the snapshot leaves uncategorised

The jlcparts project is MIT-licensed; its parts data is scraped from JLCPCB's
public catalogue, with no separate licence stated.
