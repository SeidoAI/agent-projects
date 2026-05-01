import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, expect } from "vitest";

import { server } from "./mocks/server";

// Auto-cleanup mounted React trees after every test. Vitest's
// `globals: false` config means RTL doesn't auto-register its own
// afterEach hook, so without this we accumulate DOM trees across
// tests inside a single file — which then breaks `getByText`/`getByTestId`
// with "Found multiple elements" when a second test renders the same
// component. One global hook here beats per-file `afterEach(cleanup)`
// boilerplate and unblocks legacy tests that lacked it.
afterEach(() => cleanup());

// MSW: intercept every fetch made by the frontend during tests.
// `onUnhandledRequest: "error"` makes any unhandled request a
// suite failure — that catches the wrong-URL / wrong-method bugs
// stub-level fetch mocks let through. Tests override the default
// handlers via `server.use(...)` for per-test scenarios.
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

// Radix UI primitives (DropdownMenu, Popover, Dialog) use pointer-capture
// APIs and scrollIntoView during open/close transitions; jsdom implements
// none of these. Patch with no-ops so fireEvent.click on a trigger actually
// opens the content in tests.
if (typeof Element !== "undefined") {
  if (!Element.prototype.hasPointerCapture) {
    Element.prototype.hasPointerCapture = () => false;
  }
  if (!Element.prototype.releasePointerCapture) {
    Element.prototype.releasePointerCapture = () => {};
  }
  if (!Element.prototype.setPointerCapture) {
    Element.prototype.setPointerCapture = () => {};
  }
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = () => {};
  }
  // SessionFlow + EventLog drive a programmatic scroll on mount via
  // `el.scrollTo(...)`; jsdom doesn't implement that on Element. The
  // patch makes the call a no-op so layout effects don't throw.
  if (!Element.prototype.scrollTo) {
    Element.prototype.scrollTo = () => {};
  }
}

// React Flow (ConceptGraph) and any future virtualised list call
// ResizeObserver at mount. jsdom doesn't ship one, so the suite
// installs a no-op stub once here instead of every test re-stubbing.
if (typeof globalThis.ResizeObserver === "undefined") {
  class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  globalThis.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver;
}

// Strict console spy: any unexpected `console.error` or
// `console.warn` (React act-warning, key warning, DOM-nesting
// warning, etc.) fails the test. We buffer messages during the
// test and assert in afterEach so the failure surfaces cleanly —
// throwing inside `console.error` itself gets swallowed by React's
// concurrent rendering recovery and the test silently passes.
//
// Tests that intentionally exercise the error path use
// `vi.spyOn(console, "error").mockImplementation(() => {})` to
// silence locally.
const consoleMessages: string[] = [];
const originalConsoleError = console.error.bind(console);
const originalConsoleWarn = console.warn.bind(console);
console.error = (...args: unknown[]) => {
  consoleMessages.push(`[error] ${formatArgs(args)}`);
  originalConsoleError(...args);
};
console.warn = (...args: unknown[]) => {
  consoleMessages.push(`[warn] ${formatArgs(args)}`);
  originalConsoleWarn(...args);
};

afterEach(() => {
  if (consoleMessages.length > 0) {
    const joined = consoleMessages.join("\n");
    consoleMessages.length = 0;
    expect.fail(`Unexpected console output during test:\n${joined}`);
  }
});

function formatArgs(args: unknown[]): string {
  return args
    .map((a) => {
      if (a instanceof Error) return a.stack ?? a.message;
      if (typeof a === "string") return a;
      try {
        return JSON.stringify(a);
      } catch {
        return String(a);
      }
    })
    .join(" ");
}
