import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Backend alvo do proxy. No server é o uvicorn local; para desenvolver de outra máquina:
// VORTAX_API_TARGET=http://192.168.0.104:8010 npm run dev
const apiTarget = process.env.VORTAX_API_TARGET || "http://127.0.0.1:8010";

const proxy = {
  "/api": apiTarget,
  "/health": apiTarget,
  "/ws": {
    target: apiTarget.replace(/^http/, "ws"),
    ws: true,
  },
};

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    allowedHosts: ["vortax.cursar.space", "vortax-api.cursar.space"],
    proxy,
  },
  preview: {
    host: "0.0.0.0",
    port: 5173,
    allowedHosts: ["vortax.cursar.space", "vortax-api.cursar.space"],
    proxy,
  },
});
