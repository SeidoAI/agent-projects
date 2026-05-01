import { cleanup, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { queryKeys } from "@/lib/api/queryKeys";
import { makeSessionSummary } from "../mocks/fixtures";
import { makeTestQueryClient, renderWithProviders } from "../test-utils";

// `useProjectShell` is the only context dependency — stub it once
// at module scope so each test reuses the same projectId.
vi.mock("@/app/ProjectShell", () => ({
  useProjectShell: () => ({ projectId: "p1", wsStatus: "open" }),
}));

afterEach(() => cleanup());

async function loadCluster() {
  const mod = await import("@/app/ProjectStatusCluster");
  return mod.ProjectStatusCluster;
}

describe("ProjectStatusCluster — SessionStatusCluster top-bar counts", () => {
  it("collapses multi-state backend statuses onto the canonical executing stage", async () => {
    // Three sessions, three different "executing-ish" raw statuses
    // that the backend distinguishes (active, waiting_for_ci,
    // waiting_for_review). All three should land under canonical
    // `executing` once routed through `sessionStageId()`. Without
    // the mapping the top-bar exec counter would read 1 (only the
    // session whose raw state is literally "executing").
    const ProjectStatusCluster = await loadCluster();
    const qc = makeTestQueryClient();
    qc.setQueryData(queryKeys.sessions("p1"), [
      makeSessionSummary({ id: "s1", status: "executing", current_state: null }),
      makeSessionSummary({ id: "s2", status: "executing", current_state: "active" }),
      makeSessionSummary({ id: "s3", status: "executing", current_state: "waiting_for_ci" }),
      makeSessionSummary({ id: "s4", status: "queued", current_state: null }),
    ]);

    renderWithProviders(<ProjectStatusCluster wsStatus="open" />, { queryClient: qc });

    // Three sessions are in canonical `executing`; one in `queued`.
    // Counters render as `<n> exec` and `<n> queued`.
    expect(screen.getByText("3").className).toContain("color-rule");
    expect(screen.getByText(/exec/)).toBeInTheDocument();
    expect(screen.getByText("1").className).toContain("color-ink");
    expect(screen.getByText(/queued/)).toBeInTheDocument();
  });

  it("renders zeros when no sessions are in flight", async () => {
    const ProjectStatusCluster = await loadCluster();
    const qc = makeTestQueryClient();
    qc.setQueryData(queryKeys.sessions("p1"), [
      makeSessionSummary({ id: "s1", status: "completed" }),
      makeSessionSummary({ id: "s2", status: "verified" }),
    ]);

    renderWithProviders(<ProjectStatusCluster wsStatus="open" />, { queryClient: qc });

    expect(screen.getAllByText("0").length).toBeGreaterThanOrEqual(2);
  });
});
