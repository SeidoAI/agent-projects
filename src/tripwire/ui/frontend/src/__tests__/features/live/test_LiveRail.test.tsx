import { cleanup, fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LiveRail } from "@/features/live/LiveRail";
import type { ProcessEvent } from "@/lib/api/endpoints/events";
import type { InboxItem } from "@/lib/api/endpoints/inbox";
import { renderWithProviders } from "../../test-utils";

afterEach(() => cleanup());

const baseProps = {
  projectId: "p1",
  sessionId: "v08-foo",
  status: "executing" as const,
  costUsd: 1.234,
  agentState: "drafting plan",
  tripwireFires: [] as ProcessEvent[],
  costApprovalEntry: null as InboxItem | null,
  onCostApprovalClick: vi.fn(),
};

describe("LiveRail — KUI-107 right rail", () => {
  it("formats the cost ticker with $ + tabular-nums and includes the running USD value", () => {
    renderWithProviders(<LiveRail {...baseProps} />);
    const ticker = screen.getByTestId("cost-ticker");
    expect(ticker).toHaveTextContent(/\$1\.23/);
    // Tabular-nums lives on the value span; assert via class so the
    // visual-stability requirement isn't quietly regressed.
    expect(ticker.className).toMatch(/tabular-nums/);
  });

  it("shows the agent's current state when present", () => {
    renderWithProviders(
      <LiveRail {...baseProps} agentState="awaiting validator: scope-clarity" />,
    );
    expect(screen.getByTestId("agent-state")).toHaveTextContent(
      /awaiting validator: scope-clarity/,
    );
  });

  it("shows tripwire fires with agent-facing copy (no 'alert' / 'warning' language)", () => {
    const fire: ProcessEvent = {
      id: "ev-fire-1",
      kind: "tripwire_fire",
      fired_at: "2026-04-28T11:00:00Z",
      session_id: "v08-foo",
      tripwire_id: "no-merge-without-self-review",
    };
    renderWithProviders(<LiveRail {...baseProps} tripwireFires={[fire]} />);

    const row = screen.getByTestId("tripwire-fire-row-ev-fire-1");
    expect(row).toHaveTextContent(/agent received tripwire/i);
    expect(row).toHaveTextContent(/no-merge-without-self-review/);
    expect(row).not.toHaveTextContent(/alert/i);
    expect(row).not.toHaveTextContent(/warning/i);
  });

  it("renders the cost-approval chip when an open inbox cost-approval entry exists, and fires the click callback", () => {
    const entry: InboxItem = {
      id: "inbox-cap",
      bucket: "blocked",
      title: "approve cost overrun",
      body: "",
      author: "pm-agent",
      created_at: "2026-04-28T10:30:00Z",
      references: [{ session: "v08-foo" }],
      escalation_reason: "cost-approval",
      resolved: false,
      resolved_at: null,
      resolved_by: null,
    };
    const onClick = vi.fn();
    renderWithProviders(
      <LiveRail
        {...baseProps}
        costApprovalEntry={entry}
        onCostApprovalClick={onClick}
      />,
    );

    const chip = screen.getByTestId("cost-approval-chip");
    expect(chip).toHaveTextContent(/cost approval needed/i);

    fireEvent.click(chip);
    expect(onClick).toHaveBeenCalledWith("inbox-cap");
  });

  it("hides the cost-approval chip when no entry is provided", () => {
    renderWithProviders(<LiveRail {...baseProps} costApprovalEntry={null} />);
    expect(screen.queryByTestId("cost-approval-chip")).toBeNull();
  });

  it("renders the INTERVENE button so the human's escape hatch is always reachable on the rail", () => {
    renderWithProviders(<LiveRail {...baseProps} />);
    expect(screen.getByRole("button", { name: /intervene/i })).toBeInTheDocument();
  });
});
