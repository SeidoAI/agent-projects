import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import type { ReactElement, ReactNode } from "react";
import { Link, MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import { SessionDetail } from "@/features/sessions/SessionDetail";
import type { ArtifactManifest, ArtifactStatus } from "@/lib/api/endpoints/artifacts";
import type { IssueDetail } from "@/lib/api/endpoints/issues";
import type { SessionDetail as SessionDetailType } from "@/lib/api/endpoints/sessions";
import { queryKeys } from "@/lib/api/queryKeys";
import { server } from "../../mocks/server";

function clickTab(el: HTMLElement) {
  // Radix Tabs trigger uses onMouseDown + onClick; jsdom's fireEvent.click
  // alone doesn't always activate the trigger. Fire the full press sequence.
  fireEvent.mouseDown(el, { button: 0 });
  fireEvent.mouseUp(el, { button: 0 });
  fireEvent.click(el);
}

function baseSession(overrides: Partial<SessionDetailType> = {}): SessionDetailType {
  return {
    id: "sess-a",
    name: "Foundation packaging",
    agent: "backend-coder",
    status: "active",
    issues: ["KUI-1"],
    estimated_size: "M",
    blocked_by_sessions: [],
    repos: [{ repo: "SeidoAI/tripwire", base_branch: "main", branch: null, pr_number: null }],
    current_state: null,
    re_engagement_count: 0,
    task_progress: { done: 1, total: 3 },
    plan_md: "# Plan\n\nContent here.",
    key_files: [],
    docs: [],
    grouping_rationale: "Grouped because they share an API surface.",
    engagements: [],
    artifact_status: {},
    ...overrides,
  };
}

function baseIssue(): IssueDetail {
  return {
    id: "KUI-1",
    title: "First issue",
    status: "todo",
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
    body: "",
    refs: [],
    created_at: null,
    updated_at: null,
  };
}

function baseManifest(): ArtifactManifest {
  return {
    artifacts: [
      {
        name: "plan",
        file: "plan.md",
        template: "plan",
        produced_at: "planning",
        produced_by: "pm",
        owned_by: null,
        required: true,
        approval_gate: false,
      },
      {
        name: "task-checklist",
        file: "task-checklist.md",
        template: "task-checklist",
        produced_at: "executing",
        produced_by: "executor",
        owned_by: null,
        required: true,
        approval_gate: false,
      },
    ],
  };
}

function prime(opts: {
  session: SessionDetailType;
  issues?: IssueDetail[];
  manifest?: ArtifactManifest;
  statuses?: ArtifactStatus[];
}): {
  wrapper: ({ children }: { children: ReactNode }) => ReactElement;
} {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
  });
  qc.setQueryData(queryKeys.session("p1", opts.session.id), opts.session);
  for (const issue of opts.issues ?? []) {
    qc.setQueryData(queryKeys.issue("p1", issue.id), issue);
  }
  if (opts.manifest) {
    qc.setQueryData(queryKeys.artifactManifest("p1"), opts.manifest);
  }
  if (opts.statuses) {
    qc.setQueryData(queryKeys.sessionArtifacts("p1", opts.session.id), opts.statuses);
  }

  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/p/p1/sessions/${opts.session.id}`]}>
        <Routes>
          <Route path="/p/:projectId/sessions/:sid" element={children} />
          <Route path="/p/:projectId/sessions" element={<div>sessions stub</div>} />
          <Route path="/p/:projectId/issues/:key" element={<div>issue stub</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
  return { wrapper };
}

afterEach(() => {
  cleanup();
});

describe("SessionDetail", () => {
  it("renders header, tabs, and switches to each tab", () => {
    const { wrapper } = prime({
      session: baseSession(),
      issues: [baseIssue()],
      manifest: baseManifest(),
      statuses: [],
    });
    const { container } = render(<SessionDetail />, { wrapper });

    expect(screen.getByText("Foundation packaging")).toBeInTheDocument();
    expect(screen.getByText("active")).toBeInTheDocument();
    expect(screen.getByText("1/3")).toBeInTheDocument();

    // Plan tab active by default, markdown rendered
    expect(container.querySelector('[role="tabpanel"][data-state="active"]')).not.toBeNull();
    expect(screen.getByRole("heading", { name: "Plan" })).toBeInTheDocument();

    // Issues tab
    clickTab(screen.getByRole("tab", { name: "Issues" }));
    expect(screen.getByText(/Grouped because/)).toBeInTheDocument();
    expect(screen.getByText("First issue")).toBeInTheDocument();

    // Repos tab
    clickTab(screen.getByRole("tab", { name: "Repos" }));
    expect(screen.getByText("SeidoAI/tripwire")).toBeInTheDocument();

    // Artifacts tab — verify the inner ArtifactList tabs appear
    clickTab(screen.getByRole("tab", { name: "Artifacts" }));
    expect(container.querySelector('[data-tab-name="plan"]')).not.toBeNull();
    expect(container.querySelector('[data-tab-name="task-checklist"]')).not.toBeNull();
  });

  it("resets the active tab to Plan when the URL :sid changes", async () => {
    const sessionA = baseSession({ id: "sess-a", name: "Session A" });
    const sessionB = baseSession({ id: "sess-b", name: "Session B" });
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
    });
    qc.setQueryData(queryKeys.session("p1", sessionA.id), sessionA);
    qc.setQueryData(queryKeys.session("p1", sessionB.id), sessionB);

    // A link inside the route tree triggers a client-side navigation so the
    // `:sid` segment changes while the Router / QueryClient / DOM tree are
    // all preserved — the exact condition the `key={sid}` fix targets.
    const GoToB = () => (
      <Link to={`/p/p1/sessions/${sessionB.id}`} data-testid="nav-b">
        go B
      </Link>
    );

    const { container } = render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={[`/p/p1/sessions/${sessionA.id}`]}>
          <Routes>
            <Route
              path="/p/:projectId/sessions/:sid"
              element={
                <>
                  <GoToB />
                  <SessionDetail />
                </>
              }
            />
            <Route path="/p/:projectId/sessions" element={<div>sessions stub</div>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    // Start on Session A, switch to Repos tab.
    expect(screen.getByText("Session A")).toBeInTheDocument();
    clickTab(screen.getByRole("tab", { name: "Repos" }));
    const activeA = container.querySelector('[role="tab"][data-state="active"]');
    expect(activeA?.textContent).toMatch(/Repos/);

    // Client-side nav to session B via an in-tree link.
    fireEvent.click(screen.getByTestId("nav-b"));

    // React re-renders with the new :sid. `key={sid}` on SessionDetailInner
    // remounts the subtree; the uncontrolled Tabs default ("plan") wins.
    expect(await screen.findByText("Session B")).toBeInTheDocument();
    const activeB = container.querySelector('[role="tab"][data-state="active"]');
    expect(activeB?.textContent).toMatch(/Plan/);
  });

  it("renders 'not found' when the session API returns 404", async () => {
    server.use(
      http.get("/api/projects/p1/sessions/missing", () =>
        HttpResponse.json({ detail: "missing", code: "session/not_found" }, { status: 404 }),
      ),
    );
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/p/p1/sessions/missing"]}>
          <Routes>
            <Route path="/p/:projectId/sessions/:sid" element={children} />
            <Route path="/p/:projectId/sessions" element={<div>sessions stub</div>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );
    render(<SessionDetail />, { wrapper });

    expect(await screen.findByText("Session not found")).toBeInTheDocument();
  });
});
