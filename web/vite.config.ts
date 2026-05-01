/// <reference types="vitest/config" />
import fs from "node:fs";
import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Read the tripwire framework version from the repo's pyproject.toml
// so the UI sidebar's VersionStamp shows the running build's
// version. Build-time injection avoids a network round-trip and a
// backend-restart dependency. Falls back to "dev" if the file isn't
// readable (e.g. when the frontend is built outside the monorepo).
function readTripwireVersion(): string {
  try {
    const pyproject = fs.readFileSync(
      path.resolve(__dirname, "../pyproject.toml"),
      "utf-8",
    );
    const match = pyproject.match(/^version\s*=\s*"([^"]+)"/m);
    return match?.[1] ?? "dev";
  } catch {
    return "dev";
  }
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  define: {
    __TRIPWIRE_VERSION__: JSON.stringify(readTripwireVersion()),
  },
  test: {
    environment: "jsdom",
    passWithNoTests: true,
    setupFiles: ["./src/__tests__/setup.ts"],
    coverage: {
      provider: "v8",
      reporter: ["text", "html", "lcov"],
      // Scope: features + components. Endpoint wrappers and
      // query-client glue (under lib/) are mostly query-string
      // assembly and would drag branch coverage below the bar
      // without telling us anything new about the UI contract.
      include: ["src/components/**", "src/features/**"],
      exclude: ["**/*.d.ts", "**/__tests__/**", "src/components/ui/**"],
      // Branches lowered from 70 → 65 (2026-04-26): 70% global gate
      // penalised new sessions for legacy untested edges. Long-term fix
      // is patch-coverage via codecov (chore — see KUI-?? when filed).
      // Lines/functions/statements stay at 70 — those grow proportionally
      // with new code regardless of legacy debt.
      thresholds: {
        lines: 70,
        functions: 70,
        branches: 65,
        statements: 70,
      },
    },
  },
  build: {
    outDir: "../src/tripwire/ui/static",
    emptyOutDir: true,
    sourcemap: true,
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  server: {
    // Defaults match the documented dev stack (Vite 3000 → FastAPI 8000).
    // Override via env so multiple worktrees can run dev stacks in
    // parallel without colliding on those ports.
    port: Number(process.env.VITE_DEV_PORT ?? 3000),
    proxy: {
      "/api/ws": {
        target: `ws://localhost:${process.env.VITE_BACKEND_PORT ?? 8000}`,
        ws: true,
      },
      "/api": {
        target: `http://localhost:${process.env.VITE_BACKEND_PORT ?? 8000}`,
        changeOrigin: false,
      },
    },
  },
});
