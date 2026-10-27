import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In sviluppo le chiamate /api vanno al backend FastAPI (porta 8010).
// La marca di build compare in fondo alla barra laterale: serve a capire quale versione sta girando.
const BUILD = new Date().toISOString().slice(0, 16).replace("T", " ");

export default defineConfig({
  plugins: [react()],
  define: { __BUILD_TIME__: JSON.stringify(BUILD) },
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8010" } },
});
