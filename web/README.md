# reflow learn UI

The learn-mode web app (DECISIONS L-2), served by `reflow learn RUN_DIR` (`reflow/learn/server.py`).

- `npm ci && npm run build` writes `../reflow/learn/static/`, which the Python package ships. Users never need Node.
- `npm run dev` serves it with hot reload and proxies `/api` to a learn server on 127.0.0.1:8765 (`reflow learn RUN --port 8765 --no-browser`).
- Versions are pinned exactly: the tscircuit viewers release almost daily. `src/BoardView.tsx` is the only file that uses them.
- Nothing is fetched from the internet. The schematic viewer's CDN importer is aliased to `src/noRemoteImport.ts`, its part-price lookup gets a fetch that always fails, and the server sends a same-origin Content-Security-Policy.

- `/build` is the live build view (T-02), served by `reflow watch RUN_DIR` (`reflow/learn/build.py`). Every view of the board there is drawn by KiCad on the server (`kicad-cli pcb export svg`, `sch export svg`, `pcb render`); `src/KicadView.tsx` only shows it, cropping KiCad's SVG to the drawing.
