import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig, devices } from "@playwright/test";

const webRoot = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(webRoot, "..");
const fixtureProject = path.join(repoRoot, "tests/fixtures/ui-e2e-project");
const backendPort = Number(process.env.PLAYWRIGHT_BACKEND_PORT ?? 43101);
const frontendPort = Number(process.env.PLAYWRIGHT_FRONTEND_PORT ?? 43100);

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  expect: { timeout: 7_500 },
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["list"]] : "list",
  use: {
    baseURL: `http://127.0.0.1:${frontendPort}`,
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: [
    {
      command: `uv run tripwire ui --project-dir ${fixtureProject} --port ${backendPort} --no-browser --dev`,
      cwd: fixtureProject,
      url: `http://127.0.0.1:${backendPort}/api/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
    {
      command: `VITE_BACKEND_PORT=${backendPort} VITE_DEV_PORT=${frontendPort} npm run dev -- --host 127.0.0.1`,
      cwd: webRoot,
      url: `http://127.0.0.1:${frontendPort}/`,
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
  ],
});
