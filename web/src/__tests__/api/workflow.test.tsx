import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { useWorkflow, WORKFLOW_REFETCH_MS, workflowApi } from "@/lib/api/endpoints/workflow";
import { queryKeys } from "@/lib/api/queryKeys";

function mockFetch() {
  const res = {
    ok: true,
    status: 200,
    json: () =>
      Promise.resolve({
        project_id: "p1",
        workflows: [],
        registry: {
          tripwires: [],
          heuristics: [],
          jit_prompts: [],
          prompt_checks: [],
          commands: [],
          skills: [],
        },
        drift: { count: 0, findings: [] },
      }),
  } as Response;
  return vi.spyOn(globalThis, "fetch").mockResolvedValue(res);
}

describe("workflowApi.get — PM-mode header threading", () => {
  it("sends X-Tripwire-Role: pm when pmMode is true", async () => {
    const spy = mockFetch();
    await workflowApi.get("p1", { pmMode: true });
    expect(spy).toHaveBeenCalledWith(
      "/api/projects/p1/workflow",
      expect.objectContaining({
        method: "GET",
        headers: expect.objectContaining({ "X-Tripwire-Role": "pm" }),
      }),
    );
    spy.mockRestore();
  });

  it("does NOT send X-Tripwire-Role when pmMode is false / unset", async () => {
    const spy = mockFetch();
    await workflowApi.get("p1");
    const callArgs = spy.mock.calls[0];
    if (!callArgs) throw new Error("fetch was not called");
    const init = callArgs[1] as RequestInit;
    const headers = (init.headers ?? {}) as Record<string, string>;
    expect(headers["X-Tripwire-Role"]).toBeUndefined();
    spy.mockRestore();
  });
});

describe("queryKeys.workflow + pmMode separation", () => {
  it("PM and non-PM cache entries do not collide", () => {
    // The hook composes the cache key as
    //   [...queryKeys.workflow(pid), { pmMode }]
    // — assert the two variants differ so React Query caches them
    // independently.
    const base = queryKeys.workflow("p1");
    const pmKey = [...base, { pmMode: true }] as const;
    const defaultKey = [...base, { pmMode: false }] as const;
    expect(JSON.stringify(pmKey)).not.toBe(JSON.stringify(defaultKey));
  });
});

describe("useWorkflow — refresh path (Codex round-3 P1)", () => {
  it("registers a refetchInterval on the query observer (polling floor)", async () => {
    // Without an explicit refresh path the workflow view stays
    // stale forever (no refetchOnWindowFocus globally, no WS
    // handler before this round). The hook contract is:
    //  - polling floor at WORKFLOW_REFETCH_MS
    //  - fast path via WS invalidation in eventHandlers.ts
    // We assert the floor here; the WS path is asserted in
    // __tests__/lib/realtime/eventHandlers.test.ts.
    expect(WORKFLOW_REFETCH_MS).toBeGreaterThan(0);
    expect(WORKFLOW_REFETCH_MS).toBeLessThanOrEqual(60_000);

    mockFetch();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useWorkflow("p1"), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    // The active observer's options carry the same refetchInterval
    // we passed to useQuery. If a future PR drops it, this fails.
    const observers = qc
      .getQueryCache()
      .findAll({ queryKey: queryKeys.workflow("p1"), exact: false });
    const observed = observers.find((q) => q.observers.length > 0);
    if (!observed) throw new Error("no active observer for workflow query");
    const opts = observed.observers[0]?.options as { refetchInterval?: unknown };
    expect(opts.refetchInterval).toBe(WORKFLOW_REFETCH_MS);

    vi.restoreAllMocks();
  });
});
