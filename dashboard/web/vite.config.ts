import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Relative base + no module-preload polyfill => the built index.html has NO
// inline <script>, so CSP `script-src 'self'` holds. All assets same-origin.
export default defineConfig({
  base: "./",
  plugins: [react()],
  build: {
    outDir: "dist",
    assetsDir: "assets",
    target: "es2020",
    sourcemap: false,
    modulePreload: { polyfill: false },
    cssCodeSplit: false,
  },
  server: {
    port: 5173,
    // Fail loudly if the port is taken rather than drifting to another one.
    strictPort: true,
    proxy: {
      // 127.0.0.1, never "localhost". This Node resolves localhost to ::1
      // first and does not fall back, while the backend listens on IPv4 only —
      // so "localhost" here makes every proxied request fail with ECONNREFUSED
      // and the dashboard sits permanently offline while its shell loads fine.
      "/ws": {
        target: "ws://127.0.0.1:8081",
        ws: true,
      },
      "/healthz": "http://127.0.0.1:8081",
      "/auth": "http://127.0.0.1:8081",
      // The standalone debug page is rendered by the backend, so proxying it
      // puts it on the same origin the operator already has open.
      "/debug.html": "http://127.0.0.1:8081",
    },
  },
});
