import { cleanup, fireEvent, screen } from "@testing-library/react";
import { http } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProjectDetail } from "@/lib/api/endpoints/project";
import { queryKeys } from "@/lib/api/queryKeys";
import { makeProject } from "../../mocks/fixtures";
import { server } from "../../mocks/server";
import { makeTestQueryClient, renderWithProviders } from "../../test-utils";

vi.mock("@/app/ProjectShell", () => ({
  useProjectShell: () => ({ projectId: "p1", wsStatus: "open" }),
}));

async function loadBadge() {
  const mod = await import("@/features/shell/PhaseBadge");
  return mod.PhaseBadge;
}

function renderBadge(project: ProjectDetail | undefined) {
  const qc = makeTestQueryClient();
  if (project) qc.setQueryData(queryKeys.project("p1"), project);
  return qc;
}

afterEach(() => {
  cleanup();
});

describe("PhaseBadge", () => {
  it("renders the phase label and applies the phase-specific style", async () => {
    const PhaseBadge = await loadBadge();
    renderWithProviders(<PhaseBadge />, {
      queryClient: renderBadge(makeProject({ phase: "executing" })),
    });

    const button = screen.getByRole("button", { name: /project phase: executing/i });
    expect(button).toHaveAttribute("data-phase", "executing");
    expect(button.className).toMatch(/emerald/);
  });

  it("applies scoping/scoped/reviewing styles for each known phase", async () => {
    const PhaseBadge = await loadBadge();
    for (const [phase, token] of [
      ["scoping", "blue"],
      ["scoped", "violet"],
      ["reviewing", "amber"],
    ] as const) {
      const { unmount } = renderWithProviders(<PhaseBadge />, {
        queryClient: renderBadge(makeProject({ phase })),
      });
      const button = screen.getByRole("button", { name: new RegExp(phase, "i") });
      expect(button.className).toMatch(new RegExp(token));
      unmount();
    }
  });

  it("falls back to neutral styling for an unknown phase", async () => {
    const PhaseBadge = await loadBadge();
    renderWithProviders(<PhaseBadge />, {
      queryClient: renderBadge(makeProject({ phase: "archived" })),
    });
    const button = screen.getByRole("button", { name: /archived/i });
    expect(button.className).toMatch(/muted/);
  });

  it("renders a loading skeleton while the project query is pending", async () => {
    // No cache seed + no MSW resolution = useProject stays in
    // `isLoading: true`. We hold the request open with an
    // unresolved promise so the assertion runs before any
    // reconciliation flips the skeleton off.
    server.use(http.get("/api/projects/p1", () => new Promise<Response>(() => {})));
    const PhaseBadge = await loadBadge();

    renderWithProviders(<PhaseBadge />, { queryClient: renderBadge(undefined) });
    expect(screen.getByLabelText("Project phase loading")).toBeInTheDocument();
  });

  it("lists phase transitions when phase_log is present", async () => {
    const PhaseBadge = await loadBadge();
    renderWithProviders(<PhaseBadge />, {
      queryClient: renderBadge(
        makeProject({
          phase: "executing",
          phase_log: [
            { from: "scoping", to: "scoped", at: "2026-04-10T12:00:00Z", by: "pm-agent" },
            { from: "scoped", to: "executing", at: "2026-04-15T09:30:00Z", by: "sean" },
          ],
        }),
      ),
    });

    fireEvent.click(screen.getByRole("button", { name: /executing/i }));

    expect(screen.getByText("Phase transitions")).toBeInTheDocument();
    expect(screen.getByText(/scoping → scoped/)).toBeInTheDocument();
    expect(screen.getByText(/scoped → executing/)).toBeInTheDocument();
    expect(screen.getByText(/pm-agent/)).toBeInTheDocument();
  });

  it("shows the empty-state message when phase_log is missing", async () => {
    const PhaseBadge = await loadBadge();
    renderWithProviders(<PhaseBadge />, {
      queryClient: renderBadge(makeProject({ phase: "scoping" })),
    });

    fireEvent.click(screen.getByRole("button", { name: /scoping/i }));

    expect(screen.getByText("No transitions recorded yet.")).toBeInTheDocument();
  });
});
