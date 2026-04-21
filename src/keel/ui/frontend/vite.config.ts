/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  test: {
    environment: "jsdom",
    passWithNoTests: true,
    setupFiles: ["./src/__tests__/setup.ts"],
  },
  build: {
    outDir: "../static",
    emptyOutDir: true,
    sourcemap: true,
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  server: {
    port: 3000,
    proxy: {
      "/api/ws": {
        target: "ws://localhost:8000",
        ws: true,
      },
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: false,
      },
    },
  },
});
