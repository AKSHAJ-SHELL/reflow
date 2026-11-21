// reflow learn mode UI (DECISIONS L-2). `npm run build` writes ../reflow/learn/static,
// which the Python package ships, so users never need Node. Every board view on these pages is
// drawn by KiCad on the server; the page itself loads nothing from the internet.
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

export default defineConfig({
  plugins: [react()],
  base: "/",
  resolve: {
    dedupe: ["react", "react-dom"],
  },
  build: {
    outDir: "../reflow/learn/static",
    emptyOutDir: true,
  },
  server: {
    proxy: { "/api": "http://127.0.0.1:8765" },
  },
})
