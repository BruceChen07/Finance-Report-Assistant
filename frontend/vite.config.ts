import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

/**
 * Vite config:
 * - Dev server proxies backend paths to FastAPI (avoid CORS issues).
 * - Test coverage thresholds enforce >= 80% (basic quality gate).
 */
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/health": "http://127.0.0.1:8000",
      "/docs": "http://127.0.0.1:8000",
      "/openapi.json": "http://127.0.0.1:8000"
    }
  },
  build: {
    sourcemap: false
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    coverage: {
      provider: "v8",
      reporter: ["text", "html"],
      lines: 80,
      functions: 80,
      statements: 80,
      branches: 70
    }
  }
});

