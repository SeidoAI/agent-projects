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
    new Response(JSON.stringify({ id: "n1", layout: { x: 1, y: 2 } }), {
      status: 200,
      headers: { "content-type": "application/json" },
    }),
  );
}

describe("useLayoutPersistence", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("flush() PATCHes the latest position per node", async () => {
    const fetchSpy = mockFetch();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result } = renderHook(() => useLayoutPersistence("p1"), {
      wrapper: wrapperWith(qc),
    });

    await act(async () => {
      result.current.persist({ "user-model": { x: 10, y: 20 } });
      result.current.persist({ "user-model": { x: 11, y: 21 } });
      result.current.persist({ "user-model": { x: 12, y: 22 } });
      await result.current.flush();
    });

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSpy.mock.calls[0] ?? [];
    expect(url).toBe("/api/projects/p1/nodes/user-model/layout");
    expect(init?.method).toBe("PATCH");
    expect(JSON.parse(String(init?.body))).toEqual({ x: 12, y: 22 });
  });

  it("flush() emits one PATCH per distinct node id", async () => {
    const fetchSpy = mockFetch();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result } = renderHook(() => useLayoutPersistence("p1"), {
      wrapper: wrapperWith(qc),
    });

    await act(async () => {
      result.current.persist({
        "user-model": { x: 1, y: 1 },
        "auth-flow": { x: 2, y: 2 },
      });
      await result.current.flush();
    });

    expect(fetchSpy).toHaveBeenCalledTimes(2);
    const urls = fetchSpy.mock.calls.map((c) => String(c[0])).sort();
    expect(urls).toEqual([
      "/api/projects/p1/nodes/auth-flow/layout",
      "/api/projects/p1/nodes/user-model/layout",
    ]);
  });

  it("flushes any pending batch on unmount (PM #25 P1)", async () => {
    // Regression: if the user navigates away within the debounce
    // window after a position change, the pending PATCH must still
    // hit the wire — otherwise the YAML never gets written and the
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

    // Unmount before the debounce timer fires — but the cleanup
    // hook must still flush the pending batch.
    await act(async () => {
      unmount();
      // Let the flushed promise resolve before assertions.
      await Promise.resolve();
    });

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSpy.mock.calls[0] ?? [];
    expect(url).toBe("/api/projects/p1/nodes/user-model/layout");
    expect(JSON.parse(String(init?.body))).toEqual({ x: 7, y: 8 });
  });

  it("debounces auto-flush — repeated persists collapse into one PATCH per node", async () => {
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
      // Before the debounce window ends, no PATCH yet.
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

      // Cross the debounce threshold from the most recent persist.
      await act(async () => {
        vi.advanceTimersByTime(500);
        await Promise.resolve();
      });
      expect(fetchSpy).toHaveBeenCalledTimes(1);
      const init = fetchSpy.mock.calls[0]?.[1];
      expect(JSON.parse(String(init?.body))).toEqual({ x: 9, y: 9 });
    } finally {
      vi.useRealTimers();
    }
  });
});
