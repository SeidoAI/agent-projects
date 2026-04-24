import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { type RenderOptions, type RenderResult, render } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

/**
 * Build a QueryClient with the same defaults every test wants:
 * no retries (so a 404 fixture doesn't spin into 3 attempts), and
 * `staleTime: Infinity` (so background refetches don't fire while
 * the test is asserting against the rendered output).
 *
 * Exported because some tests need to write into the cache before
 * mount (`qc.setQueryData(...)`).
 */
export function makeTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
  });
}

export interface RenderWithProvidersOptions extends Omit<RenderOptions, "wrapper"> {
  /** Pre-existing client; defaults to `makeTestQueryClient()`. */
  queryClient?: QueryClient;
  /** Single entry path to seed `MemoryRouter`; default `"/"`. */
  initialPath?: string;
  /** Optional route pattern — defaults to wrapping `ui` in a wildcard. */
  routePath?: string;
}

export interface RenderWithProvidersResult extends RenderResult {
  queryClient: QueryClient;
}

/**
 * Render `ui` inside the provider stack every test needs:
 * QueryClientProvider + MemoryRouter pinned at `initialPath`.
 *
 * If `routePath` is supplied, `ui` is mounted under that route so
 * components calling `useParams()` see the path params from
 * `initialPath`. If omitted, `ui` is rendered at the root and the
 * caller is responsible for any nested Routes.
 *
 * Returns the standard RTL result PLUS the `queryClient` so the
 * test can `setQueryData(...)` after mount or assert cache writes.
 */
export function renderWithProviders(
  ui: ReactElement,
  options: RenderWithProvidersOptions = {},
): RenderWithProvidersResult {
  const {
    queryClient = makeTestQueryClient(),
    initialPath = "/",
    routePath,
    ...rtlOptions
  } = options;

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[initialPath]}>
          {routePath ? (
            <Routes>
              <Route path={routePath} element={children} />
            </Routes>
          ) : (
            children
          )}
        </MemoryRouter>
      </QueryClientProvider>
    );
  }

  const result = render(ui, { wrapper: Wrapper, ...rtlOptions });
  return Object.assign(result, { queryClient });
}
