import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, render, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { WebSocketClient } from "@/lib/realtime/websocketClient";

const clients: Array<{
  url: string;
  client: WebSocketClient;
  onEvent: (event: unknown) => void;
  onStatusChange?: (status: string) => void;
  onReconnect?: () => void;
  close: ReturnType<typeof vi.fn>;
}> = [];

vi.mock("@/lib/realtime/websocketClient", () => {
  return {
    createWebSocketClient: (opts: {
      url: string;
      onEvent: (ev: unknown) => void;
      onStatusChange?: (status: string) => void;
      onReconnect?: () => void;
    }) => {
      const close = vi.fn();
      const client = {
        close,
        getStatus: () => "connecting" as const,
      };
      clients.push({
        url: opts.url,
        client,
        onEvent: opts.onEvent,
        onStatusChange: opts.onStatusChange,
        onReconnect: opts.onReconnect,
        close,
      });
      return client;
    },
  };
});

async function loadHook() {
  const mod = await import("@/lib/realtime/useProjectWebSocket");
  return mod;
}

function wrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient();
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

describe("useProjectWebSocket", () => {
  beforeEach(async () => {
    vi.useFakeTimers();
    clients.length = 0;
    const { __resetProjectWebSocketsForTests } = await loadHook();
    __resetProjectWebSocketsForTests();
  });

  afterEach(async () => {
    cleanup();
    const { __resetProjectWebSocketsForTests } = await loadHook();
    __resetProjectWebSocketsForTests();
    vi.runOnlyPendingTimers();
    vi.useRealTimers();
  });

  it("opens one socket per project id and closes it on unmount", async () => {
    const { useProjectWebSocket } = await loadHook();
    const { unmount } = renderHook(() => useProjectWebSocket("p1"), { wrapper });
    expect(clients).toHaveLength(1);
    expect(clients[0]?.url).toContain("project=p1");

    unmount();
    expect(clients[0]?.close).not.toHaveBeenCalled();
    act(() => {
      vi.advanceTimersByTime(50);
    });
    expect(clients[0]?.close).toHaveBeenCalledTimes(1);
  });

  it("shares a single socket across concurrent mounts for the same project", async () => {
    const { useProjectWebSocket } = await loadHook();

    function Child({ pid }: { pid: string }) {
      useProjectWebSocket(pid);
      return null;
    }

    const { unmount } = render(
      <QueryClientProvider client={new QueryClient()}>
        <Child pid="p1" />
        <Child pid="p1" />
      </QueryClientProvider>,
    );

    expect(clients).toHaveLength(1);
    unmount();
    expect(clients[0]?.close).not.toHaveBeenCalled();
    act(() => {
      vi.advanceTimersByTime(50);
    });
    expect(clients[0]?.close).toHaveBeenCalledTimes(1);
  });

  it("keeps the socket through a StrictMode-style immediate remount", async () => {
    const { useProjectWebSocket } = await loadHook();

    const first = renderHook(() => useProjectWebSocket("p1"), { wrapper });
    expect(clients).toHaveLength(1);

    first.unmount();
    expect(clients[0]?.close).not.toHaveBeenCalled();

    const second = renderHook(() => useProjectWebSocket("p1"), { wrapper });
    expect(clients).toHaveLength(1);

    act(() => {
      vi.advanceTimersByTime(50);
    });
    expect(clients[0]?.close).not.toHaveBeenCalled();

    second.unmount();
    act(() => {
      vi.advanceTimersByTime(50);
    });
    expect(clients[0]?.close).toHaveBeenCalledTimes(1);
  });

  it("opens a separate socket per project id", async () => {
    const { useProjectWebSocket } = await loadHook();

    function Child({ pid }: { pid: string }) {
      useProjectWebSocket(pid);
      return null;
    }

    render(
      <QueryClientProvider client={new QueryClient()}>
        <Child pid="p1" />
        <Child pid="p2" />
      </QueryClientProvider>,
    );

    const urls = clients.map((c) => c.url);
    expect(urls.some((u) => u.includes("project=p1"))).toBe(true);
    expect(urls.some((u) => u.includes("project=p2"))).toBe(true);
    expect(clients).toHaveLength(2);
  });

  it("propagates status transitions from the underlying client", async () => {
    const { useProjectWebSocket } = await loadHook();
    const { result } = renderHook(() => useProjectWebSocket("p1"), { wrapper });

    expect(result.current.status).toBe("connecting");

    act(() => {
      clients[0]?.onStatusChange?.("open");
    });
    expect(result.current.status).toBe("open");

    act(() => {
      clients[0]?.onStatusChange?.("error");
    });
    expect(result.current.status).toBe("error");
  });

  it("invalidates every cached query on reconnect", async () => {
    const { useProjectWebSocket } = await loadHook();
    const queryClient = new QueryClient();
    const invalidateAll = vi.spyOn(queryClient, "invalidateQueries");

    function CustomWrapper({ children }: { children: ReactNode }) {
      return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
    }

    renderHook(() => useProjectWebSocket("p1"), { wrapper: CustomWrapper });
    expect(invalidateAll).not.toHaveBeenCalled();

    act(() => {
      clients[0]?.onReconnect?.();
    });
    // No-arg invalidate → all queries (catch up after a dropped connection).
    expect(invalidateAll).toHaveBeenCalledWith();
  });
});
