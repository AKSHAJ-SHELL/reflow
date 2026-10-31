// reflow learn mode UI (DECISIONS L-2). `npm run build` writes ../reflow/learn/static,
// which the Python package ships, so users never need Node.
import { fileURLToPath } from "node:url"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

export default defineConfig({
  plugins: [react()],
  base: "/",
  resolve: {
    // Several tscircuit packages carry their own React; the page must use exactly one.
    dedupe: ["react", "react-dom"],
    alias: {
      // The schematic viewer's optional "style analysis" downloads code from a CDN at runtime.
      // Learn mode keeps everything on the user's machine, so that import is replaced.
      "@tscircuit/internal-dynamic-import": fileURLToPath(new URL("./src/noRemoteImport.ts", import.meta.url)),
    },
  },
  build: {
    outDir: "../reflow/learn/static",
    emptyOutDir: true,
    chunkSizeWarningLimit: 8000,
  },
  server: {
    proxy: { "/api": "http://127.0.0.1:8765" },
  },
})
