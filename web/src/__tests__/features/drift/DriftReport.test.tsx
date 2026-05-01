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
        workflow_drift_findings: 2,
      },
      workflow_drift_findings: [
        {
          code: "drift/prompt_check_missing",
          workflow: "coding-session",
          instance: "session-a",
          station: "queued",
          severity: "error",
          message: "missing prompt check",
        },
        {
          code: "drift/jit_prompt_should_have_fired",
          workflow: "coding-session",
          instance: "session-b",
          station: "executing",
          severity: "error",
          message: "missing JIT prompt",
        },
      ],
    });

    expect(screen.getByTestId("drift-score")).toHaveTextContent("78");
    expect(screen.getByText("Stale pins")).toBeInTheDocument();
    expect(screen.getByText("Unresolved references")).toBeInTheDocument();
    expect(screen.getByText("Stale concepts")).toBeInTheDocument();
    expect(screen.getByText("Workflow drift findings")).toBeInTheDocument();
  });

  it("clean project shows score 100 and empty drill-down", () => {
    renderWithSeed({
      score: 100,
      breakdown: {
        stale_pins: 0,
        unresolved_refs: 0,
        stale_concepts: 0,
        workflow_drift_findings: 0,
      },
      workflow_drift_findings: [],
    });
    expect(screen.getByTestId("drift-score")).toHaveTextContent("100");
    expect(screen.getByTestId("drift-drill-down")).toHaveTextContent(
      /no active workflow drift findings/i,
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
        workflow_drift_findings: 2,
      },
      workflow_drift_findings: [
        {
          code: "drift/prompt_check_missing",
          workflow: "coding-session",
          instance: "session-a",
          station: "queued",
          severity: "error",
          message: "missing prompt check",
        },
        {
          code: "drift/jit_prompt_should_have_fired",
          workflow: "coding-session",
          instance: "session-b",
          station: "executing",
          severity: "error",
          message: "missing JIT prompt",
        },
      ],
    });

    const drillDown = screen.getByTestId("drift-drill-down");
    expect(drillDown).toHaveTextContent("drift/prompt_check_missing");
    expect(drillDown).toHaveTextContent("missing JIT prompt");

    // Click the workflow_drift_findings row to filter — list stays
    // populated since the only findings are workflow drift findings.
    await user.click(screen.getByText("Workflow drift findings"));
    expect(screen.getByText("clear filter")).toBeInTheDocument();
  });
});
