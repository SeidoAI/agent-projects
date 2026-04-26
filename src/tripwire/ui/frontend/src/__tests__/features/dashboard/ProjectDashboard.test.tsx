import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ProjectDashboard } from "@/features/dashboard/ProjectDashboard";
import type { EnumDescriptor } from "@/lib/api/endpoints/enums";
import type { EventsResponse } from "@/lib/api/endpoints/events";
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
  events?: EventsResponse;
}

function seed(data: Seed) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
  });
  if (data.project) qc.setQueryData(queryKeys.project("p1"), data.project);
  if (data.issues) qc.setQueryData(queryKeys.issues("p1"), data.issues);
  if (data.statusEnum) qc.setQueryData(queryKeys.enum("p1", "issue_status"), data.statusEnum);
  if (data.sessions) qc.setQueryData(queryKeys.sessions("p1"), data.sessions);
  // Events are seeded under the same query key the Dashboard consumes
  // (centre column "Recent Activity"). The Dashboard requests the
  // last 6 of a fixed kind list — match that exact param signature.
  if (data.events)
    qc.setQueryData(
      queryKeys.events("p1", {
        limit: 6,
        kinds: [
          "tripwire_fire",
          "validator_fail",
          "artifact_rejected",
          "pm_review_opened",
        ],
      }),
      data.events,
    );
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

function issue(id: string, status: string): IssueSummary {
  return {
    id,
    title: `title ${id}`,
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
      sessions: [
        session("sessA", "executing"),
        session("sessB", "in_review"),
      ],
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

  it("renders an empty state when there are no sessions and no events", () => {
    const wrapper = seed({
      project: { id: "p1", name: "Demo", key_prefix: "DEMO", phase: "scoping" },
      issues: [],
      statusEnum: ENUM,
      sessions: [],
    });
    render(<ProjectDashboard />, { wrapper });
    expect(screen.getByText(/no open sessions/i)).toBeInTheDocument();
    expect(screen.getByText(/no recent activity/i)).toBeInTheDocument();
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
});
