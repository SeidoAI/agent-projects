import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import React from "react";
import { describe, expect, it } from "vitest";

import { useSessionEvents } from "@/lib/api/endpoints/events";

import { server } from "../mocks/server";

function wrapper(qc: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return React.createElement(QueryClientProvider, { client: qc }, children);
  };
}

describe("useSessionEvents", () => {
  it("requests /api/projects/<pid>/events with session_id param", async () => {
    // Hold the captured URL inside a wrapping object — TS narrows
    // a `let foo: URL | null = null` to `null` since it can't see
    // the closure-mutation. Wrapping defeats that narrowing.
    const captured: { url: URL | null } = { url: null };
    server.use(
      http.get("/api/projects/p1/events", ({ request }) => {
        captured.url = new URL(request.url);
        return HttpResponse.json({ events: [], next_cursor: null });
      }),
    );

    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const { result } = renderHook(() => useSessionEvents("p1", "sess-a"), {
      wrapper: wrapper(qc),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(captured.url).not.toBeNull();
    expect(captured.url?.searchParams.get("session_id")).toBe("sess-a");
  });

  it("forwards `kinds` as repeated `kind` params and includes them in the cache key", async () => {
    let kinds: string[] = [];
    server.use(
      http.get("/api/projects/p1/events", ({ request }) => {
        kinds = new URL(request.url).searchParams.getAll("kind");
        return HttpResponse.json({ events: [], next_cursor: null });
      }),
    );

    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const { result } = renderHook(
      () =>
        useSessionEvents("p1", "sess-a", {
          kinds: ["tripwire_fire", "validator_fail"],
        }),
      { wrapper: wrapper(qc) },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(kinds).toEqual(["tripwire_fire", "validator_fail"]);
  });
});
