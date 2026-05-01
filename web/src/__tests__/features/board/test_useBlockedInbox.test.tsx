import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";

import { useBlockedInbox } from "@/features/board/hooks/useBlockedInbox";
import type { InboxItem } from "@/lib/api/endpoints/inbox";
import { queryKeys } from "@/lib/api/queryKeys";

function makeItem(overrides: Partial<InboxItem> = {}): InboxItem {
  return {
    id: `inb-${Math.random().toString(36).slice(2, 7)}`,
    bucket: "blocked",
    title: "test",
    body: "",
    author: "pm-agent",
    created_at: "2026-04-27T10:00:00Z",
    references: [],
    escalation_reason: null,
    resolved: false,
    resolved_at: null,
    resolved_by: null,
    ...overrides,
  };
}

function wrapper(qc: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

describe("useBlockedInbox", () => {
  it("indexes open blocked entries by session and issue id", async () => {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
    });
    qc.setQueryData(queryKeys.inboxFiltered("p1", { bucket: "blocked" }), [
      makeItem({
        id: "a",
        references: [{ session: "sess-1" }, { issue: "KUI-9" }],
      }),
      makeItem({ id: "b", references: [{ session: "sess-2" }] }),
      makeItem({ id: "c", resolved: true, references: [{ session: "sess-1" }] }),
    ]);

    const { result } = renderHook(() => useBlockedInbox("p1"), { wrapper: wrapper(qc) });
    await waitFor(() => {
      expect(result.current.ready).toBe(true);
    });
    // Resolved items are excluded — they no longer demand attention.
    expect(result.current.bySession.get("sess-1")?.map((i) => i.id)).toEqual(["a"]);
    expect(result.current.bySession.get("sess-2")?.map((i) => i.id)).toEqual(["b"]);
    expect(result.current.byIssue.get("KUI-9")?.map((i) => i.id)).toEqual(["a"]);
    expect(result.current.byIssue.get("nonexistent")).toBeUndefined();
  });

  it("returns empty maps before the inbox query resolves", () => {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
    });
    const { result } = renderHook(() => useBlockedInbox("p1"), { wrapper: wrapper(qc) });
    expect(result.current.ready).toBe(false);
    expect(result.current.bySession.size).toBe(0);
    expect(result.current.byIssue.size).toBe(0);
  });
});
