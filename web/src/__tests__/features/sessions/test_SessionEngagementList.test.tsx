import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { SessionEngagementList } from "@/features/sessions/SessionEngagementList";
import type { Engagement } from "@/lib/api/endpoints/sessions";

afterEach(() => {
  cleanup();
});

describe("SessionEngagementList", () => {
  it("renders the empty-state hint when no engagements are recorded", () => {
    render(<SessionEngagementList engagements={[]} />);
    expect(screen.getByText(/no engagements recorded/i)).toBeInTheDocument();
  });

  it("renders one row per engagement with engagement number, started_at, and trigger", () => {
    const engagements: Engagement[] = [
      {
        engagement_id: "e1",
        started_at: "2026-04-26T12:00:00Z",
        ended_at: "2026-04-26T13:30:00Z",
        trigger: "spawn",
        outcome: "paused",
      },
      {
        engagement_id: "e2",
        started_at: "2026-04-27T09:00:00Z",
        ended_at: null,
        trigger: "re-engagement",
      },
    ];
    render(<SessionEngagementList engagements={engagements} />);

    // engagement number — 1-based, monotonic in array order
    expect(screen.getByText(/engagement #1/i)).toBeInTheDocument();
    expect(screen.getByText(/engagement #2/i)).toBeInTheDocument();

    // trigger surfaces on each row
    expect(screen.getByText(/spawn/i)).toBeInTheDocument();
    expect(screen.getByText(/re-engagement/i)).toBeInTheDocument();

    // started_at is rendered (we don't pin format, just substring)
    expect(screen.getByText(/2026-04-26/)).toBeInTheDocument();
    expect(screen.getByText(/2026-04-27/)).toBeInTheDocument();
  });

  it("marks an open engagement (no ended_at) as active", () => {
    const engagements: Engagement[] = [
      {
        engagement_id: "running",
        started_at: "2026-04-27T09:00:00Z",
        ended_at: null,
      },
    ];
    render(<SessionEngagementList engagements={engagements} />);
    // the "active" indicator is keyed by data attribute so the visual
    // can shift without breaking the test
    const row = screen.getByTestId("engagement-row-1");
    expect(row.getAttribute("data-active")).toBe("true");
  });

  it("renders duration when both timestamps are present", () => {
    const engagements: Engagement[] = [
      {
        engagement_id: "e1",
        started_at: "2026-04-26T12:00:00Z",
        ended_at: "2026-04-26T13:30:00Z",
        trigger: "spawn",
        outcome: "success",
      },
    ];
    render(<SessionEngagementList engagements={engagements} />);
    // 90 minutes — accept "1h 30m" or "90m" depending on impl
    expect(screen.getByTestId("engagement-row-1").textContent).toMatch(/1h 30m|90m/);
  });
});
