import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";
import { fileURLToPath } from "node:url";

const dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(dirname, "src") },
  },
  server: {
    port: 5173,
    host: true, // Listen on all local IPs (0.0.0.0) so phone can access
    allowedHosts: true, // Allow Cloudflare tunnel and LAN hostnames
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true, ws: true },
      "/companion": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
});
