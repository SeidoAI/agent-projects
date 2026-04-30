import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useLayoutPersistence } from "@/features/graph/useLayoutPersistence";

function wrapperWith(qc: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

function mockFetch() {
  return vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ layouts: {} }), {
      status: 200,
      headers: { "content-type": "application/json" },
    }),
  );
}

function bodyOf(call: unknown[] | undefined): Record<string, { x: number; y: number }> {
  const init = call?.[1] as RequestInit | undefined;
  return JSON.parse(String(init?.body)) as Record<string, { x: number; y: number }>;
}

describe("useLayoutPersistence", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("flush() sends a single batched PATCH carrying every distinct node id", async () => {
    const fetchSpy = mockFetch();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result } = renderHook(() => useLayoutPersistence("p1"), {
      wrapper: wrapperWith(qc),
    });

    await act(async () => {
      result.current.persist({
        "user-model": { x: 10, y: 20 },
        "auth-flow": { x: 1, y: 2 },
      });
      result.current.persist({ "user-model": { x: 12, y: 22 } });
      await result.current.flush();
    });

    // Exactly one HTTP call — not one per node.
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSpy.mock.calls[0] ?? [];
    expect(url).toBe("/api/projects/p1/graph/concept/layout");
    expect(init?.method).toBe("PATCH");
    expect(bodyOf(fetchSpy.mock.calls[0])).toEqual({
      // Only the latest position per node survives in the batch.
      "user-model": { x: 12, y: 22 },
      "auth-flow": { x: 1, y: 2 },
    });
  });

  it("flush() with an empty buffer is a no-op (no HTTP call)", async () => {
    const fetchSpy = mockFetch();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result } = renderHook(() => useLayoutPersistence("p1"), {
      wrapper: wrapperWith(qc),
    });

    await act(async () => {
      await result.current.flush();
    });

    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("flushes any pending batch on unmount (PM #25 P1)", async () => {
    // Regression: if the user navigates away within the debounce
    // window after a position change, the pending PATCH must still
    // hit the wire — otherwise the sidecar never gets written and the
    // next page load re-runs d3-force as if nothing was saved.
    const fetchSpy = mockFetch();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result, unmount } = renderHook(() => useLayoutPersistence("p1"), {
      wrapper: wrapperWith(qc),
    });

    act(() => {
      result.current.persist({ "user-model": { x: 7, y: 8 } });
    });
    expect(fetchSpy).not.toHaveBeenCalled();

    await act(async () => {
      unmount();
      await Promise.resolve();
    });

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url] = fetchSpy.mock.calls[0] ?? [];
    expect(url).toBe("/api/projects/p1/graph/concept/layout");
    expect(bodyOf(fetchSpy.mock.calls[0])).toEqual({
      "user-model": { x: 7, y: 8 },
    });
  });

  it("flushes the buffered batch to the OLD project when projectId changes (PM #25 round 3 P1)", async () => {
    // Regression: React Router keeps the same component instance
    // for `/p/:projectId/graph` across project changes. A pending
    // batch buffered while on Project A must not be dispatched
    // against Project B if the user navigates inside the debounce
    // window. Approach: flush on projectId change so the OLD
    // project receives its own buffered positions, then clear.
    const fetchSpy = mockFetch();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result, rerender } = renderHook(
      ({ pid }: { pid: string }) => useLayoutPersistence(pid),
      { wrapper: wrapperWith(qc), initialProps: { pid: "proj-a" } },
    );

    act(() => {
      result.current.persist({ "user-model": { x: 1, y: 2 } });
    });
    expect(fetchSpy).not.toHaveBeenCalled();

    await act(async () => {
      rerender({ pid: "proj-b" });
      await Promise.resolve();
    });

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const url = String(fetchSpy.mock.calls[0]?.[0] ?? "");
    expect(url).toBe("/api/projects/proj-a/graph/concept/layout");
    const projBCalls = fetchSpy.mock.calls.filter((c) =>
      String(c[0]).startsWith("/api/projects/proj-b/"),
    );
    expect(projBCalls).toHaveLength(0);
  });

  it("debounces auto-flush — repeated persists collapse into one PATCH per debounce window", async () => {
    vi.useFakeTimers();
    try {
      const fetchSpy = mockFetch();
      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      const { result } = renderHook(() => useLayoutPersistence("p1"), {
        wrapper: wrapperWith(qc),
      });

      act(() => {
        result.current.persist({ "user-model": { x: 1, y: 1 } });
      });
      act(() => {
        vi.advanceTimersByTime(500);
      });
      expect(fetchSpy).not.toHaveBeenCalled();

      act(() => {
        result.current.persist({ "user-model": { x: 9, y: 9 } });
      });
      // Total elapsed > original debounce, but the second persist
      // restarted the timer — still no PATCH yet.
      act(() => {
        vi.advanceTimersByTime(1200);
      });
      expect(fetchSpy).not.toHaveBeenCalled();

      await act(async () => {
        vi.advanceTimersByTime(500);
        await Promise.resolve();
      });
      expect(fetchSpy).toHaveBeenCalledTimes(1);
      expect(bodyOf(fetchSpy.mock.calls[0])).toEqual({
        "user-model": { x: 9, y: 9 },
      });
    } finally {
      vi.useRealTimers();
    }
  });
});
