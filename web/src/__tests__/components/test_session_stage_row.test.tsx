import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  SESSION_STAGES,
  SessionStageRow,
  sessionStageColor,
  sessionStageId,
  UNASSIGNED_STAGE_ID,
} from "@/components/ui/session-stage-row";

const EMPTY_BUCKETS = {
  [UNASSIGNED_STAGE_ID]: { sessionCount: 0, issueCount: 0 },
  ...Object.fromEntries(SESSION_STAGES.map((s) => [s.id, { sessionCount: 0, issueCount: 0 }])),
};

describe("sessionStageId", () => {
  it("maps the canonical lifecycle states to themselves", () => {
    expect(sessionStageId("planned")).toBe("planned");
    expect(sessionStageId("queued")).toBe("queued");
    expect(sessionStageId("executing")).toBe("executing");
    expect(sessionStageId("in_review")).toBe("in_review");
    expect(sessionStageId("verified")).toBe("verified");
    expect(sessionStageId("completed")).toBe("completed");
  });

  it("collapses richer enum states into the canonical 6", () => {
    // The backend enum has 13 values; the dashboard groups them.
    expect(sessionStageId("active")).toBe("executing");
    expect(sessionStageId("waiting_for_ci")).toBe("executing");
    expect(sessionStageId("waiting_for_review")).toBe("executing");
    expect(sessionStageId("waiting_for_deploy")).toBe("executing");
    expect(sessionStageId("re_engaged")).toBe("in_review");
  });

  it("collapses failed/paused/abandoned into the off_track stage", () => {
    // Off-track sessions belong on the dashboard — they're some of
    // the most important states for a PM to see. They also surface
    // via the attention queue, but the row stays the primary view.
    expect(sessionStageId("failed")).toBe("off_track");
    expect(sessionStageId("paused")).toBe("off_track");
    expect(sessionStageId("abandoned")).toBe("off_track");
  });

  it("returns null for null/undefined and genuinely unknown states", () => {
    expect(sessionStageId(null)).toBeNull();
    expect(sessionStageId(undefined)).toBeNull();
    expect(sessionStageId("never-heard-of-this")).toBeNull();
  });
});

describe("sessionStageColor", () => {
  it("returns the stage's color for canonical states", () => {
    expect(sessionStageColor("executing")).toBe("#c83d2e");
    expect(sessionStageColor("verified")).toBe("#2d5a3d");
  });

  it("returns the same color across the collapsed group", () => {
    // Since `active` collapses to `executing`, both share the
    // executing colour — keeps the right-column pill consistent
    // with the top card's stripe.
    expect(sessionStageColor("active")).toBe(sessionStageColor("executing"));
  });

  it("returns the off-track ochre for failed/paused/abandoned", () => {
    // These all collapse to off_track and share its colour so the
    // pill stays visually distinct from the in-flow stages.
    expect(sessionStageColor("failed")).toBe("#b8741a");
    expect(sessionStageColor("paused")).toBe("#b8741a");
    expect(sessionStageColor("abandoned")).toBe("#b8741a");
  });
});

describe("SessionStageRow", () => {
  afterEach(() => cleanup());

  it("renders 8 cards (1 unassigned + 7 stages including off-track)", () => {
    render(
      <SessionStageRow buckets={EMPTY_BUCKETS} selected={new Set()} onStageClick={() => {}} />,
    );
    // Each card has an aria-label of the form "Filter to <label> ..."
    const buttons = screen.getAllByRole("button");
    expect(buttons.length).toBe(8);
  });

  it("renders the issue count for the unassigned card and session+issue counts for stage cards", () => {
    const buckets = {
      ...EMPTY_BUCKETS,
      [UNASSIGNED_STAGE_ID]: { sessionCount: 0, issueCount: 4 },
      executing: { sessionCount: 3, issueCount: 7 },
    };
    render(<SessionStageRow buckets={buckets} selected={new Set()} onStageClick={() => {}} />);
    // Unassigned: shows the issue count as the big number (no
    // sessions exist for unassigned issues — that's the whole
    // point).
    const unassigned = screen.getByLabelText(/Filter to unassigned \(0 sessions, 4 issues\)/);
    expect(unassigned).toBeInTheDocument();
    // Stage cards show "N sess · M iss" beneath the big session count.
    expect(screen.getByText("3 sess · 7 iss")).toBeInTheDocument();
  });

  it("marks selected cards with aria-pressed", () => {
    render(
      <SessionStageRow
        buckets={EMPTY_BUCKETS}
        selected={new Set(["executing"])}
        onStageClick={() => {}}
      />,
    );
    const executing = screen.getByLabelText(/Filter to executing/);
    expect(executing).toHaveAttribute("aria-pressed", "true");
    const verified = screen.getByLabelText(/Filter to verified/);
    expect(verified).toHaveAttribute("aria-pressed", "false");
  });

  it("fires onStageClick with additive=false for plain clicks", () => {
    const onStageClick = vi.fn();
    render(
      <SessionStageRow buckets={EMPTY_BUCKETS} selected={new Set()} onStageClick={onStageClick} />,
    );
    fireEvent.click(screen.getByLabelText(/Filter to executing/));
    expect(onStageClick).toHaveBeenCalledWith("executing", false);
  });

  it("fires onStageClick with additive=true when meta or ctrl key is held", () => {
    const onStageClick = vi.fn();
    render(
      <SessionStageRow buckets={EMPTY_BUCKETS} selected={new Set()} onStageClick={onStageClick} />,
    );
    fireEvent.click(screen.getByLabelText(/Filter to executing/), { metaKey: true });
    expect(onStageClick).toHaveBeenCalledWith("executing", true);
    fireEvent.click(screen.getByLabelText(/Filter to review/), { ctrlKey: true });
    expect(onStageClick).toHaveBeenCalledWith("in_review", true);
  });
});
