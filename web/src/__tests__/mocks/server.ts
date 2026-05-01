import { setupServer } from "msw/node";

import { defaultHandlers } from "./handlers";

/**
 * One shared MSW server for every test. Lifecycle (listen / reset /
 * close) is wired in `src/__tests__/setup.ts`.
 *
 * `onUnhandledRequest: "error"` is enforced there too — any request
 * the suite makes that no handler matches becomes a hard failure,
 * which is the whole reason MSW beats stub-level fetch mocks: a
 * typo in a URL no longer silently returns `undefined`.
 */
export const server = setupServer(...defaultHandlers);
