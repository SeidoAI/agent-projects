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
  };
}

function session(id: string): SessionSummary {
  return {
    id,
    name: `Session ${id}`,
    agent: "frontend-coder",
    status: "active",
    issues: [],
    estimated_size: null,
    blocked_by_sessions: [],
    repos: [],
    current_state: null,
    re_engagement_count: 0,
    task_progress: { done: 0, total: 0 },
  };
}

describe("ProjectDashboard", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders status counts derived from issues + enum", () => {
    const wrapper = seed({
      project: {
        id: "p1",
        name: "Demo",
        key_prefix: "DEMO",
        phase: "executing",
      },
      issues: [
        issue("X-1", "todo"),
        issue("X-2", "todo"),
        issue("X-3", "doing"),
        issue("X-4", "done"),
      ],
      statusEnum: ENUM,
      sessions: [],
    });
    render(<ProjectDashboard />, { wrapper });

    // 4 issues total in the header
    expect(screen.getByText("4 issues")).toBeInTheDocument();
    // One card per enum value with the right count
    const todoCard = screen.getByLabelText(/2 issues in status To do/i);
    expect(todoCard).toHaveAttribute("href", "/p/p1/board?status=todo");
    expect(screen.getByLabelText(/1 issues in status Doing/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/1 issues in status Done/i)).toBeInTheDocument();
  });

  it("shows the phase card with a human description", () => {
    const wrapper = seed({
      project: { id: "p1", name: "Demo", key_prefix: "DEMO", phase: "executing" },
      issues: [],
      statusEnum: ENUM,
      sessions: [],
    });
    render(<ProjectDashboard />, { wrapper });
    expect(screen.getByText("executing")).toBeInTheDocument();
    expect(screen.getByText(/Sessions are in flight/)).toBeInTheDocument();
  });

  it("shows the empty-state copy when there are no sessions", () => {
    const wrapper = seed({
      project: { id: "p1", name: "Demo", key_prefix: "DEMO", phase: "scoping" },
      issues: [],
      statusEnum: ENUM,
      sessions: [],
    });
    render(<ProjectDashboard />, { wrapper });
    expect(screen.getByText(/No sessions yet/)).toBeInTheDocument();
  });

  it("renders recent sessions as links to the session detail route", () => {
    const wrapper = seed({
      project: { id: "p1", name: "Demo", key_prefix: "DEMO", phase: "executing" },
      issues: [],
      statusEnum: ENUM,
      sessions: [session("sessA"), session("sessB")],
    });
    render(<ProjectDashboard />, { wrapper });
    expect(screen.getByRole("link", { name: /Session sessA/ })).toHaveAttribute(
      "href",
      "/p/p1/sessions/sessA",
    );
  });

  it("renders shortcut links to board, graph, sessions", () => {
    const wrapper = seed({
      project: { id: "p1", name: "Demo", key_prefix: "DEMO", phase: "executing" },
      issues: [],
      statusEnum: ENUM,
      sessions: [],
    });
    render(<ProjectDashboard />, { wrapper });
    expect(screen.getByRole("link", { name: /Open board/ })).toHaveAttribute("href", "/p/p1/board");
    expect(screen.getByRole("link", { name: /Concept graph/ })).toHaveAttribute(
      "href",
      "/p/p1/graph",
    );
  });
});
