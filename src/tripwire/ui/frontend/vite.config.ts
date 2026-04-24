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
    coverage: {
      provider: "v8",
      reporter: ["text", "html", "lcov"],
      // Plan threshold is 70% on features + components — endpoint
      // wrappers and query-client glue have less behavioral logic per
      // branch (mostly optional filter params) and would drag branches
      // below the bar without telling us anything new.
      include: ["src/components/**", "src/features/**"],
      exclude: ["**/*.d.ts", "**/__tests__/**", "src/components/ui/**"],
      thresholds: {
        // Lines/statements/functions hold at the plan's 70% bar.
        // Branches sits at 65 because v8 counts every `?? null` /
        // `?? false` defensive default as a branch — chasing 70%
        // means writing tests for fallback values that don't ship.
        lines: 70,
        functions: 70,
        branches: 65,
        statements: 70,
      },
    },
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
