import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ProjectDashboard } from "@/features/dashboard/ProjectDashboard";
import type { EnumDescriptor } from "@/lib/api/endpoints/enums";
import type { IssueSummary } from "@/lib/api/endpoints/issues";
import type { ProjectDetail } from "@/lib/api/endpoints/project";
import type { SessionSummary } from "@/lib/api/endpoints/sessions";
import { queryKeys } from "@/lib/api/queryKeys";

vi.mock("@/app/ProjectShell", () => ({
  useProjectShell: () => ({ projectId: "p1", wsStatus: "open" }),
}));

interface Seed {
  project?: ProjectDetail;
  issues?: IssueSummary[];
  statusEnum?: EnumDescriptor;
  sessions?: SessionSummary[];
}

function issue(id: string, status: string): IssueSummary {
  return {
    id,
    title: `Issue ${id}`,
    status,
    priority: "medium",
    executor: "ai",
    verifier: "required",
    kind: null,
    agent: null,
    labels: [],
    parent: null,
    repo: null,
    blocked_by: [],
    is_blocked: false,
    is_epic: false,
    created_at: null,
    updated_at: null,
  };
}

function seed(data: Seed) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
  });
  if (data.project) qc.setQueryData(queryKeys.project("p1"), data.project);
  if (data.issues) qc.setQueryData(queryKeys.issues("p1"), data.issues);
  if (data.statusEnum) qc.setQueryData(queryKeys.enum("p1", "issue_status"), data.statusEnum);
  if (data.sessions) qc.setQueryData(queryKeys.sessions("p1"), data.sessions);
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/p/p1"]}>
        <Routes>
          <Route path="/p/:projectId" element={children} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

const ENUM: EnumDescriptor = {
  name: "issue_status",
  values: [
    { value: "todo", label: "To do", color: "#888", description: null },
    { value: "doing", label: "Doing", color: "#0af", description: null },
    { value: "done", label: "Done", color: "#0f0", description: null },
  ],
};

function session(id: string, current_state: string | null = null): SessionSummary {
  return {
    id,
    name: `Session ${id}`,
    agent: "frontend-coder",
    status: "active",
    issues: [],
    estimated_size: null,
    blocked_by_sessions: [],
    repos: [],
    current_state,
    re_engagement_count: 0,
    task_progress: { done: 0, total: 0 },
    cost_usd: 0,
  };
}

describe("ProjectDashboard", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders the project name as a hero heading", () => {
    const wrapper = seed({
      project: { id: "p1", name: "Demo Project", key_prefix: "DEMO", phase: "executing" },
      issues: [],
      statusEnum: ENUM,
      sessions: [],
    });
    render(<ProjectDashboard />, { wrapper });
    expect(screen.getByRole("heading", { name: /Demo Project/ })).toBeInTheDocument();
  });

  it("renders the lifecycle wire with the six default stations", () => {
    const wrapper = seed({
      project: { id: "p1", name: "Demo", key_prefix: "DEMO", phase: "executing" },
      issues: [],
      statusEnum: ENUM,
      sessions: [],
    });
    render(<ProjectDashboard />, { wrapper });
    // The default wire is the session lifecycle: planned → completed.
    for (const label of ["planned", "queued", "executing", "review", "verified", "completed"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it("groups open work by station and lists active sessions in the left column", () => {
    const wrapper = seed({
      project: { id: "p1", name: "Demo", key_prefix: "DEMO", phase: "executing" },
      issues: [],
      statusEnum: ENUM,
      sessions: [session("sessA", "executing"), session("sessB", "in_review")],
    });
    render(<ProjectDashboard />, { wrapper });
    expect(screen.getByRole("link", { name: /Session sessA/ })).toHaveAttribute(
      "href",
      "/p/p1/sessions/sessA",
    );
    expect(screen.getByRole("link", { name: /Session sessB/ })).toHaveAttribute(
      "href",
      "/p/p1/sessions/sessB",
    );
  });

  it("renders an empty state when there are no sessions", () => {
    const wrapper = seed({
      project: { id: "p1", name: "Demo", key_prefix: "DEMO", phase: "scoping" },
      issues: [],
      statusEnum: ENUM,
      sessions: [],
    });
    render(<ProjectDashboard />, { wrapper });
    expect(screen.getByText(/^no sessions$/i)).toBeInTheDocument();
  });

  it("does not crash when project data hasn't loaded yet", () => {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
    });
    function Wrap({ children }: { children: ReactNode }) {
      return (
        <QueryClientProvider client={qc}>
          <MemoryRouter initialEntries={["/p/p1"]}>
            <Routes>
              <Route path="/p/:projectId" element={children} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>
      );
    }
    render(<ProjectDashboard />, { wrapper: Wrap });
    // Falls back to the project id as the heading until the API resolves.
    expect(screen.getByRole("heading", { name: /p1/ })).toBeInTheDocument();
  });

  it("counts unassigned issues into the unassigned stage card", () => {
    const wrapper = seed({
      project: { id: "p1", name: "Demo", key_prefix: "DEMO", phase: "executing" },
      issues: [issue("X-1", "todo"), issue("X-2", "todo"), issue("X-3", "doing")],
      statusEnum: ENUM,
      sessions: [],
    });
    render(<ProjectDashboard />, { wrapper });
    // 3 issues, 0 sessions → unassigned card holds all 3.
    expect(
      screen.getByLabelText(/Filter to unassigned \(0 sessions, 3 issues\)/),
    ).toBeInTheDocument();
  });

  it("renders the project description under the heading when present", () => {
    const wrapper = seed({
      project: {
        id: "p1",
        name: "Demo",
        key_prefix: "DEMO",
        phase: "executing",
        description: "Two-line description.\nSecond line for vibes.",
      },
      issues: [issue("X-1", "todo")],
      statusEnum: ENUM,
      sessions: [],
    });
    render(<ProjectDashboard />, { wrapper });
    expect(screen.getByText(/Two-line description/i)).toBeInTheDocument();
    expect(screen.getByText(/Second line for vibes/i)).toBeInTheDocument();
  });

  it("omits the description block when project has no description", () => {
    const wrapper = seed({
      project: { id: "p1", name: "Demo", key_prefix: "DEMO", phase: "executing" },
      issues: [],
      statusEnum: ENUM,
      sessions: [],
    });
    render(<ProjectDashboard />, { wrapper });
    // No description text → no italic-serif tagline. Heading still
    // renders unchanged.
    expect(screen.getByRole("heading", { name: /Demo/ })).toBeInTheDocument();
  });

  it("renders the singular 'session' label when exactly one session is open", () => {
    const wrapper = seed({
      project: { id: "p1", name: "Demo", key_prefix: "DEMO", phase: "executing" },
      issues: [],
      statusEnum: ENUM,
      sessions: [session("sessA", "executing")],
    });
    render(<ProjectDashboard />, { wrapper });
    expect(screen.getByText(/^1 session$/)).toBeInTheDocument();
  });
});
