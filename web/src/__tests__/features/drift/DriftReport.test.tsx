import { cleanup, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DriftReport } from "@/features/drift/DriftReport";
import type { DriftReport as DriftReportPayload } from "@/lib/api/endpoints/drift";
import { queryKeys } from "@/lib/api/queryKeys";
import { makeTestQueryClient, renderWithProviders } from "../../test-utils";

vi.mock("@/app/ProjectShell", () => ({
  useProjectShell: () => ({ projectId: "p1", wsStatus: "open" }),
}));

afterEach(() => cleanup());

function renderWithSeed(payload: DriftReportPayload) {
  const queryClient = makeTestQueryClient();
  queryClient.setQueryData(queryKeys.drift("p1"), payload);
  return renderWithProviders(<DriftReport />, { queryClient, initialPath: "/" });
}

describe("DriftReport", () => {
  it("renders score and breakdown rows", () => {
    renderWithSeed({
      score: 78,
      breakdown: {
        stale_pins: 1,
        unresolved_refs: 2,
        stale_concepts: 0,
        workflow_drift_events: 3,
      },
      workflow_drift_events: [
        { event: "workflow_drift", at: "2026-04-30T10:00:00+00:00", kind: "stale_pin" },
        { event: "workflow_drift", at: "2026-04-29T10:00:00+00:00", kind: "missing_artifact" },
        { event: "workflow_drift", at: "2026-04-28T10:00:00+00:00", kind: "stale_pin" },
      ],
    });

    expect(screen.getByTestId("drift-score")).toHaveTextContent("78");
    expect(screen.getByText("Stale pins")).toBeInTheDocument();
    expect(screen.getByText("Unresolved references")).toBeInTheDocument();
    expect(screen.getByText("Stale concepts")).toBeInTheDocument();
    expect(screen.getByText("Workflow drift events")).toBeInTheDocument();
  });

  it("clean project shows score 100 and empty drill-down", () => {
    renderWithSeed({
      score: 100,
      breakdown: {
        stale_pins: 0,
        unresolved_refs: 0,
        stale_concepts: 0,
        workflow_drift_events: 0,
      },
      workflow_drift_events: [],
    });
    expect(screen.getByTestId("drift-score")).toHaveTextContent("100");
    expect(screen.getByTestId("drift-drill-down")).toHaveTextContent(
      /no recent workflow_drift events/i,
    );
  });

  it("clicking workflow-drift breakdown filters drill-down", async () => {
    const user = userEvent.setup();
    renderWithSeed({
      score: 70,
      breakdown: {
        stale_pins: 1,
        unresolved_refs: 0,
        stale_concepts: 0,
        workflow_drift_events: 2,
      },
      workflow_drift_events: [
        { event: "workflow_drift", at: "2026-04-30T10:00:00+00:00", kind: "stale_pin" },
        { event: "workflow_drift", at: "2026-04-29T10:00:00+00:00", kind: "missing_artifact" },
      ],
    });

    const drillDown = screen.getByTestId("drift-drill-down");
    expect(drillDown).toHaveTextContent("stale_pin");
    expect(drillDown).toHaveTextContent("missing_artifact");

    // Click the workflow_drift_events row to filter — list stays
    // populated since the only events are workflow_drift.
    await user.click(screen.getByText("Workflow drift events"));
    expect(screen.getByText("clear filter")).toBeInTheDocument();
  });
});
