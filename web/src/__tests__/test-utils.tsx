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
  /** Optional route pattern — when supplied, `ui` mounts under it so
   *  `useParams()` resolves the placeholders from `initialPath`. */
  routePath?: string;
  /** Extra `<Route>` siblings (back-nav stubs etc.). Ignored unless
   *  `routePath` is also supplied. */
  extraRoutes?: ReactNode;
  /** Wrap the rendered target in extra context providers
   *  (e.g., `TooltipProvider`). The wrapper sits between the route
   *  element and the test target. */
  wrap?: (target: ReactNode) => ReactElement;
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
 * `initialPath`. `extraRoutes` lets the test add sibling `<Route>`
 * stubs (a back-nav target, an "issue not found" landing page).
 *
 * `wrap(target)` lets the test layer extra providers (typically
 * `TooltipProvider` or `ErrorBoundary`) between the route element
 * and the test target without forcing every caller to construct a
 * full Wrapper component.
 *
 * Returns the standard RTL result PLUS the `queryClient` handle so
 * the test can `setQueryData(...)` after mount or assert cache
 * writes.
 */
export function renderWithProviders(
  ui: ReactElement,
  options: RenderWithProvidersOptions = {},
): RenderWithProvidersResult {
  const {
    queryClient = makeTestQueryClient(),
    initialPath = "/",
    routePath,
    extraRoutes,
    wrap,
    ...rtlOptions
  } = options;

  function Wrapper({ children }: { children: ReactNode }) {
    const target = wrap ? wrap(children) : children;
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[initialPath]}>
          {routePath ? (
            <Routes>
              <Route path={routePath} element={target} />
              {extraRoutes}
            </Routes>
          ) : (
            target
          )}
        </MemoryRouter>
      </QueryClientProvider>
    );
  }

  const result = render(ui, { wrapper: Wrapper, ...rtlOptions });
  return Object.assign(result, { queryClient });
}
