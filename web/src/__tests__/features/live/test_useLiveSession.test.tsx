import { QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it } from "vitest";

import { useLiveSession } from "@/features/live/useLiveSession";
import type { EventsResponse, ProcessEvent } from "@/lib/api/endpoints/events";
import type { InboxItem } from "@/lib/api/endpoints/inbox";
import { queryKeys } from "@/lib/api/queryKeys";
import { makeSessionDetail } from "../../mocks/fixtures";
import { makeTestQueryClient } from "../../test-utils";

afterEach(() => {});

function withClient(client = makeTestQueryClient()) {
  return {
    client,
    wrapper: ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    ),
  };
}

describe("useLiveSession", () => {
  it("returns session, off-track flag, and surfaces JIT prompt fires + cost-approval entry", async () => {
    const { client, wrapper } = withClient();

    // Seed the session as `executing` (in-flow).
    client.setQueryData(
      queryKeys.session("p1", "v08-foo"),
      makeSessionDetail({
        id: "v08-foo",
        status: "executing",
        cost_usd: 1.234,
      }),
    );

    // JIT-prompt-fire events scoped to this session, plus an unrelated
    // event that must NOT appear in the filtered list.
    const fire: ProcessEvent = {
      id: "ev-1",
      kind: "jit_prompt_fire",
      fired_at: "2026-04-28T10:00:00Z",
      session_id: "v08-foo",
      jit_prompt_id: "no-merge-without-self-review",
    };
    const otherFire: ProcessEvent = {
      id: "ev-2",
      kind: "jit_prompt_fire",
      fired_at: "2026-04-28T10:01:00Z",
      session_id: "other-sess",
      jit_prompt_id: "x",
    };
    const eventsResp: EventsResponse = {
      events: [fire, otherFire],
      next_cursor: null,
    };
    client.setQueryData(queryKeys.events("p1", { session_id: "v08-foo" }), eventsResp);

    // One open `cost-approval` blocked-bucket entry referencing this session.
    const inboxEntries: InboxItem[] = [
      {
        id: "inbox-1",
        bucket: "blocked",
        title: "approve $0.05 cost overrun for v08-foo",
        body: "",
        author: "pm-agent",
        created_at: "2026-04-28T10:30:00Z",
        references: [{ session: "v08-foo" }],
        escalation_reason: "cost-approval",
        resolved: false,
        resolved_at: null,
        resolved_by: null,
      },
      {
        id: "inbox-2",
        bucket: "blocked",
        title: "different concern",
        body: "",
        author: "pm-agent",
        created_at: "2026-04-28T10:31:00Z",
        references: [{ session: "v08-foo" }],
        escalation_reason: "scope-clarification",
        resolved: false,
        resolved_at: null,
        resolved_by: null,
      },
    ];
    client.setQueryData(
      queryKeys.inboxFiltered("p1", { bucket: "blocked", resolved: false }),
      inboxEntries,
    );

    const { result } = renderHook(() => useLiveSession("p1", "v08-foo"), {
      wrapper,
    });

    await waitFor(() => expect(result.current.session).not.toBeUndefined());

    expect(result.current.session?.id).toBe("v08-foo");
    expect(result.current.session?.cost_usd).toBe(1.234);
    expect(result.current.isOffTrack).toBe(false);
    // Only the JIT prompt fire scoped to *this* session should be returned.
    expect(result.current.jitPromptFires.map((e) => e.id)).toEqual(["ev-1"]);
    // The cost-approval entry must surface; the other blocked entry
    // (different escalation_reason) must not.
    expect(result.current.costApprovalEntry?.id).toBe("inbox-1");
  });

  it("flags isOffTrack when status is paused / failed / abandoned", async () => {
    const { client, wrapper } = withClient();
    client.setQueryData(
      queryKeys.session("p1", "v08-foo"),
      makeSessionDetail({ id: "v08-foo", status: "paused" }),
    );

    const { result } = renderHook(() => useLiveSession("p1", "v08-foo"), {
      wrapper,
    });

    await waitFor(() => expect(result.current.session).not.toBeUndefined());
    expect(result.current.isOffTrack).toBe(true);
  });

  it("returns null cost-approval entry when none exists for this session", async () => {
    const { client, wrapper } = withClient();
    client.setQueryData(
      queryKeys.session("p1", "v08-foo"),
      makeSessionDetail({ id: "v08-foo", status: "executing" }),
    );
    client.setQueryData(queryKeys.inboxFiltered("p1", { bucket: "blocked", resolved: false }), [
      {
        id: "inbox-3",
        bucket: "blocked",
        title: "for a different session",
        body: "",
        author: "pm-agent",
        created_at: "2026-04-28T10:00:00Z",
        references: [{ session: "other-sess" }],
        escalation_reason: "cost-approval",
        resolved: false,
        resolved_at: null,
        resolved_by: null,
      },
    ] satisfies InboxItem[]);

    const { result } = renderHook(() => useLiveSession("p1", "v08-foo"), {
      wrapper,
    });

    await waitFor(() => expect(result.current.session).not.toBeUndefined());
    expect(result.current.costApprovalEntry).toBeNull();
  });
});
