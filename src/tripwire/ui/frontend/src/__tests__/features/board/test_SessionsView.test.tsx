import { cleanup, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { SessionsView } from "@/features/board/SessionsView";
import type { SessionSummary } from "@/lib/api/endpoints/sessions";
import { renderWithProviders } from "../../test-utils";

afterEach(() => cleanup());

function makeSession(overrides: Partial<SessionSummary>): SessionSummary {
  return {
    id: "s",
    name: "session",
    agent: "frontend-coder",
    status: "executing",
    issues: [],
    estimated_size: null,
    blocked_by_sessions: [],
    repos: [],
    current_state: null,
    re_engagement_count: 0,
    task_progress: { done: 0, total: 0 },
    ...overrides,
  };
}

describe("SessionsView", () => {
  it("renders all 6 in-flow columns plus off-track when there are off-track sessions", () => {
    renderWithProviders(
      <SessionsView
        sessions={[
          makeSession({ id: "p", status: "planned" }),
          makeSession({ id: "q", status: "queued" }),
          makeSession({ id: "e", status: "executing" }),
          makeSession({ id: "r", status: "in_review" }),
          makeSession({ id: "v", status: "verified" }),
          makeSession({ id: "c", status: "completed" }),
          makeSession({ id: "f", status: "failed" }),
          makeSession({ id: "a", status: "abandoned" }),
        ]}
        blockedInbox={{ bySession: new Map(), byIssue: new Map(), ready: true }}
        onCardClick={() => {}}
        onCrossLinkClick={() => {}}
        activeStages={null}
      />,
    );
    for (const col of [
      "planned",
      "queued",
      "executing",
      "review",
      "verified",
      "completed",
      "off-track",
    ]) {
      expect(screen.getByRole("region", { name: new RegExp(col, "i") })).toBeInTheDocument();
    }
  });

  it("places sessions into the correct column by canonical stage", () => {
    renderWithProviders(
      <SessionsView
        sessions={[
          makeSession({ id: "active-x", status: "active" }),
          makeSession({ id: "review-y", status: "in_review" }),
          makeSession({ id: "queued-z", status: "queued" }),
        ]}
        blockedInbox={{ bySession: new Map(), byIssue: new Map(), ready: true }}
        onCardClick={() => {}}
        onCrossLinkClick={() => {}}
        activeStages={null}
      />,
    );
    // `active` collapses to the executing stage per sessionStageId().
    const exec = screen.getByRole("region", { name: /executing/i });
    expect(within(exec).getByText("active-x")).toBeInTheDocument();
    const review = screen.getByRole("region", { name: /^review/i });
    expect(within(review).getByText("review-y")).toBeInTheDocument();
  });

  it("keeps off-track sessions visible when a stage filter is active", () => {
    // Per dec-attention-leverage-frame, off-track sessions must
    // surface regardless of filter — they're exactly what a PM
    // needs to see and the filter pill shouldn't hide them.
    renderWithProviders(
      <SessionsView
        sessions={[
          makeSession({ id: "exec", status: "executing" }),
          makeSession({ id: "fail", status: "failed" }),
        ]}
        blockedInbox={{ bySession: new Map(), byIssue: new Map(), ready: true }}
        onCardClick={() => {}}
        onCrossLinkClick={() => {}}
        // Filter is set to a stage that excludes both — but off-track
        // is not affected by stage filter selection.
        activeStages={new Set(["planned"])}
      />,
    );
    expect(screen.queryByText("exec")).not.toBeInTheDocument();
    expect(screen.getByText("fail")).toBeInTheDocument();
  });
});
