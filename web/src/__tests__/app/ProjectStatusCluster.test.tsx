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
  it("counts sessions by canonical session_status", async () => {
    // The cluster preferentially keys on `current_state` (the
    // structured agent-state) but falls back to `status` (the
    // session lifecycle state) when current_state is null. With
    // the v0.9.4 collapse there are no aliases — every counter
    // tracks a canonical SessionStatus directly.
    const ProjectStatusCluster = await loadCluster();
    const qc = makeTestQueryClient();
    qc.setQueryData(queryKeys.sessions("p1"), [
      makeSessionSummary({ id: "s1", status: "executing", current_state: null }),
      makeSessionSummary({ id: "s2", status: "executing", current_state: null }),
      makeSessionSummary({ id: "s3", status: "executing", current_state: null }),
      makeSessionSummary({ id: "s4", status: "queued", current_state: null }),
    ]);

    renderWithProviders(<ProjectStatusCluster wsStatus="open" />, { queryClient: qc });

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
