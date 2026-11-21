# reflow learn UI

The web pages reflow serves on 127.0.0.1: learn mode (DECISIONS L-2), from `reflow learn RUN_DIR` (`reflow/learn/server.py`), and the live build view at `/build` (T-02), from `reflow watch RUN_DIR` (`reflow/learn/build.py`).

- **Every view of a board is drawn by KiCad on the server.** That means `kicad-cli pcb export svg`, `sch export svg` of the KiCad schematic reflow writes, and `pcb render` for 3D (`reflow.learn.build.KicadDrawings`). `src/KicadView.tsx` only shows the result, cropping KiCad's SVG to the drawing. No other viewer draws a board here; the human asked for this on 2026-11-21.
- **In learn mode you pick a part from the list beside the board,** not by clicking the drawing.
- **`npm ci && npm run build`** writes `../reflow/learn/static/`, which the Python package ships. Users never need Node.
- **`npm run dev`** serves it with hot reload and proxies `/api` to a learn server on 127.0.0.1:8765 (`reflow learn RUN --port 8765 --no-browser`).
- **Nothing is fetched from the internet.** The page talks only to its own server, which sends a same-origin Content-Security-Policy.
