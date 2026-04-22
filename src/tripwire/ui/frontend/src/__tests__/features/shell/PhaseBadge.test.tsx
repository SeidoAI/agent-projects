import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ProjectDetail } from "@/lib/api/endpoints/project";
import { queryKeys } from "@/lib/api/queryKeys";

vi.mock("@/app/ProjectShell", () => ({
  useProjectShell: () => ({ projectId: "p1", wsStatus: "open" }),
}));

async function loadBadge() {
  const mod = await import("@/features/shell/PhaseBadge");
  return mod.PhaseBadge;
}

function withProject(project: ProjectDetail | undefined): {
  wrapper: ({ children }: { children: ReactNode }) => ReactElement;
} {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
  });
  if (project) {
    queryClient.setQueryData(queryKeys.project("p1"), project);
  }
  return {
    wrapper: ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    ),
  };
}

describe("PhaseBadge", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(() => new Promise(() => {})),
    );
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("renders the phase label and applies the phase-specific style", async () => {
    const PhaseBadge = await loadBadge();
    const { wrapper } = withProject({
      id: "p1",
      name: "Demo",
      key_prefix: "DEMO",
      phase: "executing",
    });

    render(<PhaseBadge />, { wrapper });

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
      const { wrapper } = withProject({
        id: "p1",
        name: "Demo",
        key_prefix: "DEMO",
        phase,
      });
      const { unmount } = render(<PhaseBadge />, { wrapper });
      const button = screen.getByRole("button", { name: new RegExp(phase, "i") });
      expect(button.className).toMatch(new RegExp(token));
      unmount();
    }
  });

  it("falls back to neutral styling for an unknown phase", async () => {
    const PhaseBadge = await loadBadge();
    const { wrapper } = withProject({
      id: "p1",
      name: "Demo",
      key_prefix: "DEMO",
      phase: "archived",
    });

    render(<PhaseBadge />, { wrapper });
    const button = screen.getByRole("button", { name: /archived/i });
    expect(button.className).toMatch(/muted/);
  });

  it("renders a loading skeleton while the project query is pending", async () => {
    const PhaseBadge = await loadBadge();
    const { wrapper } = withProject(undefined);

    render(<PhaseBadge />, { wrapper });
    expect(screen.getByLabelText("Project phase loading")).toBeInTheDocument();
  });

  it("lists phase transitions when phase_log is present", async () => {
    const PhaseBadge = await loadBadge();
    const { wrapper } = withProject({
      id: "p1",
      name: "Demo",
      key_prefix: "DEMO",
      phase: "executing",
      phase_log: [
        {
          from: "scoping",
          to: "scoped",
          at: "2026-04-10T12:00:00Z",
          by: "pm-agent",
        },
        {
          from: "scoped",
          to: "executing",
          at: "2026-04-15T09:30:00Z",
          by: "sean",
        },
      ],
    });

    render(<PhaseBadge />, { wrapper });
    fireEvent.click(screen.getByRole("button", { name: /executing/i }));

    expect(screen.getByText("Phase transitions")).toBeInTheDocument();
    expect(screen.getByText(/scoping → scoped/)).toBeInTheDocument();
    expect(screen.getByText(/scoped → executing/)).toBeInTheDocument();
    expect(screen.getByText(/pm-agent/)).toBeInTheDocument();
  });

  it("shows the empty-state message when phase_log is missing", async () => {
    const PhaseBadge = await loadBadge();
    const { wrapper } = withProject({
      id: "p1",
      name: "Demo",
      key_prefix: "DEMO",
      phase: "scoping",
    });

    render(<PhaseBadge />, { wrapper });
    fireEvent.click(screen.getByRole("button", { name: /scoping/i }));

    expect(screen.getByText("No transitions recorded yet.")).toBeInTheDocument();
  });
});
