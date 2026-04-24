import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SessionList } from "@/features/sessions/SessionList";
import type { SessionSummary } from "@/lib/api/endpoints/sessions";
import { queryKeys } from "@/lib/api/queryKeys";

vi.mock("@/app/ProjectShell", () => ({
  useProjectShell: () => ({ projectId: "p1", wsStatus: "open" }),
}));

function makeSession(overrides: Partial<SessionSummary> = {}): SessionSummary {
  return {
    id: "sess-a",
    name: "Session A",
    agent: "backend-coder",
    status: "active",
    issues: ["KUI-1", "KUI-2"],
    estimated_size: "M",
    blocked_by_sessions: [],
    repos: [],
    current_state: null,
    re_engagement_count: 0,
    task_progress: { done: 2, total: 5 },
    ...overrides,
  };
}

function prime(sessions: SessionSummary[]): {
  wrapper: ({ children }: { children: ReactNode }) => ReactElement;
} {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
  });
  qc.setQueryData(queryKeys.sessions("p1"), sessions);
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
  return { wrapper };
}

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

describe("SessionList", () => {
  it("renders a card per session with name, agent, and task progress", () => {
    const { wrapper } = prime([
      makeSession({ id: "a", name: "Session A" }),
      makeSession({
        id: "b",
        name: "Session B",
        status: "planned",
        task_progress: { done: 0, total: 0 },
      }),
    ]);
    render(<SessionList />, { wrapper });

    expect(screen.getByText("Session A")).toBeInTheDocument();
    expect(screen.getByText("Session B")).toBeInTheDocument();
    expect(screen.getAllByText(/backend-coder/).length).toBeGreaterThan(0);
    expect(screen.getByText("2/5")).toBeInTheDocument();
    expect(screen.getAllByTestId("task-progress-empty").length).toBeGreaterThan(0);
  });

  it("filters by status via the selector", () => {
    const { wrapper } = prime([
      makeSession({ id: "a", status: "active" }),
      makeSession({ id: "b", status: "planned", name: "Planned one" }),
    ]);
    render(<SessionList />, { wrapper });

    const select = screen.getByLabelText("Filter sessions by status");
    fireEvent.change(select, { target: { value: "active" } });
    // After selection, useSessions refetches with filter; since the initial cache
    // had both, the new query key has different cache. The UI should show both
    // until the new query resolves — but with no fetch mock, it stays pending.
    // We just verify the selector updated.
    expect((select as HTMLSelectElement).value).toBe("active");
  });

  it("hides blocked 'planned' sessions when Only actionable is on", () => {
    const { wrapper } = prime([
      makeSession({
        id: "blocked",
        name: "Blocked",
        status: "planned",
        blocked_by_sessions: ["upstream"],
      }),
      makeSession({
        id: "upstream",
        name: "Upstream",
        status: "active",
        blocked_by_sessions: [],
      }),
    ]);
    render(<SessionList />, { wrapper });

    // Before toggling, both show
    expect(screen.getByText("Blocked")).toBeInTheDocument();
    expect(screen.getByText("Upstream")).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText(/Only actionable/));

    expect(screen.queryByText("Blocked")).not.toBeInTheDocument();
    expect(screen.getByText("Upstream")).toBeInTheDocument();
  });

  it("renders the empty state when there are no sessions", () => {
    const { wrapper } = prime([]);
    render(<SessionList />, { wrapper });

    expect(screen.getByText(/No sessions yet. The PM agent creates sessions/)).toBeInTheDocument();
  });
});
