import type { Page, TestInfo } from "@playwright/test";
import { expect } from "@playwright/test";

const VITE_NOISE = [/^\[vite\]/i];
const IMPORTANT_WARNINGS = [
  /Encountered two children with the same key/i,
  /WebSocket connection .* failed/i,
  /WebSocket is closed before the connection is established/i,
  /\[tripwire-ui\] unhandled/i,
];

export function installConsoleGuard(page: Page, testInfo: TestInfo) {
  const failures: string[] = [];

  page.on("console", (msg) => {
    const text = msg.text();
    if (VITE_NOISE.some((pattern) => pattern.test(text))) return;

    if (msg.type() === "error") {
      failures.push(`console.error: ${text}`);
      return;
    }

    if (msg.type() === "warning" && IMPORTANT_WARNINGS.some((pattern) => pattern.test(text))) {
      failures.push(`console.warn: ${text}`);
    }
  });

  page.on("pageerror", (err) => {
    failures.push(`pageerror: ${err.message}`);
  });

  page.on("response", (response) => {
    const status = response.status();
    if (status < 400) return;
    failures.push(`HTTP ${status}: ${response.url()}`);
  });

  return {
    async assertClean() {
      if (failures.length > 0) {
        await testInfo.attach("browser-console-and-network-failures", {
          body: failures.join("\n"),
          contentType: "text/plain",
        });
      }
      expect(failures).toEqual([]);
    },
  };
}
