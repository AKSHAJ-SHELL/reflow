import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { App } from "./App"
import { BuildView } from "./BuildView"
import "./styles.css"

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {window.location.pathname.startsWith("/build") ? <BuildView /> : <App />}
  </StrictMode>,
)
